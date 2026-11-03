//! Anthropic Messages API: streaming SSE, tools, adaptive thinking, effort, prompt caching and
//! server-side fallbacks.

use crate::http::{self, SseEvent};
use crate::model::{Block, ChatModel, Delta, Effort, Msg, Speaker, Stop, StopReason, ToolDef, TurnRequest, TurnResult, Usage};
use craft_anything_evidence::{ErrorCode, ToolError};
use serde_json::{Value, json};

pub const DEFAULT_BASE: &str = "https://api.anthropic.com";
pub const DEFAULT_MODEL: &str = "claude-opus-5-5";
/// Offered in the model dropdown when the live list can't be fetched.
pub const MODELS: &[&str] = &["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1"];
/// Models that offer fewer effort levels than all five (Claude's effort guide), by model id
/// prefix; any other model is sent the level as chosen.
pub const EFFORT_LEVELS: &[(&str, &[Effort])] = &[
    ("claude-opus-4-6", &[Effort::Low, Effort::Medium, Effort::High, Effort::Max]),
    ("claude-sonnet-4-6", &[Effort::Low, Effort::Medium, Effort::High, Effort::Max]),
    ("claude-opus-4-5", &[Effort::Low, Effort::Medium, Effort::High]),
];

/// The effort level `model` is sent: `effort`, or the nearest level below it the model has.
pub fn effort_for(model: &str, effort: Effort) -> Effort {
    let model = model.trim().trim_start_matches("anthropic/").trim_start_matches("anthropic.");
    EFFORT_LEVELS.iter().find(|(prefix, _)| model.starts_with(prefix)).map_or(effort, |(_, levels)| effort.within(levels))
}
pub const API_VERSION: &str = "2023-06-01";
pub const FALLBACK_BETA: &str = "server-side-fallback-2026-07-01";
pub const MAX_TOKENS: u32 = 64_000;

/// Most content blocks we track in one response.
const MAX_BLOCKS: usize = 4096;

#[derive(Debug, Clone)]
pub struct Anthropic {
    pub base_url: String,
    pub api_key: String,
    pub model: String,
    /// Send the server-side fallback header and body field.
    pub fallbacks: bool,
}

impl Anthropic {
    pub fn new(base_url: Option<&str>, api_key: String, model: &str) -> Self {
        Anthropic {
            base_url: base_url.unwrap_or(DEFAULT_BASE).trim_end_matches('/').to_string(),
            api_key,
            model: if model.is_empty() { DEFAULT_MODEL.to_string() } else { model.to_string() },
            fallbacks: true,
        }
    }

    fn url(&self, path: &str) -> String {
        let base = self.base_url.trim_end_matches("/v1");
        format!("{base}/v1/{path}")
    }

    pub fn headers(&self) -> Vec<(&'static str, String)> {
        let mut h = vec![("x-api-key", self.api_key.clone()), ("anthropic-version", API_VERSION.to_string())];
        if self.fallbacks {
            h.push(("anthropic-beta", FALLBACK_BETA.to_string()));
        }
        h
    }

    /// The request body for one streamed turn.
    pub fn body(&self, req: &TurnRequest<'_>) -> Value {
        let mut body = json!({
            "model": self.model,
            "max_tokens": req.max_tokens,
            "stream": true,
            "system": [{"type": "text", "text": req.system, "cache_control": {"type": "ephemeral"}}],
            "messages": req.messages.iter().map(message_json).collect::<Vec<_>>(),
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": effort_for(&self.model, req.effort).as_str()},
        });
        if !req.tools.is_empty() {
            let n = req.tools.len();
            let tools: Vec<Value> = req
                .tools
                .iter()
                .enumerate()
                .map(|(i, t)| {
                    let mut v = json!({"name": t.name, "description": t.description, "input_schema": t.schema, "eager_input_streaming": true});
                    if i + 1 == n
                        && let Some(m) = v.as_object_mut()
                    {
                        m.insert("cache_control".into(), json!({"type": "ephemeral"}));
                    }
                    v
                })
                .collect();
            if let Some(m) = body.as_object_mut() {
                m.insert("tools".into(), Value::Array(tools));
                m.insert("tool_choice".into(), json!({"type": "auto"}));
            }
        }
        if self.fallbacks
            && let Some(m) = body.as_object_mut()
        {
            m.insert("fallbacks".into(), json!("default"));
        }
        body
    }

    /// Model ids available to this key.
    pub fn list_models(&self, timeout: std::time::Duration) -> Result<Vec<String>, ToolError> {
        let agent = http::quick_agent(timeout);
        let v = http::get_json(&agent, "Anthropic", &self.url("models"), &self.headers())?;
        Ok(v.get("data")
            .and_then(Value::as_array)
            .map(|a| a.iter().filter_map(|m| m.get("id").and_then(Value::as_str).map(str::to_string)).collect())
            .unwrap_or_default())
    }
}

pub fn message_json(m: &Msg) -> Value {
    let role = match m.role {
        Speaker::User => "user",
        Speaker::Assistant => "assistant",
    };
    let content: Vec<Value> = m
        .blocks
        .iter()
        .map(|b| match b {
            Block::Text { text } => json!({"type": "text", "text": text}),
            Block::Thinking { thinking, signature } => json!({"type": "thinking", "thinking": thinking, "signature": signature}),
            Block::RedactedThinking { data } => json!({"type": "redacted_thinking", "data": data}),
            Block::ToolUse { id, name, input } => json!({"type": "tool_use", "id": id, "name": name, "input": input}),
            Block::ToolResult { tool_use_id, content, is_error } => {
                json!({"type": "tool_result", "tool_use_id": tool_use_id, "content": content, "is_error": is_error})
            }
        })
        .collect();
    json!({"role": role, "content": content})
}

#[derive(Debug, Default)]
enum Partial {
    #[default]
    Empty,
    Text(String),
    Thinking(String, String),
    Redacted(String),
    Tool {
        id: String,
        name: String,
        json: String,
    },
}

/// Accumulates one streamed response.
#[derive(Debug, Default)]
pub struct StreamState {
    blocks: Vec<Partial>,
    pub usage: Usage,
    pub stop: Option<StopReason>,
    pub model: String,
    pub done: bool,
}

impl StreamState {
    fn slot(&mut self, index: usize) -> Option<&mut Partial> {
        if index >= MAX_BLOCKS {
            return None;
        }
        if self.blocks.len() <= index {
            self.blocks.resize_with(index + 1, Partial::default);
        }
        self.blocks.get_mut(index)
    }

    /// Apply one SSE event.
    pub fn apply(&mut self, ev: &SseEvent, on_delta: &mut dyn FnMut(Delta)) -> Result<(), ToolError> {
        if ev.data.is_empty() {
            return Ok(());
        }
        let v: Value =
            serde_json::from_str(&ev.data).map_err(|e| ToolError::new(ErrorCode::GarbledOutput, format!("Anthropic sent an event we couldn't read: {e}")))?;
        let kind = v.get("type").and_then(Value::as_str).or(ev.event.as_deref()).unwrap_or_default();
        let index = v.get("index").and_then(Value::as_u64).and_then(|i| usize::try_from(i).ok()).unwrap_or(0);
        match kind {
            "message_start" => {
                let m = v.get("message").cloned().unwrap_or(Value::Null);
                self.model = m.get("model").and_then(Value::as_str).unwrap_or_default().to_string();
                if let Some(u) = m.get("usage") {
                    self.read_usage(u);
                }
            }
            "content_block_start" => {
                let b = v.get("content_block").cloned().unwrap_or(Value::Null);
                let s = |k: &str| b.get(k).and_then(Value::as_str).unwrap_or_default().to_string();
                let p = match b.get("type").and_then(Value::as_str).unwrap_or_default() {
                    "text" => Partial::Text(s("text")),
                    "thinking" => Partial::Thinking(s("thinking"), s("signature")),
                    "redacted_thinking" => Partial::Redacted(s("data")),
                    "tool_use" | "server_tool_use" => Partial::Tool { id: s("id"), name: s("name"), json: String::new() },
                    _ => Partial::Empty,
                };
                if !s("text").is_empty() {
                    on_delta(Delta::Text(s("text")));
                }
                if let Some(slot) = self.slot(index) {
                    *slot = p;
                }
            }
            "content_block_delta" => {
                let d = v.get("delta").cloned().unwrap_or(Value::Null);
                let s = |k: &str| d.get(k).and_then(Value::as_str).unwrap_or_default().to_string();
                let dtype = d.get("type").and_then(Value::as_str).unwrap_or_default().to_string();
                let Some(slot) = self.slot(index) else { return Ok(()) };
                match (dtype.as_str(), slot) {
                    ("text_delta", Partial::Text(t)) => {
                        let piece = s("text");
                        t.push_str(&piece);
                        on_delta(Delta::Text(piece));
                    }
                    ("text_delta", slot @ Partial::Empty) => {
                        let piece = s("text");
                        *slot = Partial::Text(piece.clone());
                        on_delta(Delta::Text(piece));
                    }
                    ("thinking_delta", Partial::Thinking(t, _)) => {
                        let piece = s("thinking");
                        t.push_str(&piece);
                        on_delta(Delta::Thinking(piece));
                    }
                    ("signature_delta", Partial::Thinking(_, sig)) => sig.push_str(&s("signature")),
                    ("input_json_delta", Partial::Tool { json, .. }) => {
                        json.push_str(&s("partial_json"));
                        if json.len() > 4 * 1024 * 1024 {
                            return Err(ToolError::new(ErrorCode::OverLimit, "The model sent oversized tool input."));
                        }
                    }
                    _ => {}
                }
            }
            "content_block_stop" | "ping" => {}
            "message_delta" => {
                if let Some(r) = v.pointer("/delta/stop_reason").and_then(Value::as_str) {
                    self.stop = Some(StopReason::parse(r));
                }
                if let Some(u) = v.get("usage") {
                    self.read_usage(u);
                }
            }
            "message_stop" => self.done = true,
            "error" => {
                let et = v.pointer("/error/type").and_then(Value::as_str).unwrap_or("error");
                let msg = v.pointer("/error/message").and_then(Value::as_str).unwrap_or("unknown error");
                let code = match et {
                    "overloaded_error" | "api_error" => ErrorCode::EngineMissing,
                    "rate_limit_error" => ErrorCode::OverLimit,
                    "authentication_error" | "permission_error" => ErrorCode::NoPermission,
                    _ => ErrorCode::ProgramFailed,
                };
                return Err(
                    ToolError::new(code, format!("Anthropic stream error ({et}): {msg}")).with_remediation("Try again; if it keeps happening, switch backend.")
                );
            }
            _ => {}
        }
        Ok(())
    }

    fn read_usage(&mut self, u: &Value) {
        let g = |k: &str| u.get(k).and_then(Value::as_u64);
        if let Some(n) = g("input_tokens") {
            self.usage.input_tokens = n;
        }
        if let Some(n) = g("output_tokens") {
            self.usage.output_tokens = n;
        }
        if let Some(n) = g("cache_read_input_tokens") {
            self.usage.cache_read_tokens = n;
        }
        if let Some(n) = g("cache_creation_input_tokens") {
            self.usage.cache_write_tokens = n;
        }
    }

    /// The finished assistant message.
    pub fn finish(self, fallback_model: &str) -> Result<TurnResult, ToolError> {
        let mut blocks = Vec::new();
        for p in self.blocks {
            match p {
                Partial::Empty => {}
                Partial::Text(t) => blocks.push(Block::Text { text: t }),
                Partial::Thinking(t, s) => blocks.push(Block::Thinking { thinking: t, signature: s }),
                Partial::Redacted(d) => blocks.push(Block::RedactedThinking { data: d }),
                Partial::Tool { id, name, json } => {
                    // Eagerly streamed input is not validated by the server: a truncated or
                    // malformed object becomes a marked input the agent loop answers with an error.
                    let input = if json.trim().is_empty() { json!({}) } else { serde_json::from_str(&json).unwrap_or_else(|_| invalid_input(&json)) };
                    blocks.push(Block::ToolUse { id, name, input });
                }
            }
        }
        let stop = match self.stop {
            Some(s) => s,
            None if self.done => StopReason::EndTurn,
            None => return Err(ToolError::new(ErrorCode::Truncated, "The answer stream ended early.").with_remediation("Try again.")),
        };
        let model = if self.model.is_empty() { fallback_model.to_string() } else { self.model };
        Ok(TurnResult { message: Msg { role: Speaker::Assistant, blocks }, stop, usage: self.usage, model })
    }
}

impl ChatModel for Anthropic {
    fn turn(&mut self, req: &TurnRequest<'_>, on_delta: &mut dyn FnMut(Delta), stop: &Stop) -> Result<TurnResult, ToolError> {
        let agent = http::stream_agent();
        let reader = http::post_json(&agent, "Anthropic", &self.url("messages"), &self.headers(), &self.body(req))?;
        let mut state = StreamState::default();
        http::parse_sse(reader, |ev| {
            stop.check()?;
            state.apply(&ev, on_delta)?;
            Ok(!state.done)
        })?;
        stop.check()?;
        state.finish(&self.model)
    }

    fn model(&self) -> String {
        self.model.clone()
    }
}

/// Marker for tool input that wasn't valid JSON.
pub const INVALID_INPUT_KEY: &str = "__invalid_json_input";

pub fn invalid_input(raw: &str) -> Value {
    json!({ INVALID_INPUT_KEY: raw.chars().take(200).collect::<String>() })
}

/// Tool definitions sorted by name so the cached prefix stays identical between requests.
pub fn sorted(mut tools: Vec<ToolDef>) -> Vec<ToolDef> {
    tools.sort_by(|a, b| a.name.cmp(&b.name));
    tools
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::Effort;

    #[test]
    fn body_has_required_fields() {
        let a = Anthropic::new(None, "k".into(), "");
        let msgs = vec![Msg::user_text("hi")];
        let tools = vec![
            ToolDef { name: "a".into(), description: "d".into(), schema: json!({"type": "object"}) },
            ToolDef { name: "b".into(), description: "d".into(), schema: json!({"type": "object"}) },
        ];
        let b = a.body(&TurnRequest { system: "sys", messages: &msgs, tools: &tools, effort: Effort::High, max_tokens: MAX_TOKENS });
        assert_eq!(b["model"], "claude-opus-5-5");
        assert_eq!(b["thinking"]["type"], "adaptive");
        assert_eq!(b["output_config"]["effort"], "high");
        assert_eq!(b["tool_choice"]["type"], "auto");
        assert_eq!(b["fallbacks"], "default");
        assert_eq!(b["max_tokens"], 64000);
        assert!(b["tools"][0].get("cache_control").is_none());
        assert_eq!(b["tools"][1]["cache_control"]["type"], "ephemeral");
        assert_eq!(b["system"][0]["cache_control"]["type"], "ephemeral");
        assert!(a.headers().iter().any(|(k, v)| *k == "anthropic-beta" && v == FALLBACK_BETA));
        let mut off = a.clone();
        off.fallbacks = false;
        assert!(off.body(&TurnRequest { system: "s", messages: &msgs, tools: &[], effort: Effort::Low, max_tokens: 10 }).get("fallbacks").is_none());
        assert!(off.headers().iter().all(|(k, _)| *k != "anthropic-beta"));
    }

    /// Every level goes to a model that has it; one that lacks it gets the nearest level below.
    #[test]
    fn effort_steps_down_to_a_level_the_model_has() {
        for e in Effort::ALL {
            assert_eq!(effort_for("claude-opus-5-5", e), e);
            assert_eq!(Effort::parse(&e.as_str().to_uppercase()), Some(e));
        }
        assert_eq!(effort_for("claude-sonnet-4-6", Effort::Xhigh), Effort::High);
        assert_eq!(effort_for("anthropic/claude-opus-4-6", Effort::Max), Effort::Max);
        assert_eq!(effort_for("claude-opus-4-5-20251101", Effort::Max), Effort::High);
        assert_eq!(Effort::Low.within(&[Effort::Medium, Effort::High]), Effort::Medium, "none below: the lowest it has");
        assert_eq!(Effort::Max.within(&[]), Effort::Max);
        assert_eq!(Effort::parse("extreme"), None);
        let a = Anthropic::new(None, "k".into(), "claude-sonnet-4-6");
        let b = a.body(&TurnRequest { system: "s", messages: &[], tools: &[], effort: Effort::Xhigh, max_tokens: 10 });
        assert_eq!(b["output_config"]["effort"], "high");
    }

    #[test]
    fn stream_state_builds_blocks() {
        let events = [
            json!({"type":"message_start","message":{"model":"claude-opus-5-5","usage":{"input_tokens":10,"cache_read_input_tokens":4}}}),
            json!({"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":""}}),
            json!({"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"hmm"}}),
            json!({"type":"content_block_delta","index":0,"delta":{"type":"signature_delta","signature":"sig"}}),
            json!({"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"t1","name":"x","input":{}}}),
            json!({"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\"a\":"}}),
            json!({"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"1}"}}),
            json!({"type":"content_block_stop","index":1}),
            json!({"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":7}}),
            json!({"type":"message_stop"}),
        ];
        let mut st = StreamState::default();
        let mut thinking = String::new();
        for e in events {
            st.apply(&SseEvent { event: None, data: e.to_string() }, &mut |d| {
                if let Delta::Thinking(t) = d {
                    thinking.push_str(&t)
                }
            })
            .unwrap();
        }
        let r = st.finish("m").unwrap();
        assert_eq!(thinking, "hmm");
        assert_eq!(r.stop, StopReason::ToolUse);
        assert_eq!(r.usage, Usage { input_tokens: 10, output_tokens: 7, cache_read_tokens: 4, cache_write_tokens: 0 });
        assert_eq!(r.message.blocks[0], Block::Thinking { thinking: "hmm".into(), signature: "sig".into() });
        assert_eq!(r.message.tool_uses(), vec![("t1".into(), "x".into(), json!({"a": 1}))]);
    }

    #[test]
    fn stream_errors_and_truncation() {
        let mut st = StreamState::default();
        let e = st
            .apply(
                &SseEvent { event: Some("error".into()), data: json!({"type":"error","error":{"type":"overloaded_error","message":"busy"}}).to_string() },
                &mut |_| {},
            )
            .unwrap_err();
        assert_eq!(e.code, ErrorCode::EngineMissing);
        let st = StreamState::default();
        assert_eq!(st.finish("m").unwrap_err().code, ErrorCode::Truncated);
        let mut st = StreamState::default();
        assert!(st.apply(&SseEvent { event: None, data: "{not json".into() }, &mut |_| {}).is_err());
        // indexes far out of range are ignored, not allocated
        st.apply(
            &SseEvent { event: None, data: json!({"type":"content_block_start","index":999999999,"content_block":{"type":"text","text":""}}).to_string() },
            &mut |_| {},
        )
        .unwrap();
    }
}
