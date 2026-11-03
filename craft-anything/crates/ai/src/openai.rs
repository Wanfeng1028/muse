//! OpenAI chat completions (and every OpenAI-compatible server: OpenRouter, Ollama, LM Studio,
//! llama.cpp, vLLM…): streaming, function tools, and a ReAct text fallback for models without
//! tool calling.

use crate::http::{self, SseEvent};
use crate::model::{Block, ChatModel, Delta, Msg, Speaker, Stop, StopReason, ToolDef, TurnRequest, TurnResult, Usage};
use craft_anything_evidence::{ErrorCode, ToolError};
use serde_json::{Value, json};
use std::collections::BTreeMap;

pub const OPENAI_BASE: &str = "https://api.openai.com/v1";
pub const OPENROUTER_BASE: &str = "https://openrouter.ai/api/v1";
pub const OPENAI_DEFAULT_MODEL: &str = "gpt-5";
pub const OPENROUTER_DEFAULT_MODEL: &str = "anthropic/claude-opus-5-5";
/// Kimi K3 (Moonshot AI) on OpenRouter: 1M-token context, tool calls.
pub const KIMI_K3: &str = "moonshotai/kimi-k3";
/// OpenRouter models offered when adding it.
pub const OPENROUTER_MODELS: &[&str] = &[OPENROUTER_DEFAULT_MODEL, KIMI_K3];
/// Generic app identification for OpenRouter (no personal data).
pub const APP_REFERER: &str = "https://github.com/storytold/craft-anything";
pub const APP_TITLE: &str = "Craft Anything";

/// Well-known local servers: (name, base URL).
pub const LOCAL_SERVERS: &[(&str, &str)] = &[
    ("Ollama", "http://127.0.0.1:11434/v1"),
    ("LM Studio", "http://127.0.0.1:1234/v1"),
    ("llama.cpp server", "http://127.0.0.1:8080/v1"),
    ("vLLM", "http://127.0.0.1:8000/v1"),
];

#[derive(Debug, Clone)]
pub struct OpenAi {
    /// For messages ("OpenAI", "OpenRouter", "Ollama"…).
    pub label: String,
    pub base_url: String,
    pub api_key: Option<String>,
    pub model: String,
    pub extra_headers: Vec<(&'static str, String)>,
    /// Use the ReAct text protocol instead of function tools.
    pub react: bool,
    /// Switch to ReAct automatically when the server rejects tools.
    pub auto_react: bool,
}

impl OpenAi {
    pub fn official(base: Option<&str>, key: String, model: &str) -> Self {
        Self::compatible("OpenAI", base.unwrap_or(OPENAI_BASE), Some(key), if model.is_empty() { OPENAI_DEFAULT_MODEL } else { model })
    }

    pub fn openrouter(base: Option<&str>, key: String, model: &str) -> Self {
        let mut o = Self::compatible("OpenRouter", base.unwrap_or(OPENROUTER_BASE), Some(key), if model.is_empty() { OPENROUTER_DEFAULT_MODEL } else { model });
        o.extra_headers = vec![("HTTP-Referer", APP_REFERER.to_string()), ("X-Title", APP_TITLE.to_string())];
        o
    }

    pub fn compatible(label: &str, base: &str, key: Option<String>, model: &str) -> Self {
        OpenAi {
            label: label.to_string(),
            base_url: base.trim_end_matches('/').to_string(),
            api_key: key.filter(|k| !k.is_empty()),
            model: model.to_string(),
            extra_headers: Vec::new(),
            react: false,
            auto_react: true,
        }
    }

    fn url(&self, path: &str) -> String {
        format!("{}/{path}", self.base_url)
    }

    pub fn headers(&self) -> Vec<(&'static str, String)> {
        let mut h = self.extra_headers.clone();
        if let Some(k) = &self.api_key {
            h.push(("authorization", format!("Bearer {k}")));
        }
        h
    }

    pub fn body(&self, req: &TurnRequest<'_>) -> Value {
        let mut system = req.system.to_string();
        if self.react && !req.tools.is_empty() {
            system.push_str(&react_instructions(req.tools));
        }
        let mut messages = vec![json!({"role": "system", "content": system})];
        for m in req.messages {
            messages.extend(messages_json(m, self.react));
        }
        let mut body = json!({
            "model": self.model,
            "stream": true,
            "stream_options": {"include_usage": true},
            "messages": messages,
        });
        if !self.react
            && !req.tools.is_empty()
            && let Some(o) = body.as_object_mut()
        {
            let tools: Vec<Value> = req
                .tools
                .iter()
                .map(|t| json!({"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.schema}}))
                .collect();
            o.insert("tools".into(), Value::Array(tools));
            o.insert("tool_choice".into(), json!("auto"));
        }
        body
    }

    /// Model ids from `GET /models`.
    pub fn list_models(&self, timeout: std::time::Duration) -> Result<Vec<String>, ToolError> {
        let agent = http::quick_agent(timeout);
        let v = http::get_json(&agent, &self.label, &self.url("models"), &self.headers())?;
        let arr = v.get("data").or_else(|| v.get("models")).and_then(Value::as_array).cloned().unwrap_or_default();
        Ok(arr.iter().filter_map(|m| m.get("id").or_else(|| m.get("name")).and_then(Value::as_str).map(str::to_string)).collect())
    }

    fn stream_once(&self, req: &TurnRequest<'_>, on_delta: &mut dyn FnMut(Delta), stop: &Stop) -> Result<TurnResult, ToolError> {
        let agent = http::stream_agent();
        let reader = http::post_json(&agent, &self.label, &self.url("chat/completions"), &self.headers(), &self.body(req))?;
        let mut st = ChatStream::default();
        http::parse_sse(reader, |ev| {
            stop.check()?;
            st.apply(&ev, on_delta)?;
            Ok(!st.done)
        })?;
        stop.check()?;
        let mut r = st.finish(&self.model)?;
        if self.react {
            react_postprocess(&mut r);
        }
        Ok(r)
    }
}

fn rejects_tools(e: &ToolError) -> bool {
    let m = e.message.to_ascii_lowercase();
    let status = e.details.as_ref().and_then(|d| d.get("status")).and_then(Value::as_u64).unwrap_or(0);
    (status == 400 || status == 422 || status == 500 || status == 404) && (m.contains("tool") || m.contains("function"))
}

impl ChatModel for OpenAi {
    fn turn(&mut self, req: &TurnRequest<'_>, on_delta: &mut dyn FnMut(Delta), stop: &Stop) -> Result<TurnResult, ToolError> {
        match self.stream_once(req, on_delta, stop) {
            Err(e) if !self.react && self.auto_react && !req.tools.is_empty() && rejects_tools(&e) => {
                log::info!("{} rejected tool calling; switching to the text protocol", self.label);
                self.react = true;
                self.stream_once(req, on_delta, stop)
            }
            other => other,
        }
    }

    fn model(&self) -> String {
        self.model.clone()
    }
}

/// Wire messages for one neutral message (a user message with several tool results becomes
/// several `tool` messages).
pub fn messages_json(m: &Msg, react: bool) -> Vec<Value> {
    match m.role {
        Speaker::User => {
            let mut out = Vec::new();
            let mut text = String::new();
            for b in &m.blocks {
                match b {
                    Block::Text { text: t } => text.push_str(t),
                    Block::ToolResult { tool_use_id, content, is_error } => {
                        if react {
                            let tag = if *is_error { "Observation (error)" } else { "Observation" };
                            text.push_str(&format!("{tag}: {content}\n"));
                        } else {
                            out.push(json!({"role": "tool", "tool_call_id": tool_use_id, "content": content}));
                        }
                    }
                    _ => {}
                }
            }
            if !text.is_empty() {
                out.push(json!({"role": "user", "content": text}));
            }
            out
        }
        Speaker::Assistant => {
            let text = m.text();
            if react {
                return vec![json!({"role": "assistant", "content": text})];
            }
            let calls: Vec<Value> = m
                .tool_uses()
                .into_iter()
                .map(|(id, name, input)| json!({"id": id, "type": "function", "function": {"name": name, "arguments": input.to_string()}}))
                .collect();
            let mut v = json!({"role": "assistant", "content": if text.is_empty() { Value::Null } else { Value::String(text) }});
            if !calls.is_empty()
                && let Some(o) = v.as_object_mut()
            {
                o.insert("tool_calls".into(), Value::Array(calls));
            }
            vec![v]
        }
    }
}

#[derive(Debug, Default)]
struct CallAcc {
    id: String,
    name: String,
    args: String,
}

/// Accumulates a streamed chat completion.
#[derive(Debug, Default)]
pub struct ChatStream {
    text: String,
    calls: BTreeMap<u64, CallAcc>,
    pub usage: Usage,
    pub finish: Option<String>,
    pub model: String,
    pub done: bool,
}

impl ChatStream {
    pub fn apply(&mut self, ev: &SseEvent, on_delta: &mut dyn FnMut(Delta)) -> Result<(), ToolError> {
        let data = ev.data.trim();
        if data.is_empty() {
            return Ok(());
        }
        if data == "[DONE]" {
            self.done = true;
            return Ok(());
        }
        let v: Value =
            serde_json::from_str(data).map_err(|e| ToolError::new(ErrorCode::GarbledOutput, format!("The server sent a chunk we couldn't read: {e}")))?;
        if let Some(err) = v.get("error") {
            let msg = err.get("message").and_then(Value::as_str).unwrap_or("unknown error");
            return Err(ToolError::new(ErrorCode::EngineMissing, format!("Stream error: {msg}")));
        }
        if let Some(m) = v.get("model").and_then(Value::as_str) {
            self.model = m.to_string();
        }
        if let Some(u) = v.get("usage").filter(|u| u.is_object()) {
            self.usage.output_tokens = u.get("completion_tokens").and_then(Value::as_u64).unwrap_or(self.usage.output_tokens);
            let cached = u.pointer("/prompt_tokens_details/cached_tokens").and_then(Value::as_u64);
            if let Some(c) = cached {
                self.usage.cache_read_tokens = c;
            }
            // prompt_tokens includes the cached ones; input_tokens is the rest, as Anthropic reports
            // it, so the context budget and the cost count cached tokens once (#252).
            if let Some(p) = u.get("prompt_tokens").and_then(Value::as_u64) {
                self.usage.input_tokens = p.saturating_sub(cached.unwrap_or(0));
            }
        }
        let Some(choice) = v.get("choices").and_then(Value::as_array).and_then(|a| a.first()) else { return Ok(()) };
        let d = choice.get("delta").cloned().unwrap_or(Value::Null);
        if let Some(t) = d.get("content").and_then(Value::as_str).filter(|t| !t.is_empty()) {
            self.text.push_str(t);
            on_delta(Delta::Text(t.to_string()));
        }
        if let Some(t) = d.get("reasoning_content").or_else(|| d.get("reasoning")).and_then(Value::as_str).filter(|t| !t.is_empty()) {
            on_delta(Delta::Thinking(t.to_string()));
        }
        if let Some(calls) = d.get("tool_calls").and_then(Value::as_array) {
            for (pos, c) in calls.iter().enumerate() {
                let idx = c.get("index").and_then(Value::as_u64).unwrap_or(pos as u64);
                if self.calls.len() >= 256 && !self.calls.contains_key(&idx) {
                    continue;
                }
                let acc = self.calls.entry(idx).or_default();
                if let Some(id) = c.get("id").and_then(Value::as_str) {
                    acc.id = id.to_string();
                }
                if let Some(n) = c.pointer("/function/name").and_then(Value::as_str) {
                    acc.name.push_str(n);
                }
                if let Some(a) = c.pointer("/function/arguments").and_then(Value::as_str) {
                    acc.args.push_str(a);
                }
            }
        }
        if let Some(f) = choice.get("finish_reason").and_then(Value::as_str) {
            self.finish = Some(f.to_string());
        }
        Ok(())
    }

    pub fn finish(self, fallback_model: &str) -> Result<TurnResult, ToolError> {
        let mut blocks = Vec::new();
        if !self.text.is_empty() {
            blocks.push(Block::Text { text: self.text });
        }
        let has_calls = !self.calls.is_empty();
        for (i, (_, c)) in self.calls.into_iter().enumerate() {
            let input =
                if c.args.trim().is_empty() { json!({}) } else { serde_json::from_str(&c.args).unwrap_or_else(|_| crate::anthropic::invalid_input(&c.args)) };
            let id = if c.id.is_empty() { format!("call_{i}") } else { c.id };
            blocks.push(Block::ToolUse { id, name: c.name, input });
        }
        let stop = match self.finish.as_deref() {
            Some(f) => StopReason::parse(f),
            None if has_calls => StopReason::ToolUse,
            None if self.done => StopReason::EndTurn,
            None => return Err(ToolError::new(ErrorCode::Truncated, "The answer stream ended early.")),
        };
        // Some servers say "stop" even when they emitted tool calls.
        let stop = if has_calls { StopReason::ToolUse } else { stop };
        let model = if self.model.is_empty() { fallback_model.to_string() } else { self.model };
        Ok(TurnResult { message: Msg { role: Speaker::Assistant, blocks }, stop, usage: self.usage, model })
    }
}

/// Extra system text for the ReAct protocol.
pub fn react_instructions(tools: &[ToolDef]) -> String {
    let mut s = String::from(
        "\n\n## Using tools (text protocol)\nYou can't call tools directly. To use one, reply with exactly two lines and nothing after them:\nAction: <tool name>\nAction Input: <JSON object with the parameters>\nYou'll get the result back as an Observation. When you have the answer, start a line with \"Final Answer:\" and write it.\n\nTools:\n",
    );
    for t in tools {
        s.push_str(&format!("- {}: {} Parameters: {}\n", t.name, t.description, t.schema));
    }
    s
}

/// A ReAct step parsed from model text.
#[derive(Debug, Clone, PartialEq)]
pub enum ReactStep {
    Action {
        tool: String,
        input: Value,
    },
    Final(String),
    /// Plain text with no protocol markers (treated as the answer).
    Text(String),
}

/// Parse the model's text according to the ReAct protocol.
pub fn parse_react(text: &str) -> ReactStep {
    if let Some(pos) = text.find("Final Answer:") {
        return ReactStep::Final(text.get(pos + "Final Answer:".len()..).unwrap_or_default().trim().to_string());
    }
    let Some(apos) = text.find("Action:") else { return ReactStep::Text(text.trim().to_string()) };
    let after = text.get(apos + "Action:".len()..).unwrap_or_default();
    let tool = after.lines().next().unwrap_or_default().trim().trim_matches('`').to_string();
    let input = match after.find("Action Input:") {
        Some(ipos) => {
            let raw = after.get(ipos + "Action Input:".len()..).unwrap_or_default().trim();
            let raw = raw.trim_start_matches("```json").trim_start_matches("```").trim();
            extract_json_object(raw).unwrap_or_else(|| json!({}))
        }
        None => json!({}),
    };
    if tool.is_empty() { ReactStep::Text(text.trim().to_string()) } else { ReactStep::Action { tool, input } }
}

/// The first balanced `{…}` in `s`, parsed.
fn extract_json_object(s: &str) -> Option<Value> {
    let start = s.find('{')?;
    let mut depth = 0usize;
    let mut in_str = false;
    let mut esc = false;
    for (i, c) in s.char_indices().skip_while(|(i, _)| *i < start) {
        if in_str {
            match (esc, c) {
                (true, _) => esc = false,
                (false, '\\') => esc = true,
                (false, '"') => in_str = false,
                _ => {}
            }
            continue;
        }
        match c {
            '"' => in_str = true,
            '{' => depth += 1,
            '}' => {
                depth = depth.saturating_sub(1);
                if depth == 0 {
                    return serde_json::from_str(s.get(start..=i)?).ok();
                }
            }
            _ => {}
        }
    }
    None
}

static REACT_COUNTER: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

/// Turn ReAct text into neutral tool-use blocks.
fn react_postprocess(r: &mut TurnResult) {
    let text = r.message.text();
    if let ReactStep::Action { tool, input } = parse_react(&text) {
        let n = REACT_COUNTER.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        r.message.blocks.push(Block::ToolUse { id: format!("react_{n}"), name: tool, input });
        r.stop = StopReason::ToolUse;
    } else {
        r.stop = StopReason::EndTurn;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::Effort;

    #[test]
    fn react_parsing() {
        assert_eq!(
            parse_react("Thought: look\nAction: core_session_show\nAction Input: {\"a\": \"}\"}\nmore"),
            ReactStep::Action { tool: "core_session_show".into(), input: json!({"a": "}"}) }
        );
        assert_eq!(parse_react("Action: core_targets_list\n"), ReactStep::Action { tool: "core_targets_list".into(), input: json!({}) });
        assert_eq!(parse_react("blah\nFinal Answer: it saves JSON"), ReactStep::Final("it saves JSON".into()));
        assert_eq!(parse_react("just words"), ReactStep::Text("just words".into()));
        assert_eq!(parse_react("Action: x\nAction Input: ```json\n{\"k\":1}\n```"), ReactStep::Action { tool: "x".into(), input: json!({"k": 1}) });
    }

    #[test]
    fn tool_call_accumulation() {
        let chunks = [
            json!({"model":"gpt-x","choices":[{"delta":{"role":"assistant","content":"Let me look"}}]}),
            json!({"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"core_session_","arguments":""}}]}}]}),
            json!({"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"show","arguments":"{\"x\""}}]}}]}),
            json!({"choices":[{"delta":{"tool_calls":[{"index":1,"id":"c2","function":{"name":"core_targets_list","arguments":"{}"}}]}}]}),
            json!({"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":":1}"}}]}}]}),
            json!({"choices":[{"delta":{},"finish_reason":"tool_calls"}]}),
            json!({"choices":[],"usage":{"prompt_tokens":11,"completion_tokens":5}}),
        ];
        let mut st = ChatStream::default();
        let mut text = String::new();
        for c in chunks {
            st.apply(&SseEvent { event: None, data: c.to_string() }, &mut |d| {
                if let Delta::Text(t) = d {
                    text.push_str(&t)
                }
            })
            .unwrap();
        }
        st.apply(&SseEvent { event: None, data: "[DONE]".into() }, &mut |_| {}).unwrap();
        let r = st.finish("m").unwrap();
        assert_eq!(text, "Let me look");
        assert_eq!(r.stop, StopReason::ToolUse);
        assert_eq!(r.usage.input_tokens, 11);
        // #252: cached prompt tokens are part of prompt_tokens, and are counted once.
        let mut st = ChatStream::default();
        let usage = json!({"choices": [], "usage": {"prompt_tokens": 100_000, "completion_tokens": 10, "prompt_tokens_details": {"cached_tokens": 65_536}}});
        let end = json!({"choices": [{"delta": {}, "finish_reason": "stop"}]});
        for data in [end.to_string(), usage.to_string(), "[DONE]".into()] {
            st.apply(&SseEvent { event: None, data }, &mut |_| {}).unwrap();
        }
        let u = st.finish("m").unwrap().usage;
        assert_eq!((u.input_tokens, u.cache_read_tokens, u.output_tokens), (34_464, 65_536, 10));
        assert_eq!(
            r.message.tool_uses(),
            vec![("c1".into(), "core_session_show".into(), json!({"x": 1})), ("c2".into(), "core_targets_list".into(), json!({}))]
        );
    }

    #[test]
    fn wire_messages() {
        let o = OpenAi::openrouter(None, "k".into(), "");
        assert!(o.headers().iter().any(|(k, _)| *k == "X-Title"));
        assert!(o.headers().iter().any(|(k, v)| *k == "authorization" && v == "Bearer k"));
        let local = OpenAi::compatible("Ollama", "http://127.0.0.1:11434/v1/", None, "llama3");
        assert!(local.headers().is_empty());
        assert_eq!(local.url("models"), "http://127.0.0.1:11434/v1/models");
        let assistant = Msg { role: Speaker::Assistant, blocks: vec![Block::ToolUse { id: "c1".into(), name: "t".into(), input: json!({"a":1}) }] };
        let results = Msg {
            role: Speaker::User,
            blocks: vec![
                Block::ToolResult { tool_use_id: "c1".into(), content: "ok".into(), is_error: false },
                Block::ToolResult { tool_use_id: "c2".into(), content: "bad".into(), is_error: true },
            ],
        };
        let msgs = vec![Msg::user_text("q"), assistant, results];
        let tools = vec![ToolDef { name: "t".into(), description: "d".into(), schema: json!({"type":"object"}) }];
        let b = local.body(&TurnRequest { system: "S", messages: &msgs, tools: &tools, effort: Effort::Low, max_tokens: 100 });
        let m = b["messages"].as_array().unwrap();
        assert_eq!(m[0]["role"], "system");
        assert_eq!(m[2]["tool_calls"][0]["function"]["arguments"], "{\"a\":1}");
        assert_eq!(m[3]["role"], "tool");
        assert_eq!(m[4]["tool_call_id"], "c2");
        assert_eq!(b["tool_choice"], "auto");
        let mut react = local.clone();
        react.react = true;
        let b = react.body(&TurnRequest { system: "S", messages: &msgs, tools: &tools, effort: Effort::Low, max_tokens: 100 });
        assert!(b.get("tools").is_none());
        assert!(b["messages"][0]["content"].as_str().unwrap().contains("Action Input:"));
        assert!(b["messages"][3]["content"].as_str().unwrap().contains("Observation (error): bad"));
    }
}
