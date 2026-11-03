//! HTTP plumbing: one ureq agent (rustls), JSON POST with streamed responses, and an SSE parser.

use craft_anything_evidence::{ErrorCode, ToolError};
use serde_json::Value;
use std::io::{BufRead, BufReader, Read};
use std::time::Duration;

/// Generic, non-identifying User-Agent.
pub const USER_AGENT: &str = "CraftAnything-dev";

/// An agent for model calls: generous body time (streams can run for many minutes), bounded
/// connect and first-byte waits.
pub fn agent(connect: Duration, first_byte: Duration, body: Duration) -> ureq::Agent {
    ureq::Agent::config_builder()
        .http_status_as_error(false)
        .user_agent(USER_AGENT)
        .timeout_connect(Some(connect))
        .timeout_recv_response(Some(first_byte))
        .timeout_recv_body(Some(body))
        .build()
        .new_agent()
}

/// The agent for streamed model turns.
pub fn stream_agent() -> ureq::Agent {
    agent(Duration::from_secs(15), Duration::from_secs(300), Duration::from_secs(60 * 60))
}

/// The agent for quick calls (model lists, probes).
pub fn quick_agent(total: Duration) -> ureq::Agent {
    agent(total, total, total)
}

fn net_error(what: &str, e: ureq::Error) -> ToolError {
    let timeout = matches!(e, ureq::Error::Timeout(_));
    let code = if timeout { ErrorCode::TimedOut } else { ErrorCode::EngineMissing };
    ToolError::new(code, format!("Couldn't reach {what}: {e}"))
        .with_remediation("Check your internet connection or that the server is running, then try again.")
}

/// Turn a non-2xx response into a plain error. Keys are never echoed.
pub fn status_error(what: &str, status: u16, body: &str) -> ToolError {
    let detail: String = serde_json::from_str::<Value>(body)
        .ok()
        .and_then(|v| {
            v.pointer("/error/message").and_then(Value::as_str).map(str::to_string).or_else(|| v.get("error").and_then(Value::as_str).map(str::to_string))
        })
        .unwrap_or_else(|| body.chars().take(300).collect());
    let (code, remediation) = match status {
        401 | 403 => (ErrorCode::NoPermission, "The API key was rejected. Check it in Settings → AI."),
        404 => (ErrorCode::BadSettings, "The model or address wasn't found. Check the model name and base URL."),
        408 | 504 => (ErrorCode::TimedOut, "The service took too long. Try again."),
        429 => (ErrorCode::OverLimit, "You've hit a rate or spending limit. Wait a moment or check your plan."),
        500..=599 => (ErrorCode::EngineMissing, "The service is having trouble. Try again soon, or use another backend."),
        _ => (ErrorCode::BadInput, "The request was rejected; see the message."),
    };
    ToolError::new(code, format!("{what} answered {status}: {detail}")).with_remediation(remediation).with_details(serde_json::json!({"status": status}))
}

/// POST JSON and return a reader over the (streamed) body; errors on non-2xx.
pub fn post_json(agent: &ureq::Agent, what: &str, url: &str, headers: &[(&str, String)], body: &Value) -> Result<Box<dyn Read + Send>, ToolError> {
    let mut req = agent.post(url).header("content-type", "application/json");
    for (k, v) in headers {
        req = req.header(*k, v.as_str());
    }
    let resp = req.send(body.to_string()).map_err(|e| net_error(what, e))?;
    let status = resp.status().as_u16();
    if !(200..300).contains(&status) {
        let text = resp.into_body().read_to_string().unwrap_or_default();
        return Err(status_error(what, status, &text));
    }
    Ok(Box::new(resp.into_body().into_reader()))
}

/// GET JSON.
pub fn get_json(agent: &ureq::Agent, what: &str, url: &str, headers: &[(&str, String)]) -> Result<Value, ToolError> {
    let mut req = agent.get(url);
    for (k, v) in headers {
        req = req.header(*k, v.as_str());
    }
    let resp = req.call().map_err(|e| net_error(what, e))?;
    let status = resp.status().as_u16();
    let text = resp.into_body().read_to_string().map_err(|e| net_error(what, e))?;
    if !(200..300).contains(&status) {
        return Err(status_error(what, status, &text));
    }
    serde_json::from_str(&text).map_err(|e| ToolError::new(ErrorCode::GarbledOutput, format!("{what} sent JSON we couldn't read: {e}")))
}

/// One server-sent event.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SseEvent {
    pub event: Option<String>,
    pub data: String,
}

/// Longest single SSE line we accept (protects memory against a hostile server).
const MAX_SSE_LINE: usize = 8 * 1024 * 1024;

/// Parse an SSE stream, calling `f` for each event. `f` returns false to stop early.
/// Handles CRLF, multi-line `data:`, comments (`:`), and a final event without a blank line.
pub fn parse_sse<R: Read>(r: R, mut f: impl FnMut(SseEvent) -> Result<bool, ToolError>) -> Result<(), ToolError> {
    let mut reader = BufReader::new(r);
    let mut cur = SseEvent::default();
    let mut has_data = false;
    let mut line = Vec::new();
    loop {
        line.clear();
        let n = (&mut reader)
            .take(MAX_SSE_LINE as u64)
            .read_until(b'\n', &mut line)
            .map_err(|e| ToolError::new(ErrorCode::EngineMissing, format!("The stream broke off: {e}")))?;
        if n == 0 {
            break;
        }
        if line.last() != Some(&b'\n') && line.len() >= MAX_SSE_LINE {
            return Err(ToolError::new(ErrorCode::OverLimit, "The stream sent a line that was too long."));
        }
        let text = String::from_utf8_lossy(&line);
        let l = text.trim_end_matches(['\n', '\r']);
        if l.is_empty() {
            if has_data || cur.event.is_some() {
                let ev = std::mem::take(&mut cur);
                has_data = false;
                if !f(ev)? {
                    return Ok(());
                }
            }
            continue;
        }
        if l.starts_with(':') {
            continue;
        }
        let (field, value) = match l.split_once(':') {
            Some((k, v)) => (k, v.strip_prefix(' ').unwrap_or(v)),
            None => (l, ""),
        };
        match field {
            "event" => cur.event = Some(value.to_string()),
            "data" => {
                if has_data {
                    cur.data.push('\n');
                }
                cur.data.push_str(value);
                has_data = true;
            }
            _ => {}
        }
    }
    if has_data {
        f(cur)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn collect(s: &str) -> Vec<SseEvent> {
        let mut v = Vec::new();
        parse_sse(s.as_bytes(), |e| {
            v.push(e);
            Ok(true)
        })
        .unwrap();
        v
    }

    #[test]
    fn sse_edge_cases() {
        let evs = collect(": comment\r\nevent: a\r\ndata: 1\r\ndata: 2\r\n\r\ndata:x\n\n\n\ndata: tail");
        assert_eq!(evs.len(), 3);
        assert_eq!(evs[0], SseEvent { event: Some("a".into()), data: "1\n2".into() });
        assert_eq!(evs[1].data, "x");
        assert_eq!(evs[2].data, "tail");
    }

    #[test]
    fn early_stop() {
        let mut n = 0;
        parse_sse("data: 1\n\ndata: 2\n\n".as_bytes(), |_| {
            n += 1;
            Ok(false)
        })
        .unwrap();
        assert_eq!(n, 1);
    }

    #[test]
    fn status_errors_are_plain() {
        let e = status_error("Anthropic", 401, r#"{"error":{"message":"invalid x-api-key"}}"#);
        assert_eq!(e.code, ErrorCode::NoPermission);
        assert!(e.message.contains("invalid x-api-key"));
        assert_eq!(status_error("x", 429, "slow down").code, ErrorCode::OverLimit);
    }
}
