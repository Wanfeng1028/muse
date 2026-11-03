//! Radio signal recordings, decoded by rtl_433 run as an external program (never linked): it reads
//! a saved recording (I/Q samples such as `.cu8`/`.cs16`/`.cf32`, or AM/FM `.s16`), recognises the
//! devices it knows (weather stations, remotes, tyre sensors, meters…) and prints one JSON object
//! per message, which become the evidence.

use super::external_disasm_tools::{input_file, locate, run};
use super::native_common::{params_json, spec};
use super::static_input::builder;
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Authority, Confidence, Coverage, Limitation, Subject, ToolError};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use std::collections::BTreeMap;

pub fn specs() -> Vec<ToolSpec> {
    let eng = Requires::Engine("rtl433");
    vec![
        spec(
            "radio_recording_decode",
            "Decode a radio recording",
            "Decode a saved radio recording (absolute path or the active target) with rtl_433: I/Q samples (.cu8, .cs8, .cs16, .cf32) or demodulated AM/FM (.am.s16, .fm.s16), format and sample rate read from the file name (for example g001_433.92M_250k.cu8; 250 kHz when absent) unless sample_rate is given. Returns each decoded message (device model, id, channel and readings) paged with offset/limit, plus counts by model. decoders limits decoding to those protocol numbers (see radio_decoders_list); otherwise rtl_433's default set runs. Optional engine.",
            "Find out which devices a radio recording heard and what they sent.",
            Toolset::Formats,
            Effects::LAUNCHES_PROCESS,
            eng,
            schema_of::<DecodeParams>,
            radio_recording_decode,
        ),
        spec(
            "radio_decoders_list",
            "List radio decoders",
            "List the device protocols the installed rtl_433 can decode: number, name, and whether it runs by default (the others only run when asked for with decoders). Optional engine.",
            "See which radio devices can be recognised.",
            Toolset::Formats,
            Effects::LAUNCHES_PROCESS,
            eng,
            schema_of::<ListParams>,
            radio_decoders_list,
        ),
    ]
}

fn d_limit() -> usize {
    200
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DecodeParams {
    /// Absolute path of the recording; omit to use the active target.
    #[serde(default)]
    pub path: Option<String>,
    /// Protocol numbers to decode (from radio_decoders_list); empty runs the default set.
    #[serde(default)]
    pub decoders: Vec<u16>,
    /// Sample rate in Hz, when the file name doesn't say.
    #[serde(default)]
    pub sample_rate: Option<u32>,
    /// First message of the page.
    #[serde(default)]
    pub offset: usize,
    /// Messages per page (1–5000, default 200).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ListParams {
    /// Only decoders whose name contains this text (any case).
    #[serde(default)]
    pub filter: Option<String>,
}

/// rtl_433's arguments for decoding `file`.
fn decode_args(file: &str, decoders: &[u16], sample_rate: Option<u32>) -> Vec<String> {
    let mut a: Vec<String> = vec!["-F".into(), "json".into()];
    for d in decoders {
        a.extend(["-R".to_string(), d.to_string()]);
    }
    if let Some(r) = sample_rate {
        a.extend(["-s".to_string(), r.to_string()]);
    }
    a.extend(["-r".into(), file.to_string()]);
    a
}

/// The JSON messages in rtl_433's output (other lines are ignored), and how many lines weren't JSON.
fn messages(stdout: &str) -> (Vec<Map<String, Value>>, usize) {
    let mut out = Vec::new();
    let mut other = 0;
    for line in stdout.lines().map(str::trim).filter(|l| !l.is_empty()) {
        match serde_json::from_str::<Value>(line) {
            Ok(Value::Object(m)) => out.push(m),
            _ => other += 1,
        }
    }
    (out, other)
}

/// One protocol from `rtl_433 -R help`: `  [07]* Name` (the star: off by default).
fn decoder_line(line: &str) -> Option<Value> {
    let rest = line.trim_start().strip_prefix('[')?;
    let (num, rest) = rest.split_once(']')?;
    let number: u16 = num.trim().parse().ok()?;
    let (off, name) = match rest.strip_prefix('*') {
        Some(n) => (true, n),
        None => (false, rest),
    };
    let name = name.trim();
    (!name.is_empty()).then(|| json!({"number": number, "name": name, "default": !off}))
}

fn radio_recording_decode(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: DecodeParams = parse_params(params)?;
    if p.decoders.len() > 64 || p.decoders.contains(&0) {
        return Err(ToolError::invalid("decoders takes up to 64 protocol numbers from radio_decoders_list (1 and up)"));
    }
    if p.sample_rate.is_some_and(|r| !(1_000..=100_000_000).contains(&r)) {
        return Err(ToolError::invalid("sample_rate must be between 1 kHz and 100 MHz"));
    }
    let (file, subject) = input_file(ctx, p.path.as_deref())?;
    let exe = locate(ctx, "rtl433")?;
    // On Windows rtl_433 reads a path given with `/` as nothing at all (and still exits 0).
    let file_arg = if cfg!(windows) { file.display().to_string().replace('/', "\\") } else { file.display().to_string() };
    let args = decode_args(&file_arg, &p.decoders, p.sample_rate);
    ctx.report(None, "Decoding the recording with rtl_433");
    let out = run(ctx, &exe, &args, "rtl_433")?;
    let (msgs, other) = messages(&out.stdout_text());
    if !out.success && msgs.is_empty() {
        return Err(craft_anything_platform::process::nonzero_error("rtl_433", &out));
    }
    let mut by_model: BTreeMap<String, u64> = BTreeMap::new();
    for m in &msgs {
        let model = m.get("model").and_then(Value::as_str).unwrap_or("(no model)");
        *by_model.entry(model.to_string()).or_default() += 1;
    }
    let limit = p.limit.clamp(1, 5000);
    let page: Vec<&Map<String, Value>> = msgs.iter().skip(p.offset).take(limit).collect();
    let mut lims = vec![
        Limitation::new("decoder_coverage", "Only devices rtl_433 has a decoder for are recognised; anything else in the recording is silently skipped."),
        Limitation::new("raw_tool_output", "Field names and units are rtl_433's own and can change between its versions."),
    ];
    if msgs.is_empty() {
        lims.push(Limitation::new(
            "nothing_decoded",
            "No messages: the recording may hold no known device, need other decoders (radio_decoders_list), or have a sample rate or format the file name doesn't state.",
        ));
    }
    if out.stdout_truncated {
        lims.push(Limitation::new("output_capped", "rtl_433 printed more than 16 MiB; later messages were cut off."));
    }
    if !out.success {
        lims.push(Limitation::new("nonzero_exit", format!("rtl_433 exited with {:?}; see stderr.", out.code)));
    }
    let stderr = out.stderr_text();
    let e = builder(ctx, "radio_recording_decode", subject, params_json(&p))
        .result(json!({
            "tool": exe,
            "arguments": args,
            "exit_code": out.code,
            "total_messages": msgs.len(),
            "by_model": by_model,
            "offset": p.offset,
            "limit": limit,
            "messages": page,
            "other_lines": other,
            "stderr": stderr.get(..stderr.floor_char_boundary(16 << 10)).unwrap_or(""),
        }))
        .summary(format!("rtl_433 decoded {} message(s) from {} kind(s) of device.", msgs.len(), by_model.len()))
        .confidence(Confidence::Observed)
        .authority(Authority::OutsideService)
        .limitations(lims)
        .coverage(Coverage::page(page.len() as u64, msgs.len() as u64, p.offset as u64))
        .build()?;
    Ok(ToolOutput::evidence(e))
}

fn radio_decoders_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ListParams = parse_params(params)?;
    let exe = locate(ctx, "rtl433")?;
    let args = vec!["-R".to_string(), "help".to_string()];
    let out = run(ctx, &exe, &args, "rtl_433")?;
    // The list goes to stdout or stderr depending on the version; it may exit non-zero after it.
    let text = format!("{}\n{}", out.stdout_text(), out.stderr_text());
    let needle = p.filter.as_deref().map(str::to_lowercase);
    let all: Vec<Value> = text.lines().filter_map(decoder_line).collect();
    if all.is_empty() {
        return Err(
            craft_anything_platform::process::nonzero_error("rtl_433", &out).with_remediation("This rtl_433 didn't print a decoder list; check its version.")
        );
    }
    let shown: Vec<&Value> =
        all.iter().filter(|d| needle.as_deref().is_none_or(|n| d["name"].as_str().is_some_and(|s| s.to_lowercase().contains(n)))).collect();
    let subject = Subject { kind: "engine".into(), sha256: None, name: Some("rtl_433".into()) };
    let e = builder(ctx, "radio_decoders_list", subject, params_json(&p))
        .result(json!({"tool": exe, "total": all.len(), "shown": shown.len(), "decoders": shown}))
        .summary(format!("rtl_433 knows {} protocol(s); {} shown.", all.len(), shown.len()))
        .confidence(Confidence::Observed)
        .authority(Authority::OutsideService)
        .coverage(Coverage::complete(shown.len() as u64))
        .build()?;
    Ok(ToolOutput::evidence(e))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{CallOptions, Caller, Engine};

    #[test]
    fn reads_rtl_433_output() {
        let out = "rtl_433 version 25.02\n{\"time\":\"@0.1s\",\"model\":\"Acurite-Tower\",\"id\":1,\"temperature_C\":21.5}\nnot json\n{\"model\":\"Acurite-Tower\",\"id\":2}\n[1, 2]\n";
        let (m, other) = messages(out);
        assert_eq!(m.len(), 2);
        assert_eq!(m[0]["temperature_C"], 21.5);
        assert_eq!(other, 3);

        assert_eq!(decoder_line("    [01]  Silvercrest Remote Control"), Some(json!({"number": 1, "name": "Silvercrest Remote Control", "default": true})));
        assert_eq!(decoder_line("    [07]* Waveman Switch Transmitter"), Some(json!({"number": 7, "name": "Waveman Switch Transmitter", "default": false})));
        for no in ["", "Usage:", "[x] name", "[3]", "  -R <device> | help"] {
            assert_eq!(decoder_line(no), None, "{no}");
        }

        assert_eq!(
            decode_args("/r/g001_433.92M_250k.cu8", &[40, 41], Some(1_000_000)),
            ["-F", "json", "-R", "40", "-R", "41", "-s", "1000000", "-r", "/r/g001_433.92M_250k.cu8"]
        );
    }

    #[test]
    fn bad_requests_are_refused_before_running() {
        let mut s = crate::testing::session();
        // A stand-in path, so the checks below run without rtl_433 installed.
        let stand_in = craft_anything_testkit::temp_file("rtl_433.exe", b"");
        s.settings.engines.tools.rtl433 = Some(stand_in.clone());
        let e = Engine::new(s);
        for bad in [json!({"path": stand_in, "decoders": [0]}), json!({"path": stand_in, "sample_rate": 5}), json!({"path": "relative.cu8"})] {
            assert!(e.call("radio_recording_decode", bad.clone(), CallOptions::new(Caller::Mcp)).is_err(), "{bad}");
        }
    }

    /// A real decode, only where `CRAFT_ANYTHING_TEST_RTL433` names rtl_433 and
    /// `CRAFT_ANYTHING_TEST_RTL433_REC` a recording of an Acurite rain gauge (from rtl_433's tests).
    #[test]
    fn live_decode_with_rtl_433() {
        let (Some(exe), Some(rec)) = (std::env::var_os("CRAFT_ANYTHING_TEST_RTL433"), std::env::var("CRAFT_ANYTHING_TEST_RTL433_REC").ok()) else { return };
        let mut s = crate::testing::session();
        s.settings.engines.tools.rtl433 = Some(exe.into());
        let e = Engine::new(s);
        let Ok(ToolOutput::Evidence(ev)) = e.call("radio_recording_decode", json!({"path": rec}), CallOptions::new(Caller::Mcp)) else {
            panic!("decode failed")
        };
        let r = serde_json::to_value(&*ev).unwrap()["result"].clone();
        assert!(r["total_messages"].as_u64().unwrap() > 0, "{r}");
        assert!(r["by_model"]["Acurite-Rain899"].as_u64().is_some(), "{r}");
        let Ok(ToolOutput::Evidence(ev)) = e.call("radio_decoders_list", json!({"filter": "acurite"}), CallOptions::new(Caller::Mcp)) else {
            panic!("list failed")
        };
        let r = serde_json::to_value(&*ev).unwrap()["result"].clone();
        assert!(r["total"].as_u64().unwrap() > 100 && r["shown"].as_u64().unwrap() > 0, "{r}");
    }
}
