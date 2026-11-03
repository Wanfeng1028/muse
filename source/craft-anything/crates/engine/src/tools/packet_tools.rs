//! Saved packet captures (pcap and pcapng). The built-in decoder (craft_anything_formats::pcap)
//! needs nothing installed: an overview with paged conversations, and per-packet decoded fields
//! with simple filters. When Wireshark's `tshark` is installed it can produce the address, DNS,
//! TLS-name, protocol and HTTP inventories instead; the built-in decoder is the fallback. Nothing
//! is captured live, nothing is sent on the network.

use super::native_common::{page, params_json, spec};
use super::static_input::{self, Input, builder, format_err};
use super::{Detail, detailed};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Authority, Confidence, Coverage, ErrorCode, Limitation, Location, Subject, ToolError};
use craft_anything_formats::pcap::{self, Capture, Count, FlowTable};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::net::IpAddr;
use std::path::PathBuf;
use std::time::Duration;

pub fn specs() -> Vec<ToolSpec> {
    let e = Effects::EVIDENCE;
    vec![
        spec(
            "packets_capture_show",
            "Packet capture overview",
            "Summarize a saved pcap or pcapng capture with the built-in decoder (nothing installed): format, interfaces and link types, packet and byte counts, time span, frames per protocol, busiest addresses, conversations (flows) with packets and bytes in each direction and the application protocols seen (paged), DNS questions and answers, HTTP/1.x requests (method, Host, target; credentials removed) and TLS ClientHello server names (SNI) and ALPN. Decodes Ethernet (VLAN), raw IP, Linux cooked and loopback links; IPv4, IPv6, TCP, UDP, ICMP. Each packet is decoded on its own: no stream reassembly, no decryption.",
            "See who talked to whom in a saved network capture, and which sites were looked up.",
            Toolset::Formats,
            e,
            Requires::Nothing,
            schema_of::<CaptureParams>,
            packets_capture_show,
        ),
        spec(
            "packets_fields_show",
            "Packet fields",
            "List decoded fields of individual packets in a saved pcap or pcapng capture, paged: frame number, time, link, protocol stack, addresses and ports, conversation (flow) id, IP TTL, TCP flags/sequence/window, UDP and ICMP details, DNS questions and answers, HTTP/1.x request or status line with Host, TLS ClientHello SNI/ALPN/versions. Filter by protocol (e.g. dns, tls, http, tcp, udp, icmp, ipv6, arp), IP address, port, or flow id from packets_capture_show. Built-in decoder.",
            "Look at individual packets in a capture, filtered by protocol, address or port.",
            Toolset::Formats,
            e,
            Requires::Nothing,
            schema_of::<FieldsParams>,
            packets_fields_show,
        ),
        spec(
            "engines_tshark_check",
            "Wireshark tools check",
            "Check whether Wireshark's tshark is installed (Settings → Engines, the engine store, PATH, or the standard Wireshark folder) and which version it reports. Reads no capture. Optional: the built-in capture decoder works without it.",
            "Check whether Wireshark's command-line tool is available.",
            Toolset::Formats,
            Effects::NATIVE_EVIDENCE,
            Requires::Nothing,
            schema_of::<ClientParams>,
            engines_tshark_check,
        ),
        spec(
            "packets_inventory_show",
            "Capture inventories",
            "Inventories of a saved pcap or pcapng capture: packet count, protocol stacks, IPv4/IPv6 addresses with packet counts, DNS questions and the addresses answered for them, TLS server names (SNI) and HTTP request URIs (credentials removed), each with counts and limited to `limit` rows. Uses Wireshark's tshark when installed (engine=auto or tshark; full dissectors, run with a deadline and capped output) and the built-in decoder otherwise (engine=built_in forces it).",
            "List the addresses, websites and protocols found in a saved network capture.",
            Toolset::Formats,
            Effects::NATIVE_EVIDENCE,
            Requires::Nothing,
            schema_of::<InventoryParams>,
            packets_inventory_show,
        ),
    ]
}

fn d_limit() -> usize {
    100
}
fn d_fields_limit() -> usize {
    50
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CaptureParams {
    /// Absolute path of a .pcap/.pcapng file; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// First conversation (flow) of the page.
    #[serde(default)]
    pub offset: usize,
    /// Conversations per page (1–5000, default 100). Inventories show their top 100.
    #[serde(default = "d_limit")]
    pub limit: usize,
    /// summary or complete (default).
    #[serde(default)]
    pub detail: Detail,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct FieldsParams {
    /// Absolute path of a .pcap/.pcapng file; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Only packets with this protocol in their stack (eth, vlan, ipv4, ipv6, arp, tcp, udp, icmp, icmpv6, dns, mdns, http, tls).
    #[serde(default)]
    pub protocol: Option<String>,
    /// Only packets from or to this IP address.
    #[serde(default)]
    pub ip: Option<String>,
    /// Only packets from or to this TCP/UDP port.
    #[serde(default)]
    pub port: Option<u16>,
    /// Only packets of this conversation (the flow id from packets_capture_show, e.g. 3 or "f3").
    #[serde(default)]
    pub flow: Option<String>,
    /// First matching packet of the page.
    #[serde(default)]
    pub offset: usize,
    /// Packets per page (1–1000, default 50).
    #[serde(default = "d_fields_limit")]
    pub limit: usize,
}

#[derive(Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ClientParams {}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum CaptureEngine {
    /// tshark when installed, the built-in decoder otherwise.
    #[default]
    Auto,
    BuiltIn,
    Tshark,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct InventoryParams {
    /// Absolute path of a .pcap/.pcapng file; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// auto (default), built_in or tshark.
    #[serde(default)]
    pub engine: CaptureEngine,
    /// Rows kept per inventory, most frequent first (1–10000, default 100).
    #[serde(default = "d_limit")]
    pub limit: usize,
    /// summary or complete (default).
    #[serde(default)]
    pub detail: Detail,
}

fn load(ctx: &Ctx<'_>, path: Option<&str>) -> Result<Input, ToolError> {
    let input = static_input::load(ctx, path, static_input::DEFAULT_MAX_BYTES)?;
    if !pcap::is_capture(&input.bytes) {
        return Err(ToolError::new(ErrorCode::NotSupported, format!("{} is not a pcap or pcapng capture", input.name))
            .with_remediation("Save the capture as .pcap or .pcapng (for example from Wireshark: File → Save As). HAR files go to web_recording_show."));
    }
    Ok(input)
}

fn time(ns: Option<u64>) -> Option<String> {
    ns.map(pcap::iso8601)
}

fn top(v: &[Count], n: usize) -> &[Count] {
    v.get(..n.min(v.len())).unwrap_or(&[])
}

fn common_limitations() -> Vec<Limitation> {
    vec![
        Limitation::new(
            "per_packet_decoding",
            "Each packet is decoded on its own: data split across TCP segments (a long HTTP header, a large TLS ClientHello) is not reassembled, and encrypted payloads are not decrypted.",
        ),
        Limitation::new(
            "recording_only",
            "A capture shows only what was recorded on that interface during that time; traffic that is missing here may still have happened.",
        ),
    ]
}

// ---------------------------------------------------------------------------------------------
// packets_capture_show

fn packets_capture_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CaptureParams = parse_params(params)?;
    let input = load(ctx, p.path.as_deref())?;
    ctx.report(None, format!("Decoding {}", input.name));
    let cancel = ctx.cancel.clone();
    let s = pcap::summarize(&input.bytes, &|| cancel.is_cancelled()).map_err(|e| format_err(e, "a packet capture"))?;
    ctx.cancel.check()?;
    let (flows, cov) = page(&s.flows, p.offset, p.limit);
    let duration = s.first_ts_ns.zip(s.last_ts_ns).map(|(a, b)| b.saturating_sub(a) as f64 / 1e9);
    let summary = format!(
        "{} capture: {} packets, {} bytes{}, {} conversations, {} DNS names asked, {} TLS server names, {} HTTP requests.",
        s.format,
        s.packets,
        s.bytes,
        duration.map(|d| format!(" over {d:.1} s")).unwrap_or_default(),
        s.flows.len(),
        s.dns_queries.len(),
        s.tls_sni.len(),
        s.http_requests.len()
    );
    let mut lims = common_limitations();
    if !s.warnings.is_empty() {
        lims.push(Limitation::new("read_warnings", "Part of the file could not be read; see warnings. Packets after the damage are not counted."));
    }
    if s.undecoded_frames > 0 {
        lims.push(Limitation::new(
            "undecoded_frames",
            format!("{} frames have no decoded IP layer (other link types, ARP or other protocols).", s.undecoded_frames),
        ));
    }
    if !s.capped_inventories.is_empty() || s.flows_untracked_frames > 0 || s.truncated {
        lims.push(Limitation::new(
            "caps_hit",
            "A size cap was reached (see capped_inventories, flows_untracked_frames and truncated); counts past it are partial.",
        ));
    }
    let extras = json!({"counts": {"packets": s.packets, "flows": s.flows.len(), "dns_queries": s.dns_queries.len(), "tls_sni": s.tls_sni.len(), "http_requests": s.http_requests.len()}});
    let ev = builder(ctx, "packets_capture_show", input.subject.clone(), params_json(&p))
        .result(json!({
            "path": input.path,
            "format": s.format,
            "version": s.version,
            "interfaces": s.interfaces,
            "packets": s.packets,
            "bytes": s.bytes,
            "first_time": time(s.first_ts_ns),
            "last_time": time(s.last_ts_ns),
            "duration_seconds": duration,
            "protocols": s.protocols,
            "protocol_stacks": top(&s.stacks, 100),
            "endpoints": top(&s.endpoints, 100),
            "endpoint_count": s.endpoints.len(),
            "flow_count": s.flows.len(),
            "flows": flows,
            "flows_untracked_frames": s.flows_untracked_frames,
            "dns_queries": top(&s.dns_queries, 100),
            "dns_answers": top(&s.dns_answers, 100),
            "http_requests": top(&s.http_requests, 100),
            "tls_sni": top(&s.tls_sni, 100),
            "tls_alpn": top(&s.tls_alpn, 100),
            "undecoded_frames": s.undecoded_frames,
            "capped_inventories": s.capped_inventories,
            "truncated": s.truncated,
            "warnings": s.warnings,
            "continue_with": "packets_fields_show",
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::EarlierRecord)
        .limitations(lims)
        .coverage(cov)
        .location(Location::new("path", input.path.display().to_string()))
        .build()?;
    detailed(ctx, ev, p.detail, extras)
}

// ---------------------------------------------------------------------------------------------
// packets_fields_show

fn packets_fields_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: FieldsParams = parse_params(params)?;
    let want_ip: Option<IpAddr> = match p.ip.as_deref().map(str::trim).filter(|s| !s.is_empty()) {
        Some(s) => Some(s.parse().map_err(|_| ToolError::invalid(format!("{s:?} is not an IP address")))?),
        None => None,
    };
    let want_flow: Option<usize> = match p.flow.as_deref().map(str::trim).filter(|s| !s.is_empty()) {
        Some(s) => Some(s.trim_start_matches(['f', 'F']).parse().map_err(|_| ToolError::invalid(format!("{s:?} is not a flow id (use 3 or f3)")))?),
        None => None,
    };
    let want_proto = p.protocol.as_deref().map(|s| s.trim().to_ascii_lowercase()).filter(|s| !s.is_empty());
    let limit = p.limit.clamp(1, 1000);
    let input = load(ctx, p.path.as_deref())?;
    ctx.report(None, format!("Decoding packets in {}", input.name));
    let mut cap = Capture::new(&input.bytes).map_err(|e| format_err(e, "a packet capture"))?;
    let mut flows = FlowTable::default();
    let (mut total, mut matched) = (0u64, 0u64);
    let mut rows: Vec<Value> = Vec::new();
    for f in cap.by_ref() {
        if f.number % 4096 == 0 {
            ctx.cancel.check()?;
        }
        total += 1;
        let d = pcap::decode(f.link_type, f.data);
        let flow = d.flow_key().and_then(|(k, _)| flows.id_for(k));
        let t = d.transport.as_ref();
        let ok = want_proto.as_deref().is_none_or(|w| d.protocols.contains(&w))
            && want_ip.is_none_or(|ip| d.ip.as_ref().is_some_and(|x| x.src == ip || x.dst == ip))
            && p.port.is_none_or(|port| t.is_some_and(|t| t.src_port == Some(port) || t.dst_port == Some(port)))
            && want_flow.is_none_or(|w| flow == Some(w));
        if !ok {
            continue;
        }
        matched += 1;
        if matched <= p.offset as u64 || rows.len() >= limit {
            continue;
        }
        let mut row = json!({
            "frame": f.number,
            "time": time(f.ts_ns),
            "interface": f.interface,
            "link": pcap::link_name(f.link_type),
            "captured_len": f.data.len(),
            "original_len": f.original_len,
            "protocols": d.stack(),
            "flow": flow,
            "src": d.ip.as_ref().map(|ip| pcap::endpoint((ip.src, t.and_then(|t| t.src_port).unwrap_or(0)))),
            "dst": d.ip.as_ref().map(|ip| pcap::endpoint((ip.dst, t.and_then(|t| t.dst_port).unwrap_or(0)))),
        });
        if let (Value::Object(m), Ok(Value::Object(x))) = (&mut row, serde_json::to_value(&d)) {
            m.extend(x.into_iter().filter(|(k, _)| k != "protocols"));
        }
        rows.push(row);
    }
    let shown = rows.len() as u64;
    let cov = Coverage::page(shown, matched, p.offset as u64);
    let mut lims = common_limitations();
    if !cap.warnings.is_empty() {
        lims.push(Limitation::new("read_warnings", "Part of the file could not be read; packets after the damage are not listed."));
    }
    let filtered = want_proto.is_some() || want_ip.is_some() || p.port.is_some() || want_flow.is_some();
    let summary =
        format!("{matched} of {total} packets{} ; showing {shown} from #{}.", if filtered { " match the filter" } else { "" }, p.offset).replace(" ;", ";");
    let b = builder(ctx, "packets_fields_show", input.subject.clone(), params_json(&p))
        .result(json!({
            "path": input.path,
            "format": cap.format,
            "total_packets": total,
            "matched_packets": matched,
            "offset": p.offset,
            "limit": limit,
            "packets": rows,
            "warnings": cap.warnings,
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::EarlierRecord)
        .limitations(lims)
        .coverage(cov)
        .location(Location::new("path", input.path.display().to_string()));
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// tshark

/// tshark from Settings → Engines, the engine store or PATH, then Wireshark's standard folder.
fn find_tshark(ctx: &Ctx<'_>) -> Option<PathBuf> {
    let s = &ctx.session.settings;
    craft_anything_engines::locate("tshark", &s.engines.tools, &s.engine_store_dir()).or_else(|| {
        let mut c: Vec<PathBuf> =
            ["ProgramFiles", "ProgramFiles(x86)"].iter().filter_map(std::env::var_os).map(|r| PathBuf::from(r).join("Wireshark").join("tshark.exe")).collect();
        c.push(PathBuf::from("/Applications/Wireshark.app/Contents/MacOS/tshark"));
        c.into_iter().find(|p| cfg!(any(windows, target_os = "macos")) && p.is_file())
    })
}

fn tshark_version(ctx: &Ctx<'_>, exe: &PathBuf) -> Result<String, String> {
    let cancel = ctx.cancel.clone();
    match craft_anything_platform::Process::new(exe)
        .arg("--version")
        .timeout(Duration::from_secs(20))
        .stdout_cap(64 << 10)
        .stderr_cap(64 << 10)
        .cancel_when(move || cancel.is_cancelled())
        .label("tshark")
        .run()
    {
        Ok(o) if o.success => Ok(o.stdout_text().lines().map(str::trim).find(|l| !l.is_empty()).unwrap_or("").to_string()),
        Ok(o) => Err(format!("exited with {:?}: {}", o.code, o.stderr_text().lines().last().unwrap_or(""))),
        Err(e) => Err(e.message),
    }
}

fn engines_tshark_check(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let _p: ClientParams = parse_params(params)?;
    let found = find_tshark(ctx);
    let probe = found.as_ref().map(|exe| tshark_version(ctx, exe));
    let (version, error) = match probe {
        Some(Ok(v)) => (Some(v), None),
        Some(Err(e)) => (None, Some(e)),
        None => (None, None),
    };
    let available = version.is_some();
    let summary = match (&found, &version) {
        (Some(p), Some(v)) => format!("{v} is available at {}. packets_inventory_show will use it; the built-in decoder works without it.", p.display()),
        (Some(p), None) => format!("tshark was found at {} but did not report a version. The built-in decoder works without it.", p.display()),
        (None, _) => "Wireshark's tshark is not installed. That's fine: the packet tools use Craft Anything's built-in decoder.".into(),
    };
    let mut lims = Vec::new();
    if let Some(e) = &error {
        lims.push(Limitation::new("version_probe_failed", format!("tshark was found but `--version` failed: {e}")));
    }
    let b = builder(ctx, "engines_tshark_check", Subject { kind: "engine".into(), sha256: None, name: Some("tshark".into()) }, json!({}))
        .result(json!({
            "available": available, "path": found, "version": version, "error": error,
            "built_in_decoder": true,
            "remediation": if found.is_none() { Some("Optional: install Wireshark (it includes tshark) and, if it is not on PATH, set its path in Settings → Engines.") } else { None },
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OurRun)
        .limitations(lims)
        .coverage(Coverage::complete(1));
    Ok(ToolOutput::evidence(b.build()?))
}

/// The same inventories, whichever engine produced them.
#[derive(Debug, Default, Serialize)]
struct Inventories {
    packets: u64,
    protocol_stacks: Vec<Count>,
    endpoints: Vec<Count>,
    dns_queries: Vec<Count>,
    dns_answers: Vec<Count>,
    tls_sni: Vec<Count>,
    http_requests: Vec<Count>,
}

fn ranked(map: BTreeMap<String, u64>) -> Vec<Count> {
    let mut v: Vec<Count> = map.into_iter().map(|(value, count)| Count { value, count }).collect();
    v.sort_by(|a, b| b.count.cmp(&a.count).then_with(|| a.value.cmp(&b.value)));
    v
}

const TSHARK_FIELDS: &[&str] = &[
    "frame.protocols",
    "ip.src",
    "ip.dst",
    "ipv6.src",
    "ipv6.dst",
    "dns.flags.response",
    "dns.qry.name",
    "dns.qry.type",
    "dns.a",
    "dns.aaaa",
    "tls.handshake.extensions_server_name",
    "http.request.method",
    "http.host",
    "http.request.uri",
];

/// Aggregate `tshark -T fields` output (tab-separated, multi-values joined by commas).
fn aggregate_tshark(text: &str) -> Inventories {
    let mut inv = Inventories::default();
    let mut maps: [BTreeMap<String, u64>; 6] = Default::default();
    let mut add = |i: usize, k: String| {
        if let Some(m) = maps.get_mut(i)
            && (m.len() < pcap::MAX_INVENTORY || m.contains_key(&k))
        {
            *m.entry(k).or_insert(0) += 1;
        }
    };
    for line in text.lines() {
        inv.packets += 1;
        let f: Vec<&str> = line.split('\t').collect();
        let get = |i: usize| f.get(i).copied().unwrap_or("");
        let list = |i: usize| get(i).split(',').map(str::trim).filter(|s| !s.is_empty()).map(str::to_string).collect::<Vec<_>>();
        if !get(0).is_empty() {
            add(0, get(0).to_string());
        }
        let mut addrs: Vec<String> = (1..=4).flat_map(list).collect();
        addrs.sort();
        addrs.dedup();
        for a in addrs {
            add(1, a);
        }
        let response = matches!(get(5), "1" | "True" | "true");
        let names = list(6);
        let types = list(7);
        if !response {
            for (i, n) in names.iter().enumerate() {
                let t = types.get(i).and_then(|t| t.parse::<u16>().ok()).map(pcap::qtype_name).unwrap_or_else(|| "?".into());
                add(2, format!("{n} ({t})"));
            }
        } else if let Some(n) = names.first() {
            for a in list(8) {
                add(3, format!("{n} A {a}"));
            }
            for a in list(9) {
                add(3, format!("{n} AAAA {a}"));
            }
        }
        for s in list(10) {
            add(4, s);
        }
        if !get(11).is_empty() {
            add(5, format!("{} {} {}", get(11), if get(12).is_empty() { "-" } else { get(12) }, pcap::strip_userinfo(get(13))));
        }
    }
    let [stacks, endpoints, q, a, sni, http] = maps;
    inv.protocol_stacks = ranked(stacks);
    inv.endpoints = ranked(endpoints);
    inv.dns_queries = ranked(q);
    inv.dns_answers = ranked(a);
    inv.tls_sni = ranked(sni);
    inv.http_requests = ranked(http);
    inv
}

fn run_tshark(ctx: &Ctx<'_>, exe: &PathBuf, file: &std::path::Path) -> Result<(Inventories, bool), ToolError> {
    let mut args: Vec<String> = vec!["-n".into(), "-r".into(), file.display().to_string(), "-T".into(), "fields".into()];
    for opt in ["separator=/t", "occurrence=a", "aggregator=,", "header=n", "quote=n"] {
        args.extend(["-E".into(), opt.into()]);
    }
    for f in TSHARK_FIELDS {
        args.extend(["-e".into(), (*f).into()]);
    }
    let cancel = ctx.cancel.clone();
    let out = craft_anything_platform::Process::new(exe)
        .args(&args)
        .timeout(Duration::from_secs(300))
        .idle_timeout(Duration::from_secs(120))
        .stdout_cap(64 << 20)
        .stderr_cap(1 << 20)
        .cancel_when(move || cancel.is_cancelled())
        .label("tshark")
        .remediation("Check the capture opens in Wireshark, or use engine=built_in.")
        .run_checked()?;
    Ok((aggregate_tshark(&out.stdout_text()), out.stdout_truncated))
}

fn packets_inventory_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: InventoryParams = parse_params(params)?;
    let input = load(ctx, p.path.as_deref())?;
    let limit = p.limit.clamp(1, pcap::MAX_INVENTORY);
    let tshark = if p.engine == CaptureEngine::BuiltIn { None } else { find_tshark(ctx) };
    if p.engine == CaptureEngine::Tshark && tshark.is_none() {
        return Err(ToolError::new(ErrorCode::EngineMissing, "Wireshark's tshark is not installed.")
            .with_remediation("Install Wireshark and set tshark's path in Settings → Engines, or use engine=built_in."));
    }
    let mut lims = Vec::new();
    let (engine, inv) = match &tshark {
        Some(exe) => {
            ctx.report(None, format!("Running tshark on {}", input.name));
            let (inv, cut) = run_tshark(ctx, exe, &input.path)?;
            if cut {
                lims.push(Limitation::new("tshark_output_capped", "tshark printed more than 64 MiB; packets after that point are not counted."));
            }
            lims.push(Limitation::new("dns_answer_attribution", "DNS answer addresses are attributed to the first question of the same response."));
            ("tshark", inv)
        }
        None => {
            ctx.report(None, format!("Decoding {}", input.name));
            let cancel = ctx.cancel.clone();
            let s = pcap::summarize(&input.bytes, &|| cancel.is_cancelled()).map_err(|e| format_err(e, "a packet capture"))?;
            lims.extend(common_limitations());
            if !s.warnings.is_empty() {
                lims.push(Limitation::new("read_warnings", format!("Part of the file could not be read: {}", s.warnings.join("; "))));
            }
            let http: Vec<Count> = s.http_requests;
            let inv = Inventories {
                packets: s.packets,
                protocol_stacks: s.stacks,
                endpoints: s.endpoints,
                dns_queries: s.dns_queries,
                dns_answers: s.dns_answers,
                tls_sni: s.tls_sni,
                http_requests: http,
            };
            ("built-in", inv)
        }
    };
    ctx.cancel.check()?;
    lims.push(Limitation::new("no_credentials", "user:password parts of HTTP URIs are removed; query strings are kept as recorded."));
    let counts = json!({
        "protocol_stacks": inv.protocol_stacks.len(), "endpoints": inv.endpoints.len(), "dns_queries": inv.dns_queries.len(),
        "dns_answers": inv.dns_answers.len(), "tls_sni": inv.tls_sni.len(), "http_requests": inv.http_requests.len(),
    });
    let shown = |v: &[Count]| top(v, limit).to_vec();
    let summary = format!(
        "{} packets ({engine}): {} addresses, {} DNS questions, {} TLS server names, {} HTTP requests, {} protocol stacks.",
        inv.packets,
        inv.endpoints.len(),
        inv.dns_queries.len(),
        inv.tls_sni.len(),
        inv.http_requests.len(),
        inv.protocol_stacks.len()
    );
    let truncated =
        [&inv.protocol_stacks, &inv.endpoints, &inv.dns_queries, &inv.dns_answers, &inv.tls_sni, &inv.http_requests].iter().any(|v| v.len() > limit);
    let cov = if truncated { static_input::partial(inv.packets) } else { Coverage::complete(inv.packets) };
    let ev = builder(ctx, "packets_inventory_show", input.subject.clone(), params_json(&p))
        .result(json!({
            "path": input.path,
            "engine": engine,
            "tshark": tshark,
            "packets": inv.packets,
            "counts": counts,
            "limit": limit,
            "protocol_stacks": shown(&inv.protocol_stacks),
            "endpoints": shown(&inv.endpoints),
            "dns_queries": shown(&inv.dns_queries),
            "dns_answers": shown(&inv.dns_answers),
            "tls_sni": shown(&inv.tls_sni),
            "http_requests": shown(&inv.http_requests),
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::EarlierRecord)
        .limitations(lims)
        .coverage(cov)
        .location(Location::new("path", input.path.display().to_string()))
        .build()?;
    detailed(ctx, ev, p.detail, json!({"engine": engine, "counts": counts}))
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::{call, call_err};
    use super::aggregate_tshark;
    use crate::Engine;
    use craft_anything_testkit::pcap as fx;
    use craft_anything_testkit::temp_file;
    use serde_json::json;

    #[test]
    fn overview_and_fields() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("t.pcapng", &fx::pcapng(&fx::sample_frames()));
        let v = call(&e, "packets_capture_show", json!({"path": p, "limit": 2}));
        let r = &v["result"];
        assert_eq!(r["packets"], 7);
        assert_eq!(r["flow_count"], 3);
        assert_eq!(r["flows"].as_array().unwrap().len(), 2);
        assert_eq!(v["coverage"]["next_offset"], 2);
        assert_eq!(r["tls_sni"][0]["value"], "example.com");
        assert!(r["first_time"].as_str().unwrap().starts_with("2023-11-14T22:13:20"));

        let v = call(&e, "packets_fields_show", json!({"path": p, "protocol": "dns"}));
        assert_eq!(v["result"]["matched_packets"], 2);
        let pk = &v["result"]["packets"][1];
        assert_eq!(pk["frame"], 2);
        assert_eq!(pk["protocols"], "eth:ipv4:udp:dns");
        assert_eq!(pk["src"], "8.8.8.8:53");
        assert_eq!(pk["flow"], 1);
        assert_eq!(pk["dns"]["answers"][0]["value"], "93.184.216.34");

        let v = call(&e, "packets_fields_show", json!({"path": p, "flow": "f2", "limit": 1, "offset": 1}));
        assert_eq!(v["result"]["matched_packets"], 3);
        assert_eq!(v["result"]["packets"][0]["transport"]["tcp_flags"], "SYN,ACK");
        let v = call(&e, "packets_fields_show", json!({"path": p, "ip": "93.184.216.34", "port": 80}));
        assert_eq!(v["result"]["packets"][0]["http"]["host"], "example.com");
        call_err(&e, "packets_fields_show", json!({"path": p, "ip": "not-an-ip"}));
        call_err(&e, "packets_capture_show", json!({"path": temp_file("x.bin", b"nope")}));
    }

    #[test]
    fn built_in_inventories() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("t.pcap", &fx::pcap(&fx::sample_frames()));
        let v = call(&e, "packets_inventory_show", json!({"path": p, "engine": "built_in"}));
        let r = &v["result"];
        assert_eq!(r["engine"], "built-in");
        assert_eq!(r["packets"], 7);
        assert_eq!(r["dns_queries"][0]["value"], "example.com (A)");
        assert_eq!(r["http_requests"][0]["value"], "GET example.com http://example.com/a?b=1");
        let v = call(&e, "engines_tshark_check", json!({}));
        assert!(v["result"]["available"].is_boolean());
    }

    #[test]
    fn tshark_output_aggregation() {
        let out = "eth:ethertype:ip:udp:dns\t10.0.0.1\t8.8.8.8\t\t\t0\texample.com\t1\t\t\t\t\t\t\n\
                   eth:ethertype:ip:udp:dns\t8.8.8.8\t10.0.0.1\t\t\t1\texample.com\t1\t93.184.216.34,93.184.216.35\t\t\t\t\t\n\
                   eth:ethertype:ip:tcp:http\t10.0.0.1\t1.2.3.4\t\t\t\t\t\t\t\t\tGET\th.example\thttp://u:p@h.example/x\n";
        let inv = aggregate_tshark(out);
        assert_eq!(inv.packets, 3);
        assert_eq!(inv.dns_queries[0].value, "example.com (A)");
        assert_eq!(inv.dns_answers.len(), 2);
        assert_eq!(inv.http_requests[0].value, "GET h.example http://h.example/x");
        assert_eq!(inv.endpoints[0].value, "10.0.0.1");
        assert_eq!(inv.endpoints[0].count, 3);
    }
}
