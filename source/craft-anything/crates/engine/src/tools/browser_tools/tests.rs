//! End-to-end tests for the browser (CDP) tools driven through the engine, with a tiny in-test
//! HTTP + WebSocket server that speaks a few CDP messages. No real browser is started.

use crate::{CallOptions, Caller, Engine};
use craft_anything_evidence::{ErrorCode, ToolError};
use serde_json::{Value, json};
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

fn call(e: &Engine, id: &str, p: Value) -> Result<Value, ToolError> {
    e.call(id, p, CallOptions::new(Caller::Mcp)).map(|o| o.to_json())
}

/// A declared secret used to prove redaction; appears in a URL the fake server reports.
const SECRET: &str = "tok-SECRET-123";

/// Start a fake CDP endpoint. Returns (endpoint url, a flag set true once a WS connection closed).
fn fake_cdp() -> (String, Arc<AtomicBool>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let url = format!("http://127.0.0.1:{port}");
    let ws_seen = Arc::new(AtomicBool::new(false));
    let ws_seen2 = ws_seen.clone();
    std::thread::spawn(move || {
        for s in listener.incoming() {
            let Ok(stream) = s else { break };
            let seen = ws_seen2.clone();
            std::thread::spawn(move || serve(stream, port, seen));
        }
    });
    (url, ws_seen)
}

fn read_headers(stream: &mut TcpStream) -> (String, Vec<(String, String)>) {
    let mut buf = Vec::new();
    let mut byte = [0u8; 1];
    while !buf.windows(4).any(|w| w == b"\r\n\r\n") {
        match stream.read(&mut byte) {
            Ok(0) => break,
            Ok(_) => buf.push(byte[0]),
            Err(_) => break,
        }
        if buf.len() > 64 * 1024 {
            break;
        }
    }
    let text = String::from_utf8_lossy(&buf).into_owned();
    let mut lines = text.split("\r\n");
    let request_line = lines.next().unwrap_or("").to_string();
    let headers =
        lines.filter(|l| !l.is_empty()).filter_map(|l| l.split_once(':')).map(|(k, v)| (k.trim().to_ascii_lowercase(), v.trim().to_string())).collect();
    (request_line, headers)
}

fn http_json(stream: &mut TcpStream, body: &str) {
    let resp = format!("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len());
    let _ = stream.write_all(resp.as_bytes());
}

fn serve(mut stream: TcpStream, port: u16, ws_seen: Arc<AtomicBool>) {
    let (request_line, headers) = read_headers(&mut stream);
    let path = request_line.split_whitespace().nth(1).unwrap_or("/");
    if path.starts_with("/json/version") {
        http_json(
            &mut stream,
            &json!({"Browser": "HeadlessChrome/120", "Protocol-Version": "1.3", "webSocketDebuggerUrl": format!("ws://127.0.0.1:{port}/devtools/browser/x")})
                .to_string(),
        );
        return;
    }
    if path.starts_with("/json/list") {
        let list = json!([{
            "id": "PAGE1",
            "type": "page",
            "title": "Test Page",
            "url": "https://app.test/",
            "webSocketDebuggerUrl": format!("ws://127.0.0.1:{port}/devtools/page/PAGE1")
        }]);
        http_json(&mut stream, &list.to_string());
        return;
    }
    // WebSocket upgrade.
    if headers.iter().any(|(k, v)| k == "upgrade" && v.eq_ignore_ascii_case("websocket")) {
        let key = headers.iter().find(|(k, _)| k == "sec-websocket-key").map(|(_, v)| v.clone()).unwrap_or_default();
        let accept = ws_accept(&key);
        let resp = format!("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n");
        let _ = stream.write_all(resp.as_bytes());
        serve_ws(&mut stream);
        ws_seen.store(true, Ordering::Relaxed);
        return;
    }
    let _ = stream.write_all(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
}

fn ws_accept(key: &str) -> String {
    use base64::Engine as _;
    use sha1::{Digest, Sha1};
    let mut h = Sha1::new();
    h.update(key.as_bytes());
    h.update(b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11");
    base64::engine::general_purpose::STANDARD.encode(h.finalize())
}

/// Read one client (masked) text message from a WebSocket.
fn ws_read(stream: &mut TcpStream) -> Option<String> {
    let mut hdr = [0u8; 2];
    stream.read_exact(&mut hdr).ok()?;
    let opcode = hdr[0] & 0x0f;
    let masked = hdr[1] & 0x80 != 0;
    let mut len = (hdr[1] & 0x7f) as usize;
    if len == 126 {
        let mut e = [0u8; 2];
        stream.read_exact(&mut e).ok()?;
        len = u16::from_be_bytes(e) as usize;
    } else if len == 127 {
        let mut e = [0u8; 8];
        stream.read_exact(&mut e).ok()?;
        len = u64::from_be_bytes(e) as usize;
    }
    let mut mask = [0u8; 4];
    if masked {
        stream.read_exact(&mut mask).ok()?;
    }
    let mut payload = vec![0u8; len];
    stream.read_exact(&mut payload).ok()?;
    if masked {
        for (i, b) in payload.iter_mut().enumerate() {
            *b ^= mask[i & 3];
        }
    }
    if opcode == 0x8 {
        return None; // close
    }
    Some(String::from_utf8_lossy(&payload).into_owned())
}

/// Write one server (unmasked) text message.
fn ws_write(stream: &mut TcpStream, text: &str) {
    let bytes = text.as_bytes();
    let mut frame = vec![0x81u8];
    let len = bytes.len();
    if len < 126 {
        frame.push(len as u8);
    } else if len <= u16::MAX as usize {
        frame.push(126);
        frame.extend_from_slice(&(len as u16).to_be_bytes());
    } else {
        frame.push(127);
        frame.extend_from_slice(&(len as u64).to_be_bytes());
    }
    frame.extend_from_slice(bytes);
    let _ = stream.write_all(&frame);
}

fn serve_ws(stream: &mut TcpStream) {
    let bundle = craft_anything_testkit::electron::WEBPACK_BUNDLE;
    while let Some(msg) = ws_read(stream) {
        let req: Value = match serde_json::from_str(&msg) {
            Ok(v) => v,
            Err(_) => continue,
        };
        let id = req.get("id").and_then(Value::as_u64).unwrap_or(0);
        let method = req.get("method").and_then(Value::as_str).unwrap_or("").to_string();
        // Reply to the command.
        let result = match method.as_str() {
            "DOM.getDocument" => json!({"root": {"nodeId": 1, "nodeType": 9, "nodeName": "#document", "children": [
                {"nodeType": 1, "nodeName": "BODY", "attributes": ["data-token", SECRET], "children": [
                    {"nodeType": 1, "nodeName": "BUTTON", "nodeId": 42}
                ]}
            ]}}),
            "DOM.querySelector" => json!({"nodeId": 42}),
            "DOM.getBoxModel" => json!({"model": {"content": [0, 0, 10, 0, 10, 10, 0, 10]}}),
            "Page.getFrameTree" => json!({"frameTree": {"frame": {"url": "https://app.test/"}, "childFrames": []}}),
            "Page.getResourceTree" => json!({"frameTree": {"frame": {"url": "https://app.test/"}, "resources": [
                {"url": "https://user:pw@app.test/assets/main.js", "type": "Script", "mimeType": "application/javascript"}
            ]}}),
            "Page.captureScreenshot" => json!({"data": tiny_png_b64()}),
            "Profiler.takePreciseCoverage" => {
                let scripts: Vec<Value> = ["a", "b", "c"]
                    .iter()
                    .map(|n| json!({"scriptId": n, "url": format!("https://app.test/{n}.js"), "functions": [{"isBlockCoverage": false, "ranges": [{"count": 1}]}]}))
                    .collect();
                json!({"result": scripts})
            }
            "Debugger.getScriptSource" => json!({"scriptSource": bundle}),
            "Network.getResponseBody" => json!({"body": "{\"id\":1,\"secret\":\"x\"}", "base64Encoded": false}),
            // One accessible element: a button named "Sign in".
            "Accessibility.queryAXTree" => {
                match (req.pointer("/params/role").and_then(Value::as_str), req.pointer("/params/accessibleName").and_then(Value::as_str)) {
                    (Some("button"), Some("Sign in")) => {
                        json!({"nodes": [{"ignored": true, "backendDOMNodeId": 6}, {"ignored": false, "backendDOMNodeId": 7}]})
                    }
                    _ => json!({"nodes": []}),
                }
            }
            "DOM.pushNodesByBackendIdsToFrontend" => json!({"nodeIds": [42]}),
            "DOM.resolveNode" => json!({"object": {"objectId": "node-42"}}),
            "Page.getNavigationHistory" => json!({"currentIndex": 0, "entries": [{"url": format!("https://app.test/home?k={SECRET}")}]}),
            "DOM.getOuterHTML" => json!({"outerHTML": format!("<html><body data-token=\"{SECRET}\">Hi</body></html>")}),
            "Accessibility.getFullAXTree" => json!({"nodes": [{"role": {"value": "button"}, "name": {"value": format!("Pay {SECRET}")}}]}),
            "DOMStorage.getDOMStorageItems" => json!({"entries": [["theme", "dark-VALUE"]]}),
            "Network.getCookies" => json!({"cookies": [{"name": "sid", "value": "cookie-VALUE"}]}),
            _ => json!({}),
        };
        ws_write(stream, &json!({"id": id, "result": result}).to_string());
        // A navigation brings one event of every family the walkthrough can record, and a request.
        if method == "Page.navigate" {
            for ev in [
                json!({"method": "Runtime.consoleAPICalled", "params": {"type": "log", "args": [{"type": "string", "value": format!("hello {SECRET}")}]}}),
                json!({"method": "Runtime.exceptionThrown", "params": {"exceptionDetails": {"text": "Uncaught", "exception": {"description": "TypeError: x is undefined"}}}}),
                json!({"method": "Network.webSocketCreated", "params": {"requestId": "W1", "url": "wss://app.test/live"}}),
                json!({"method": "Network.webSocketFrameSent", "params": {"requestId": "W1", "response": {"opcode": 1, "payloadData": format!("{{\"auth\":\"{SECRET}\"}}")}}}),
                json!({"method": "Page.frameNavigated", "params": {"frame": {"id": "F1", "url": "https://app.test/"}}}),
                json!({"method": "Target.targetCreated", "params": {"targetInfo": {"targetId": "T9", "type": "service_worker", "url": "https://app.test/sw.js"}}}),
                json!({"method": "Target.targetCreated", "params": {"targetInfo": {"targetId": "T8", "type": "page", "openerId": "PAGE1", "url": "https://pop.test/"}}}),
                json!({"method": "Target.targetDestroyed", "params": {"targetId": "T9"}}),
                json!({"method": "Page.downloadWillBegin", "params": {"url": "https://app.test/file.zip", "suggestedFilename": "file.zip"}}),
                json!({"method": "Network.requestWillBeSent", "params": {"requestId": "R2", "request": {"method": "GET", "url": "https://app.test/after-goto"}, "type": "Document"}}),
            ] {
                ws_write(stream, &ev.to_string());
            }
        }
        // Emit events after specific enables.
        if method == "Debugger.enable" {
            ws_write(stream, &json!({"method": "Debugger.scriptParsed", "params": {"scriptId": "1", "url": "https://app.test/assets/main.js", "length": 1234, "sourceMapURL": ""}}).to_string());
        }
        if method == "Network.enable" {
            ws_write(
                stream,
                &json!({"method": "Network.requestWillBeSent", "params": {
                    "requestId": "R1",
                    "request": {"method": "GET", "url": format!("https://app.test/api/items?auth={SECRET}"),
                        "headers": {"Authorization": "Bearer abc", "X-Trace": format!("t-{SECRET}")}, "postData": format!("{{\"token\":\"{SECRET}\"}}")},
                    "initiator": {"type": "script"},
                    "type": "XHR"
                }})
                .to_string(),
            );
            ws_write(stream, &json!({"method": "Network.responseReceived", "params": {
                "requestId": "R1",
                "response": {"status": 200, "mimeType": "application/json", "headers": {"Set-Cookie": "sid=SUPERSECRET", "Content-Type": "application/json"}}
            }}).to_string());
        }
    }
}

/// A 1×1 transparent PNG, base64 (for screenshot tests).
fn tiny_png_b64() -> String {
    use base64::Engine as _;
    let mut out = Vec::new();
    {
        let mut enc = png::Encoder::new(&mut out, 1, 1);
        enc.set_color(png::ColorType::Rgba);
        enc.set_depth(png::BitDepth::Eight);
        let mut w = enc.write_header().unwrap();
        w.write_image_data(&[1, 2, 3, 255]).unwrap();
    }
    base64::engine::general_purpose::STANDARD.encode(&out)
}

#[test]
fn list_targets_over_http() {
    let (url, _) = fake_cdp();
    let e = Engine::new(crate::testing::session());
    let v = call(&e, "web_pages_list", json!({"cdp_endpoint": url})).unwrap();
    assert_eq!(v["environment"]["engine"], "cdp");
    assert_eq!(v["environment"]["clean_room"], false);
    assert_eq!(v["result"]["product"], "HeadlessChrome/120");
    let targets = v["result"]["targets"].as_array().unwrap();
    assert_eq!(targets.len(), 1);
    assert_eq!(targets[0]["type"], "page");
}

#[test]
fn walkthrough_applies_a_fixed_environment() {
    let (url, _) = fake_cdp();
    let e = Engine::new(crate::testing::session());
    let run = |p: Value| e.call("web_walkthrough_record", p, CallOptions::new(Caller::Mcp).with_consent(crate::Consent::Granted)).map(|o| o.to_json());
    let wait = json!([{"kind": "wait", "ms": 1}]);
    let v =
        run(json!({"cdp_endpoint": url, "actions": wait, "environment": {"width": 390, "height": 844, "locale": "de-DE", "color_scheme": "dark"}})).unwrap();
    let env = &v["result"]["environment"];
    assert_eq!(env["requested"]["width"], 390);
    assert_eq!(env["requested"]["color_scheme"], "dark");
    assert_eq!(env["requested"]["timezone"], "UTC", "unset fields keep their defaults");
    for k in ["viewport", "locale", "timezone", "media", "service_workers"] {
        assert_eq!(env["settings"][k], "applied", "{k}");
    }
    let err = run(json!({"cdp_endpoint": url, "actions": wait, "environment": {"timezone": "../etc/passwd"}})).unwrap_err();
    assert!(err.message.contains("timezone"), "{}", err.message);
}

#[test]
fn walkthrough_steps_find_elements_by_role_test_id_or_css() {
    let (url, _) = fake_cdp();
    let e = Engine::new(crate::testing::session());
    let run = |actions: Value| {
        e.call("web_walkthrough_record", json!({"cdp_endpoint": url, "actions": actions}), CallOptions::new(Caller::Mcp).with_consent(crate::Consent::Granted))
            .map(|o| o.to_json())
            .unwrap()
    };
    let v = run(json!([
        {"step_id": "sign-in", "kind": "click", "role": "button", "name": "Sign in"},
        {"kind": "fill", "test_id": "email", "value": "me@example.test"},
        {"kind": "click", "selector": "button"}
    ]));
    let steps = v["result"]["steps"].as_array().unwrap();
    assert!(steps.iter().all(|s| s["status"] == "ok"), "{steps:?}");
    assert_eq!(steps[0]["step_id"], "sign-in");
    assert!(steps[1]["step_id"].is_null());

    // A name that isn't on the page, and a step with two locators, fail in plain words.
    let v = run(json!([{"kind": "click", "role": "button", "name": "Log out"}]));
    assert!(v["result"]["steps"][0]["error"].as_str().unwrap().contains("no button named \"Log out\""), "{}", v["result"]["steps"][0]);
    let v = run(json!([{"kind": "click", "selector": "a", "role": "button", "name": "Sign in"}]));
    assert!(v["result"]["steps"][0]["error"].as_str().unwrap().contains("exactly one"), "{}", v["result"]["steps"][0]);
}

#[test]
fn walkthrough_keeps_requested_network_content_redacted() {
    let (url, _) = fake_cdp();
    let e = Engine::new(crate::testing::session());
    let run = |extra: Value| {
        let mut p = json!({"cdp_endpoint": url, "actions": [{"kind": "wait", "ms": 1}], "hidden_values": [SECRET]});
        for (k, v) in extra.as_object().unwrap() {
            p[k] = v.clone();
        }
        e.call("web_walkthrough_record", p, CallOptions::new(Caller::Mcp).with_consent(crate::Consent::Granted)).map(|o| o.to_json())
    };
    // Off by default: no bodies or header values.
    let v = run(json!({})).unwrap();
    let req = &v["result"]["network"]["requests"][0];
    assert!(req.get("request_body").is_none() && req.get("response_body").is_none() && req.get("request_headers").is_none(), "{req}");

    let v = run(json!({"keep_bodies": {"request_body": true, "response_body": true, "header_values": true}})).unwrap();
    let text = v.to_string();
    assert!(!text.contains(SECRET), "the declared secret never appears");
    let req = &v["result"]["network"]["requests"][0];
    assert!(req["request_body"]["text"].as_str().unwrap().contains("token"), "{req}");
    assert_eq!(req["request_headers"]["authorization"], "«redacted»");
    assert_eq!(req["response_header_values"]["set-cookie"], "«redacted»");
    assert_eq!(req["response_body"]["text"], "{\"id\":1,\"secret\":\"x\"}");
    assert_eq!(req["response_body"]["sha256"].as_str().unwrap().len(), 64);

    let err = run(json!({"capture_network": false, "keep_bodies": {"response_body": true}})).unwrap_err();
    assert!(err.message.contains("capture_network"), "{}", err.message);
}

#[test]
fn walkthrough_starts_with_given_storage_and_never_echoes_it() {
    let (url, _) = fake_cdp();
    let e = Engine::new(crate::testing::session());
    let run = |storage: Value| {
        e.call(
            "web_walkthrough_record",
            json!({"cdp_endpoint": url, "actions": [{"kind": "wait", "ms": 1}], "storage": storage}),
            CallOptions::new(Caller::Mcp).with_consent(crate::Consent::Granted),
        )
        .map(|o| o.to_json())
    };
    let v = run(json!({
        "cookies": [{"url": "https://app.test/", "name": "sid", "value": "cookie-VALUE-9", "http_only": true, "secure": true, "same_site": "Lax"}],
        "local_storage": [{"origin": "https://app.test", "entries": {"theme": "dark", "token": "ls-VALUE-7"}}]
    }))
    .unwrap();
    let seeded = &v["result"]["starting_storage"];
    assert_eq!(seeded["cookies_set"], json!(["sid"]));
    assert_eq!(seeded["storage_entries_set"], 2);
    assert_eq!(seeded["failed"], json!([]));
    let text = v.to_string();
    assert!(!text.contains("cookie-VALUE-9") && !text.contains("ls-VALUE-7"), "seeded values are never echoed");

    assert!(
        run(json!({"cookies": [{"url": "https://app.test/", "name": "a", "value": "b", "same_site": "Maybe"}]})).unwrap_err().message.contains("same_site")
    );
    assert!(run(json!({"session_storage": [{"origin": "ftp://x", "entries": {"a": "b"}}]})).unwrap_err().message.contains("http(s)"));
}

#[test]
fn walkthrough_records_artifacts_after_steps_and_at_the_end() {
    let (url, _) = fake_cdp();
    let e = Engine::new(crate::testing::session());
    let run = |capture: Value| {
        e.call(
            "web_walkthrough_record",
            json!({"cdp_endpoint": url, "actions": [{"kind": "wait", "ms": 1}], "capture": capture, "hidden_values": [SECRET]}),
            CallOptions::new(Caller::Mcp).with_consent(crate::Consent::Granted),
        )
        .map(|o| o.to_json())
    };
    let v = run(json!({"after_each_step": ["history"], "at_end": ["screenshot", "dom", "accessibility", "history", "storage_keys"]})).unwrap();
    let step = &v["result"]["steps"][0]["artifacts"];
    assert!(step["history"]["entries"][0]["url"].as_str().unwrap().contains("app.test/home"), "{step}");
    assert!(step.get("dom").is_none(), "only what was asked for");
    let end = &v["result"]["final_artifacts"];
    assert!(end["dom"]["text"].as_str().unwrap().contains("Hi"), "{end}");
    assert_eq!(end["accessibility"]["nodes"][0]["role"], "button");
    assert_eq!(end["storage_keys"]["origin"], "https://app.test");
    assert_eq!(end["storage_keys"]["areas"][0]["keys"], json!(["theme"]));
    assert_eq!(end["storage_keys"]["cookie_names"], json!(["sid"]));
    assert!(end["screenshot"].is_object());
    let text = v.to_string();
    assert!(!text.contains(SECRET) && !text.contains("dark-VALUE") && !text.contains("cookie-VALUE"), "no secrets or storage values");

    let all = json!(["screenshot", "dom", "accessibility", "history", "storage_keys", "dom"]);
    assert!(run(json!({"at_end": all})).unwrap_err().message.contains("at most"));
}

fn walkthrough(e: &Engine, p: Value) -> Result<Value, ToolError> {
    e.call("web_walkthrough_record", p, CallOptions::new(Caller::Mcp).with_consent(crate::Consent::Granted)).map(|o| o.to_json())
}

#[test]
fn walkthrough_keeps_network_from_every_step() {
    // Regression: a goto step used to drop every event buffered so far.
    let (url, _) = fake_cdp();
    let e = Engine::new(crate::testing::session());
    let v = walkthrough(&e, json!({"cdp_endpoint": url, "actions": [{"kind": "goto", "url": "https://app.test/", "wait_ms": 50}, {"kind": "wait", "ms": 1}]}))
        .unwrap();
    let urls: Vec<String> = v["result"]["network"]["requests"].as_array().unwrap().iter().map(|r| r["url"].as_str().unwrap().to_string()).collect();
    assert!(urls.iter().any(|u| u.contains("/api/items")), "the request from before the goto: {urls:?}");
    assert!(urls.iter().any(|u| u.contains("/after-goto")), "the request from the goto itself: {urls:?}");
    assert!(v["result"]["events"].is_null(), "no families asked for");
}

#[test]
fn walkthrough_records_requested_event_families() {
    let (url, _) = fake_cdp();
    let e = Engine::new(crate::testing::session());
    let all = json!(["console", "page_errors", "websockets", "frames", "workers", "popups", "downloads"]);
    let v = walkthrough(
        &e,
        json!({"cdp_endpoint": url, "actions": [{"kind": "goto", "url": "https://app.test/", "wait_ms": 50}], "capture": {"events": all}, "hidden_values": [SECRET]}),
    )
    .unwrap();
    let ev = &v["result"]["events"];
    let items = ev["items"].as_array().unwrap();
    let kinds: Vec<&str> = items.iter().map(|i| i["kind"].as_str().unwrap()).collect();
    for k in [
        "console",
        "page-error",
        "websocket-opened",
        "websocket-frame-sent",
        "frame-navigated",
        "worker-opened",
        "popup-opened",
        "worker-closed",
        "download-blocked",
    ] {
        assert!(kinds.contains(&k), "{k} in {kinds:?}");
    }
    assert!(items.iter().all(|i| i["step_index"] == 0), "all happened during the goto");
    assert_eq!(items[0]["sequence"], 1);
    assert!(!v.to_string().contains(SECRET), "console and frame text are redacted");
}

#[test]
fn two_scripted_runs_compare_step_by_step() {
    let (url, _) = fake_cdp();
    let e = Engine::new(crate::testing::session());
    let run = |second: &str| {
        walkthrough(
            &e,
            json!({"cdp_endpoint": url, "actions": [
                {"step_id": "open", "kind": "goto", "url": "https://app.test/", "wait_ms": 20},
                {"step_id": "sign-in", "kind": "click", "role": "button", "name": second}
            ]}),
        )
        .unwrap()
    };
    let (good, bad) = (run("Sign in"), run("Log out"));
    let v = call(&e, "web_snapshots_compare", json!({"before": good, "after": bad})).unwrap();
    let r = &v["result"];
    assert_eq!(r["kind"], "walkthrough");
    assert_eq!(r["steps"][0]["status"], "same", "{}", r["steps"]);
    assert_eq!(r["steps"][1]["status"], "changed");
    assert!(r["steps"][1]["changes"].as_array().unwrap().iter().any(|c| c["field"] == "status"));
    assert_eq!(r["comparable"], false, "an aborted run never proves equality");
    assert_eq!(r["aborted_runs"], json!(["after"]));

    // A volatile value (a build number in the step ids) stops counting once normalised.
    let named = |id: &str| walkthrough(&e, json!({"cdp_endpoint": url, "actions": [{"step_id": id, "kind": "wait", "ms": 1}]})).unwrap();
    let (a, b) = (named("open-build-1"), named("open-build-2"));
    let raw = call(&e, "web_snapshots_compare", json!({"before": a, "after": b})).unwrap();
    assert_eq!(raw["result"]["summary"]["changed_steps"], 2, "only_before + only_after");
    let rules = json!([{"rule_id": "b", "match": "build-2", "replacement": "BUILD"}, {"rule_id": "a", "match": "build-1", "replacement": "BUILD"}]);
    let norm = call(&e, "web_snapshots_compare", json!({"before": a, "after": b, "normalization": rules})).unwrap();
    assert_eq!(norm["result"]["summary"]["changed_steps"], 0, "{}", norm["result"]);
    assert_eq!(norm["result"]["normalization"][0]["rule_id"], "a", "rules run in rule_id order");
    assert_eq!(norm["result"]["normalization"][0]["replacements"], 1);

    // A run and a page capture don't compare.
    let page = make_capture(&["https://a/x.js"], &["button"]);
    assert!(call(&e, "web_snapshots_compare", json!({"before": a, "after": page})).unwrap_err().message.contains("scripted run"));
}

#[test]
fn a_plain_browser_is_not_called_electron() {
    let (url, _) = fake_cdp();
    let e = Engine::new(crate::testing::session());
    let v = call(&e, "js_electron_pages_list", json!({"cdp_endpoint": url})).unwrap();
    assert_eq!(v["result"]["runtime"], "chrome");
    assert!(v["summary"].as_str().unwrap().contains("not an Electron app"), "{}", v["summary"]);
    assert_eq!(v["result"]["targets"][0]["is_renderer"], false);
}

#[test]
fn inspect_page_minimises_and_redacts() {
    let (url, _) = fake_cdp();
    let e = Engine::new(crate::testing::session());
    let v = call(&e, "web_page_show", json!({"cdp_endpoint": url, "watch_ms": 200, "with_script_text": true, "hidden_values": [SECRET]})).unwrap();
    let text = v.to_string();
    // Framing round-trips: the scriptParsed event and DOM/resources were captured.
    assert_eq!(v["result"]["scripts"].as_array().unwrap().len(), 1);
    assert_eq!(v["result"]["dom"]["elements_by_name"]["button"], 1);
    // Data minimisation: no cookie, no userinfo, no declared secret anywhere.
    assert!(!text.contains("SUPERSECRET"), "cookie leaked: {text}");
    assert!(!text.contains(SECRET), "secret leaked: {text}");
    assert!(!text.contains("user:pw@"), "userinfo leaked: {text}");
    // The secret appeared in a URL and a DOM attribute value; both must be redacted/omitted.
    assert!(v["result"]["secret_redactions"].as_u64().unwrap() >= 1);
    let reqs = v["result"]["network"]["requests"].as_array().unwrap();
    assert!(reqs.iter().any(|r| r["url"].as_str().unwrap_or("").contains("«redacted»")));
    // The response Set-Cookie header is reported only by presence, never by value.
    assert!(reqs.iter().any(|r| r["response_headers"]["credentials_present"].as_array().map(|a| a.iter().any(|c| c == "set-cookie")).unwrap_or(false)));
    assert_eq!(v["authority"], "earlier-record");
}

#[test]
fn analyze_bundle_reuses_js_engine() {
    let (url, _) = fake_cdp();
    let e = Engine::new(crate::testing::session());
    let v = call(&e, "web_page_js_analyze", json!({"cdp_endpoint": url, "watch_ms": 200})).unwrap();
    assert_eq!(v["result"]["bundlers"], json!(["webpack"]));
    // The webpack bundle's three modules are recovered, and its endpoint is found.
    assert!(v["result"]["modules_total"].as_u64().unwrap() >= 1);
    let eps = v["result"]["endpoints"].as_array().unwrap();
    assert!(eps.iter().any(|ep| ep["url"].as_str().unwrap_or("").contains("/items")), "{}", v["result"]["endpoints"]);
}

#[test]
fn screenshot_and_compare() {
    let (url, _) = fake_cdp();
    let e = Engine::new(crate::testing::session());
    let shot = call(&e, "web_page_screenshot_take", json!({"cdp_endpoint": url})).unwrap();
    assert_eq!(shot["result"]["screenshot"]["media_type"], "image/png");
    let b64 = shot["result"]["screenshot"]["base64"].as_str().unwrap().to_string();
    assert_eq!(shot["result"]["screenshot"]["sha256"].as_str().unwrap().len(), 64);
    // Compare the screenshot with itself: identical.
    let cmp = call(&e, "web_pixels_compare", json!({"before": {"base64": b64.clone()}, "after": {"base64": b64}})).unwrap();
    assert_eq!(cmp["result"]["identical"], true);
}

#[test]
fn no_endpoint_no_launch_is_provider_unavailable() {
    // Empty engine store and no endpoint: every browser tool must refuse with a clear remediation.
    let e = Engine::new(crate::testing::session());
    for id in [
        "web_pages_list",
        "web_page_show",
        "web_page_js_analyze",
        "web_page_watch",
        "web_mcp_tools_list",
        "web_page_screenshot_take",
        "web_browser_connect",
        "web_coverage_measure",
        "web_listeners_list",
        "web_modules_trace",
    ] {
        let params = if id == "web_listeners_list" { json!({"selector": "button"}) } else { json!({}) };
        let err = call(&e, id, params).unwrap_err();
        assert_eq!(err.code, ErrorCode::EngineMissing, "{id} did not return EngineMissing");
        assert!(err.remediation.unwrap().to_lowercase().contains("settings → engines") || err.message.contains("endpoint"), "{id} remediation");
    }
}

#[test]
fn bad_endpoints_are_rejected() {
    let e = Engine::new(crate::testing::session());
    for bad in ["http://localhost:9222", "https://127.0.0.1:9222", "http://10.0.0.1:9222", "http://127.0.0.1"] {
        let err = call(&e, "web_pages_list", json!({"cdp_endpoint": bad})).unwrap_err();
        assert_eq!(err.code, ErrorCode::BadSettings, "{bad}");
    }
}

#[test]
fn compare_captures_is_pure() {
    // Two inline captures diffed without any browser.
    let e = Engine::new(crate::testing::session());
    let before = make_capture(&["https://a/x.js"], &["button"]);
    let after = make_capture(&["https://a/x.js", "https://a/y.js"], &["button", "input"]);
    let v = call(&e, "web_snapshots_compare", json!({"before": before, "after": after})).unwrap();
    let scripts = &v["result"]["sections"]["scripts"];
    assert_eq!(scripts["added"], json!(["https://a/y.js"]));
    assert!(v["result"]["summary"]["changed_sections"].as_array().unwrap().iter().any(|s| s == "scripts"));
}

/// Build a minimal web_page_show evidence record for compare tests.
fn make_capture(scripts: &[&str], elements: &[&str]) -> Value {
    use craft_anything_evidence::{Authority, Confidence, EvidenceBuilder, Subject};
    let mut by_name = serde_json::Map::new();
    for el in elements {
        by_name.insert((*el).to_string(), json!(1));
    }
    let result = json!({
        "origin": "https://a",
        "frame_origins": ["https://a"],
        "resources": [],
        "scripts": scripts.iter().map(|s| json!({"url": s})).collect::<Vec<_>>(),
        "dom": {"elements_by_name": by_name},
        "network": {"requests": []},
    });
    let ev = EvidenceBuilder::new(
        "web_page_show",
        Subject { kind: "website".into(), sha256: None, name: Some("https://a".into()) },
        crate::tools::web_common::cdp_env(false, None),
    )
    .result(result)
    .summary("x")
    .confidence(Confidence::Observed)
    .authority(Authority::EarlierRecord)
    .build()
    .unwrap();
    serde_json::to_value(ev).unwrap()
}

// ---- web_walkthrough_check ----

use super::script_check::{Severity, check_script, selector_problem, step_kinds};
use super::{WalkthroughStep, action_name};

fn errors_of(script: &Value) -> Vec<(Option<usize>, &'static str, String)> {
    let (problems, errors, _, _) = check_script(script);
    let found: Vec<_> = problems.iter().filter(|p| p.severity == Severity::Error).map(|p| (p.step, p.code, p.message.clone())).collect();
    assert_eq!(found.len() as u64, errors);
    found
}

/// Run a script for real against the fake browser: what it refused, or the first step that failed.
fn recorder_verdict(e: &Engine, url: &str, script: &Value) -> Option<(Option<usize>, String)> {
    let mut p = script.clone();
    p["cdp_endpoint"] = json!(url);
    match walkthrough(e, p) {
        Err(err) => Some((None, err.message)),
        Ok(v) => v["result"]["steps"]
            .as_array()
            .unwrap()
            .iter()
            .find(|s| s["status"] == "error")
            .map(|s| (s["index"].as_u64().map(|i| i as usize), s["error"].as_str().unwrap().to_string())),
    }
}

#[test]
fn the_checker_agrees_with_what_the_recorder_refuses() {
    let (url, _) = fake_cdp();
    let e = Engine::new(crate::testing::session());
    let ok_goto = json!({"kind": "goto", "url": "https://app.test/", "wait_ms": 1});
    let scripts = vec![
        // Accepted.
        json!({"actions": [ok_goto]}),
        json!({"actions": [ok_goto, {"kind": "click", "selector": "button"}, {"kind": "fill", "test_id": "email", "value": ""}, {"kind": "press", "selector": "input[name='q']", "key": "Enter"}, {"kind": "select", "selector": "#a > .b:nth-child(2)", "value": "x"}, {"kind": "wait", "ms": 1}, {"kind": "click", "role": "button", "name": "Sign in"}]}),
        json!({"actions": [{"kind": "click", "selector": "a[href=\"/x(1]\"]"}]}),
        json!({"actions": [{"kind": "click", "selector": "a:not(.b):first-child::before"}]}),
        json!({"actions": [{"kind": "click", "selector": "a\\:first"}]}),
        json!({"actions": [{"kind": "wait", "ms": 1, "unknown_extra": true}]}),
        json!({"actions": [{"step_id": "same", "kind": "wait", "ms": 1}, {"step_id": "same", "kind": "wait", "ms": 1}]}),
        json!({"actions": [ok_goto], "environment": {"width": 800, "height": 600}, "capture": {"at_end": ["dom"], "events": ["console"]}}),
        // Refused before anything runs.
        json!({}),
        json!({"actions": []}),
        json!({"actions": "goto"}),
        json!({"actions": vec![json!({"kind": "wait", "ms": 1}); 201]}),
        json!({"actions": [{"kind": "teleport"}]}),
        json!({"actions": [{"url": "https://app.test/"}]}),
        json!({"actions": [{"kind": 3}]}),
        json!({"actions": ["goto"]}),
        json!({"actions": [{"kind": "goto"}]}),
        json!({"actions": [{"kind": "goto", "url": 3}]}),
        json!({"actions": [{"kind": "fill", "selector": "a"}]}),
        json!({"actions": [{"kind": "press", "selector": "a"}]}),
        json!({"actions": [{"kind": "wait"}]}),
        json!({"actions": [{"kind": "wait", "ms": -1}]}),
        json!({"actions": [{"step_id": 3, "kind": "wait", "ms": 1}]}),
        json!({"actions": [ok_goto], "unknown_setting": 1}),
        json!({"actions": [ok_goto], "environment": {"width": 0}}),
        json!({"actions": [ok_goto], "environment": {"locale": "not a locale"}}),
        json!({"actions": [ok_goto], "capture": {"at_end": ["no_such_artifact"]}}),
        json!({"actions": [ok_goto], "capture": {"events": ["no_such_family"]}}),
        json!({"actions": [ok_goto], "keep_bodies": {"request_body": true}, "capture_network": false}),
        json!({"actions": [ok_goto], "storage": {"cookies": [{"url": "ftp://x", "name": "a", "value": "b"}]}}),
        json!({"actions": [ok_goto], "timeout_secs": 0}),
        json!({"actions": [ok_goto], "timeout_secs": 601}),
        // Refused at the step, after those before it ran.
        json!({"actions": [{"kind": "goto", "url": "example.com"}]}),
        json!({"actions": [ok_goto, {"kind": "click"}]}),
        json!({"actions": [{"kind": "click", "selektor": "a"}]}),
        json!({"actions": [{"kind": "click", "selector": "a", "test_id": "b"}]}),
        json!({"actions": [{"kind": "click", "selector": "a", "name": "b"}]}),
        json!({"actions": [{"kind": "click", "role": "button"}]}),
        json!({"actions": [{"kind": "click", "name": "Sign in"}]}),
        json!({"actions": [{"kind": "click", "role": "two words", "name": "x"}]}),
        json!({"actions": [{"kind": "click", "role": "button", "name": ""}]}),
        json!({"actions": [{"kind": "click", "test_id": ""}]}),
        json!({"actions": [{"kind": "click", "test_id": "a\nb"}]}),
        json!({"actions": [{"kind": "click", "selector": ""}]}),
        json!({"actions": [{"kind": "click", "selector": "//div[@id='a']"}]}),
        json!({"actions": [{"kind": "click", "selector": "text=Sign in"}]}),
        json!({"actions": [{"kind": "click", "selector": "button:has-text(\"Go\")"}]}),
        json!({"actions": [{"kind": "click", "selector": "li:contains(x)"}]}),
        json!({"actions": [{"kind": "click", "selector": "a >> b"}]}),
        json!({"actions": [{"kind": "click", "selector": "a[href"}]}),
        json!({"actions": [{"kind": "click", "selector": "a)"}]}),
        json!({"actions": [{"kind": "click", "selector": "a[x='y]"}]}),
        json!({"actions": [{"kind": "press", "selector": "a", "key": ""}]}),
    ];
    for script in &scripts {
        let checked = errors_of(script);
        let verdict = recorder_verdict(&e, &url, script);
        assert_eq!(!checked.is_empty(), verdict.is_some(), "{script}\nchecker: {checked:?}\nrecorder: {verdict:?}");
        // When a step's own form was the reason, they say the same thing about the same step.
        if let Some((Some(step), message)) = &verdict {
            let same = checked.iter().find(|(s, ..)| s == &Some(*step)).unwrap_or_else(|| panic!("{script}: {checked:?} vs {verdict:?}"));
            assert_eq!(&same.2, message, "{script}");
        }
    }
}

#[test]
fn the_kind_table_matches_the_types() {
    let schema = serde_json::to_string(&crate::tool::schema_of::<WalkthroughStep>()).unwrap();
    let parsed: Value = serde_json::from_str(&schema).unwrap();
    let kinds = step_kinds();
    let mut described = 0;
    let mut stack = vec![&parsed];
    while let Some(v) = stack.pop() {
        match v {
            Value::Object(o) => {
                if let Some(kind) = o
                    .get("properties")
                    .and_then(|p| p.get("kind"))
                    .and_then(|k| k.get("const").or_else(|| k.get("enum").and_then(|e| e.get(0))))
                    .and_then(Value::as_str)
                {
                    described += 1;
                    let (_, required, fields) =
                        kinds.iter().find(|(n, ..)| *n == kind).unwrap_or_else(|| panic!("{kind} is a step kind the checker doesn't know"));
                    for f in o["properties"].as_object().unwrap().keys() {
                        assert!(fields.contains(&f.as_str()), "{kind}: {f} isn't in the table");
                    }
                    for r in o["required"].as_array().unwrap().iter().filter_map(Value::as_str).filter(|r| *r != "kind") {
                        assert!(required.contains(&r), "{kind}: {r} is required by the type");
                    }
                }
                stack.extend(o.values());
            }
            Value::Array(a) => stack.extend(a),
            _ => {}
        }
    }
    assert_eq!(described, kinds.len(), "every kind in the table is in the types: {schema}");
    // And each table entry, given what it requires, is a step the types read as that kind.
    for (name, required, _) in &kinds {
        let mut step = json!({"kind": name});
        for r in required {
            step[*r] = if *r == "ms" { json!(1) } else { json!("x") };
        }
        if ["click", "fill", "press", "select"].contains(name) {
            step["selector"] = json!("a");
        }
        let parsed: WalkthroughStep = serde_json::from_value(step).unwrap();
        assert_eq!(action_name(&parsed.action), *name);
    }
}

#[test]
fn problems_are_structured_with_the_step_and_a_likely_fix() {
    let script = json!({"actions": [
        {"kind": "goto", "url": "https://app.test/"},
        {"step_id": "open", "kind": "clik", "selector": "a"},
        {"kind": "navigate", "url": "https://app.test/"},
        {"kind": "fill", "selector": "a", "valu": "x"},
        {"kind": "click", "selektor": "a"},
        {"kind": "wait", "ms": 999999},
        {"kind": "goto", "url": "https://a.test/", "wait_ms": 999999},
        {"step_id": "open", "kind": "wait", "ms": 1}
    ]});
    let (problems, errors, warnings, not_listed) = check_script(&script);
    assert_eq!((errors, not_listed), (4, 0), "{problems:?}");
    assert_eq!(warnings, 5, "{problems:?}");
    let find =
        |code: &str, step: usize| problems.iter().find(|p| p.code == code && p.step == Some(step)).unwrap_or_else(|| panic!("{code} at {step}: {problems:?}"));
    let clik = find("unknown_kind", 1);
    assert_eq!(clik.did_you_mean.as_deref(), Some("click"));
    assert_eq!(clik.step_id.as_deref(), Some("open"));
    assert_eq!(clik.severity, Severity::Error);
    assert_eq!(find("unknown_kind", 2).did_you_mean.as_deref(), Some("goto"), "a name from another tool");
    assert_eq!(find("missing_field", 3).field.as_deref(), Some("value"));
    assert_eq!(find("unknown_field", 3).did_you_mean.as_deref(), Some("value"));
    assert_eq!(find("bad_locator", 4).severity, Severity::Error);
    assert_eq!(find("unknown_field", 4).did_you_mean.as_deref(), Some("selector"));
    assert_eq!(find("wait_capped", 5).field.as_deref(), Some("ms"));
    assert_eq!(find("wait_capped", 6).field.as_deref(), Some("wait_ms"));
    assert_eq!(find("duplicate_step_id", 7).severity, Severity::Warning);
    assert!(!problems.iter().any(|p| p.code == "no_page_yet"), "it starts with a goto");
}

#[test]
fn a_script_with_no_first_page_gets_a_warning_unless_attaching() {
    let code = |s: &Value| check_script(s).0.iter().any(|p| p.code == "no_page_yet");
    assert!(code(&json!({"actions": [{"kind": "click", "selector": "a"}]})));
    assert!(!code(&json!({"cdp_endpoint": "http://127.0.0.1:9", "actions": [{"kind": "click", "selector": "a"}]})));
    assert!(!code(&json!({"actions": [{"kind": "wait", "ms": 1}]})));
}

#[test]
fn selector_forms() {
    for good in [
        "button",
        "#a.b > c + d ~ e",
        "a[href='x:contains(y)']",
        "a[href=\"//x\"]",
        "input[name=q]",
        "li:nth-child(2n+1)",
        "a:not(:first-child):hover",
        "a:first-of-type",
        "a:last-child",
        ":root",
        "div:has(> a)",
        "*",
        "a, b",
        "é",
        "a\\>\\>b",
        "a\\[b",
        "[data-x=\"a\\\"b\"]",
        "text",
        "input:checked",
    ] {
        assert_eq!(selector_problem(good), None, "{good}");
    }
    for bad in [
        "",
        "   ",
        "//a",
        "(//a)[1]",
        "./a",
        "xpath=//a",
        "TEXT=hi",
        "css=a",
        "a >> b",
        "a:text(x)",
        "a:visible",
        "li:eq(1)",
        "a:first",
        "(",
        ")",
        "[",
        "]",
        "a[b)",
        "'",
        "\"",
        "a\u{1}b",
        "a[x='y]",
    ] {
        assert!(selector_problem(bad).is_some(), "{bad}");
    }
    assert!(selector_problem(&"a".repeat(5000)).is_some());
    let _ = selector_problem(&"(".repeat(100_000));
    let _ = selector_problem("\\");
    let _ = selector_problem("é:é");
}

#[test]
fn hostile_scripts_are_bounded() {
    let many = vec![json!({"kind": "nope"}); 100_000];
    let (problems, errors, _, _) = check_script(&json!({"actions": many}));
    assert_eq!(errors, 201, "every step checked up to the limit, and the count itself");
    assert_eq!(problems.len(), 201);
    let long = "x".repeat(1_000_000);
    let (problems, ..) = check_script(
        &json!({"actions": [{"kind": long, "step_id": long}, {"kind": "click", "selector": long}, {"kind": "wait", "ms": 1, (long.as_str()): 1}]}),
    );
    assert!(
        problems.iter().all(|p| p.message.len() < 2000 && p.step_id.as_ref().is_none_or(|s| s.len() < 2000) && p.field.as_ref().is_none_or(|s| s.len() < 2000)),
        "{}",
        problems.len()
    );
    for odd in [json!(null), json!(3), json!("x"), json!([]), json!({"actions": null}), json!({"actions": {}}), json!({"actions": [null, [], 3]})] {
        assert!(!errors_of(&odd).is_empty(), "{odd}");
    }
}

#[test]
fn the_tool_runs_in_clean_room_and_starts_nothing() {
    assert!(crate::clean_room::allows("web_walkthrough_check"));
    let mut s = crate::testing::session();
    s.settings.deep_mode = false;
    let e = Engine::new(s);
    let good = call(&e, "web_walkthrough_check", json!({"script": {"actions": [{"kind": "goto", "url": "https://app.test/"}]}})).unwrap();
    assert_eq!(good["result"]["valid"], true, "{good}");
    assert_eq!((&good["result"]["steps"], &good["result"]["errors"]), (&json!(1), &json!(0)));
    let bare = call(&e, "web_walkthrough_check", json!({"script": [{"kind": "teleport"}]})).unwrap();
    assert_eq!(bare["result"]["valid"], false, "a bare list of steps is a script too");
    assert_eq!(bare["result"]["problems"][0]["code"], "unknown_kind");
    assert_eq!(bare["result"]["problems"][0]["step"], 0);
    assert_eq!(bare["result"]["problems"][0]["severity"], "error");
    let spec = crate::Registry::with_all_tools();
    let spec = spec.get("web_walkthrough_check").unwrap();
    assert!(!spec.effects.needs_consent() && spec.effects.read_only_hint() && !spec.effects.open_world_hint());
    assert_eq!(call(&e, "web_walkthrough_check", json!({})).unwrap_err().code, ErrorCode::BadInput);
}

#[test]
fn the_recorder_refuses_a_bad_script_before_it_needs_a_browser() {
    // No browser is listening here, so getting past these checks would fail differently.
    let e = Engine::new(crate::testing::session());
    for bad in [
        json!({"cdp_endpoint": "http://127.0.0.1:9", "actions": []}),
        json!({"cdp_endpoint": "http://127.0.0.1:9", "actions": [{"kind": "wait", "ms": 1}], "environment": {"width": 0}}),
    ] {
        assert_eq!(walkthrough(&e, bad).unwrap_err().code, ErrorCode::BadInput);
    }
}

/// #331: `limit: 0` showed one script but recorded none examined; a page shows at least one, and
/// what it examined is what it shows.
#[test]
fn coverage_records_the_scripts_it_shows() {
    let (url, _) = fake_cdp();
    let e = Engine::new(crate::testing::session());
    let run = |offset: u64, limit: u64| {
        e.call(
            "web_coverage_measure",
            json!({"cdp_endpoint": url, "watch_ms": 1, "offset": offset, "limit": limit}),
            CallOptions::new(Caller::Mcp).with_consent(crate::Consent::Granted),
        )
        .map(|o| o.to_json())
        .unwrap()
    };
    for (offset, limit, shown) in [(0, 0, 1), (0, 1, 1), (1, 1, 1), (2, 5, 1), (0, 500, 3)] {
        let v = run(offset, limit);
        assert_eq!(v["result"]["scripts_total"], 3, "{v}");
        assert_eq!(v["result"]["scripts"].as_array().map(Vec::len), Some(shown), "{offset}/{limit}");
        assert_eq!(v["coverage"]["examined"], shown, "{offset}/{limit}");
    }
}

/// A loopback server that answers every GET with `body` and records the request paths.
fn map_server(body: &'static str) -> (String, Arc<craft_anything_platform::sync::Mutex<Vec<String>>>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let origin = format!("http://127.0.0.1:{}", listener.local_addr().unwrap().port());
    let seen = Arc::new(craft_anything_platform::sync::Mutex::new(Vec::new()));
    let seen2 = seen.clone();
    std::thread::spawn(move || {
        for s in listener.incoming() {
            let Ok(mut stream) = s else { break };
            let (line, _) = read_headers(&mut stream);
            seen2.lock().unwrap().push(line.split_whitespace().nth(1).unwrap_or("").to_string());
            let resp = format!("HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len());
            let _ = stream.write_all(resp.as_bytes());
        }
    });
    (origin, seen)
}

#[test]
fn same_origin_loopback_source_maps_are_fetched() {
    const MAP: &str =
        r#"{"version":3,"file":"app.js","sources":["src/original.js"],"sourcesContent":["export const answer = 42;\n"],"names":[],"mappings":"AAAA"}"#;
    let (origin, seen) = map_server(MAP);
    // The CDP endpoint is a different loopback port from the page's origin, as in a real browser.
    let (cdp_url, _) = fake_cdp();
    let browser = super::Browser::attached(&super::cdp::parse_endpoint(&cdp_url).unwrap(), "chrome", "1");
    let dl = super::Deadline::new(std::time::Duration::from_secs(10), crate::tool::CancelToken::default());
    let script = format!("{origin}/relative.js");

    let abs = super::resolve_source_map(&browser, &format!("{origin}/app.js.map"), &script, &dl);
    assert_eq!(abs["fetched"], true, "{abs}");
    assert_eq!(abs["bytes"], MAP.len(), "{abs}");
    let rel = super::resolve_source_map(&browser, "app.js.map", &script, &dl);
    assert_eq!(rel["fetched"], true, "{rel}");
    assert_eq!(rel["bytes"], MAP.len(), "{rel}");
    assert_eq!(*seen.lock().unwrap(), vec!["/app.js.map".to_string(), "/app.js.map".to_string()]);

    // Another port, another host, or a remote https map is never requested.
    let (other, other_seen) = map_server(MAP);
    for declared in [format!("{other}/app.js.map"), "https://example.com/app.js.map".to_string(), "//example.com/app.js.map".to_string()] {
        let v = super::resolve_source_map(&browser, &declared, &script, &dl);
        assert_eq!(v["fetched"], false, "{declared}: {v}");
    }
    let remote = super::resolve_source_map(&browser, "app.js.map", "https://example.com/app.js", &dl);
    assert_eq!(remote["fetched"], false, "{remote}");
    assert!(other_seen.lock().unwrap().is_empty());
    assert_eq!(seen.lock().unwrap().len(), 2);
}
