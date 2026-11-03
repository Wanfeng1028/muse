use super::*;
use crate::{CallOptions, Caller, Engine};
use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::Duration;

fn entry(method: &str, url: &str, status: i64, body: &str) -> Value {
    json!({
        "request": {"method": method, "url": url, "headers": [{"name": "Authorization", "value": "Bearer sk-test"}]},
        "response": {
            "status": status,
            "headers": [{"name": "Set-Cookie", "value": "sid=sk-test-cookie"}, {"name": "X-Total-Count", "value": "2"}],
            "content": {"mimeType": "application/json", "text": body}
        }
    })
}

/// A hand-written recording: every value in it is an obvious fake.
fn recording(dir: &Path) -> PathBuf {
    let har = json!({"log": {"version": "1.2", "entries": [
        entry("GET", "https://api.example.test/users/1", 200, r#"{"id":1,"name":"Pat"}"#),
        entry("GET", "https://api.example.test/users/2", 200, r#"{"id":2,"name":"Sam"}"#),
        entry("GET", "https://api.example.test/poll", 200, r#"{"n":1}"#),
        entry("GET", "https://api.example.test/poll", 200, r#"{"n":2}"#),
        entry("POST", "https://api.example.test/users", 201, r#"{"id":3}"#),
        entry("GET", "https://api.example.test/gone", 404, r#"{"recorded":"not found"}"#),
    ]}});
    let path = dir.join("site.har");
    std::fs::write(&path, har.to_string()).unwrap();
    path
}

fn call(e: &Engine, id: &str, p: Value) -> Result<Value, ToolError> {
    e.call(id, p, CallOptions::new(Caller::Mcp)).map(|o| o.to_json())
}

/// Run on a thread with a time limit, so a tool that locks its own session fails instead of hanging.
fn within<T: Send + 'static>(secs: u64, f: impl FnOnce() -> T + Send + 'static) -> T {
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let _ = tx.send(f());
    });
    rx.recv_timeout(Duration::from_secs(secs)).expect("it finished in time")
}

fn http(url: &str, raw: &str) -> String {
    let port: u16 = url.rsplit(':').next().unwrap().parse().unwrap();
    let mut s = TcpStream::connect(("127.0.0.1", port)).unwrap();
    s.set_read_timeout(Some(Duration::from_secs(10))).unwrap();
    s.write_all(raw.replace("{HOST}", &format!("127.0.0.1:{port}")).as_bytes()).unwrap();
    let mut out = String::new();
    let _ = s.read_to_string(&mut out);
    out
}

fn get(url: &str, path: &str) -> String {
    http(url, &format!("GET {path} HTTP/1.1\r\nHost: {{HOST}}\r\n\r\n"))
}

#[test]
fn build_start_request_show_stop_through_the_engine() {
    within(60, || {
        let dir = crate::testing::temp_dir();
        let har = recording(&dir);
        let out = dir.join("standin");
        let e = Engine::new(crate::testing::session());

        let built = call(&e, "web_standin_build", json!({"path": har, "output_dir": out})).unwrap();
        let r = &built["result"];
        assert_eq!(r["routes_total"], 4, "{r}");
        assert!(r["routes"].as_array().unwrap().iter().any(|x| x["template"] == "/users/{id}" && x["method"] == "GET"), "{r}");
        assert_eq!(r["dropped"]["headers"], 12, "two on each of six entries");
        let codes: Vec<&str> = built["limitations"].as_array().unwrap().iter().filter_map(|l| l["code"].as_str()).collect();
        assert!(codes.contains(&"only_what_was_recorded") && codes.contains(&"read_only_replay") && codes.contains(&"secrets_dropped"), "{codes:?}");

        let written = std::fs::read_to_string(standin_file(&out)).unwrap();
        assert!(!written.contains("sk-test"), "{written}");
        assert!(!built.to_string().contains("sk-test"), "{built}");

        let started = call(&e, "web_standin_start", json!({"path": out})).unwrap();
        let url = started["result"]["url"].as_str().unwrap().to_string();
        let id = started["result"]["id"].as_str().unwrap().to_string();
        assert!(url.starts_with("http://127.0.0.1:"), "{url}");

        // An exact path, a path by template, and answers in recorded order.
        let one = get(&url, "/users/1");
        assert!(one.starts_with("HTTP/1.1 200") && one.contains("Pat") && one.contains("application/json") && one.contains("X-Total-Count: 2"), "{one}");
        assert!(one.contains("X-Craft-Anything-Stand-In: recorded") && !one.contains("sk-test"), "{one}");
        assert!(get(&url, "/users/77").contains("Pat"), "the template's first answer");
        assert!(get(&url, "/poll").contains(r#"{"n":1}"#));
        assert!(get(&url, "/poll").contains(r#"{"n":2}"#));
        assert!(get(&url, "/poll").contains(r#"{"n":1}"#), "and round again");
        // A recorded 404 is the original's answer.
        let gone = get(&url, "/gone");
        assert!(gone.starts_with("HTTP/1.1 404") && gone.contains("X-Craft-Anything-Stand-In: recorded") && gone.contains("not found"), "{gone}");
        // A write replays and changes nothing.
        let post = http(&url, "POST /users HTTP/1.1\r\nHost: {HOST}\r\nContent-Length: 2\r\n\r\n{}");
        assert!(post.starts_with("HTTP/1.1 201") && post.contains(r#"{"id":3}"#), "{post}");
        assert!(get(&url, "/users/2").contains("Sam"));

        // Nothing recorded: a structured 404 with the nearest routes.
        let no = get(&url, "/users/1/orders?token=sk-test-asked&page=1");
        assert!(no.starts_with("HTTP/1.1 404") && no.contains("X-Craft-Anything-Stand-In: no-recorded-answer"), "{no}");
        let body: Value = serde_json::from_str(no.split("\r\n\r\n").nth(1).unwrap()).unwrap();
        assert_eq!(body["error"], "no_recorded_answer");
        assert_eq!(body["reason"], "path_not_recorded");
        assert_eq!(body["nearest"][0]["template"], "/users/{id}");
        let _ = get(&url, "/users/1/orders");

        // The tool that reads these doesn't wait on anything the server holds, and vice versa.
        let shown = call(&e, "web_standin_show", json!({})).unwrap();
        let s = &shown["result"];
        assert_eq!(s["servers"][0]["id"], id.as_str());
        assert_eq!(s["servers"][0]["requests_answered"], 8, "{s}");
        assert_eq!(s["servers"][0]["requests_with_no_answer"], 2, "{s}");
        assert_eq!(s["servers"][0]["routes"], 4);
        let row = &s["no_answer"]["items"][0];
        assert_eq!((&row["method"], &row["path"], &row["times"]), (&json!("GET"), &json!("/users/1/orders"), &json!(2)), "{row}");
        assert_eq!(row["nearest"][0]["template"], "/users/{id}");
        assert_eq!(row["query_names"], json!(["token", "page"]));
        assert!(!shown.to_string().contains("sk-test"), "query values aren't logged: {shown}");
        assert!(s["answered_routes"].as_array().unwrap().iter().any(|x| x["route"] == "GET /poll" && x["times"] == 3), "{s}");

        let stopped = call(&e, "web_standin_stop", json!({"id": id})).unwrap();
        assert_eq!(stopped["result"]["stopped"][0]["requests_answered"], 8);
        // That its port is freed is tested where the server is (`dropping_a_server_frees_its_port`):
        // here, among tests that all take free ports, another one may be handed it at once.
        assert_eq!(call(&e, "web_standin_show", json!({})).unwrap()["result"]["servers"], json!([]));
    });
}

#[test]
fn starting_twice_reuses_and_a_session_ending_stops_it() {
    within(60, || {
        let dir = crate::testing::temp_dir();
        let e = Engine::new(crate::testing::session());
        let out = dir.join("s");
        call(&e, "web_standin_build", json!({"path": recording(&dir), "output_dir": out})).unwrap();
        let a = call(&e, "web_standin_start", json!({"path": out})).unwrap();
        let b = call(&e, "web_standin_start", json!({"path": standin_file(&out)})).unwrap();
        assert_eq!(a["result"]["url"], b["result"]["url"]);
        assert_eq!(b["result"]["already_running"], true);
        let url = a["result"]["url"].as_str().unwrap().to_string();
        assert!(get(&url, "/users/1").contains("Pat"));
        let port: u16 = url.rsplit(':').next().unwrap().parse().unwrap();
        drop(e);
        let until = std::time::Instant::now() + Duration::from_secs(5);
        while TcpStream::connect(("127.0.0.1", port)).is_ok() {
            assert!(std::time::Instant::now() < until, "ending the session stops it");
            std::thread::sleep(Duration::from_millis(20));
        }
    });
}

#[test]
fn a_chosen_port_and_stopping_several() {
    within(60, || {
        let dir = crate::testing::temp_dir();
        let e = Engine::new(crate::testing::session());
        let (one, two) = (dir.join("one"), dir.join("two"));
        for out in [&one, &two] {
            call(&e, "web_standin_build", json!({"path": recording(&dir), "output_dir": out})).unwrap();
        }
        // A port that's free right now.
        let free = std::net::TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
        let a = call(&e, "web_standin_start", json!({"path": one, "port": free})).unwrap();
        assert_eq!(a["result"]["url"], format!("http://127.0.0.1:{free}"));
        let in_use = call(&e, "web_standin_start", json!({"path": two, "port": free})).unwrap_err();
        assert!(in_use.remediation.as_deref().unwrap_or_default().contains("port"), "{in_use:?}");
        call(&e, "web_standin_start", json!({"path": two})).unwrap();
        let which = call(&e, "web_standin_stop", json!({})).unwrap_err();
        assert_eq!(which.code, ErrorCode::BadInput, "it won't guess which");
        assert_eq!(call(&e, "web_standin_stop", json!({"id": "standin-99"})).unwrap_err().code, ErrorCode::NotFound);
        assert_eq!(call(&e, "web_standin_show", json!({"id": "standin-99"})).unwrap_err().code, ErrorCode::NotFound);
        assert_eq!(call(&e, "web_standin_stop", json!({"id": "standin-1", "all": true})).unwrap_err().code, ErrorCode::BadInput);
        assert_eq!(call(&e, "web_standin_stop", json!({"all": true})).unwrap()["result"]["stopped"].as_array().unwrap().len(), 2);
        assert_eq!(call(&e, "web_standin_stop", json!({})).unwrap()["result"]["stopped"], json!([]), "nothing left is not an error");
    });
}

#[test]
fn waiting_keeps_it_running_until_cancelled_then_stops_it() {
    within(60, || {
        let dir = crate::testing::temp_dir();
        let e = Arc::new(Engine::new(crate::testing::session()));
        let out = dir.join("s");
        call(&e, "web_standin_build", json!({"path": recording(&dir), "output_dir": out})).unwrap();
        let port = std::net::TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
        let cancel = crate::CancelToken::default();
        let (engine, token) = (e.clone(), cancel.clone());
        let waiting = std::thread::spawn(move || {
            engine
                .call("web_standin_start", json!({"path": out, "port": port, "wait": true}), CallOptions::new(Caller::Cli).with_cancel(token))
                .map(|o| o.to_json())
        });
        let url = format!("http://127.0.0.1:{port}");
        let until = std::time::Instant::now() + Duration::from_secs(20);
        while TcpStream::connect(("127.0.0.1", port)).is_err() {
            assert!(std::time::Instant::now() < until, "it starts listening");
            std::thread::sleep(Duration::from_millis(20));
        }
        // It answers while the call that started it is still going: answering needs no session.
        assert!(get(&url, "/users/1").contains("Pat"));
        assert!(!waiting.is_finished());
        cancel.cancel();
        let done = waiting.join().unwrap().unwrap();
        assert_eq!(done["result"]["stopped"]["requests_answered"], 1, "{done}");
        assert!(TcpStream::connect(("127.0.0.1", port)).is_err(), "and it's gone");
        assert_eq!(call(&e, "web_standin_show", json!({})).unwrap()["result"]["servers"], json!([]));
    });
}

#[test]
fn missing_requests_page_most_asked_first_and_stay_bounded() {
    within(60, || {
        let dir = crate::testing::temp_dir();
        let e = Engine::new(crate::testing::session());
        let out = dir.join("s");
        call(&e, "web_standin_build", json!({"path": recording(&dir), "output_dir": out})).unwrap();
        let url = call(&e, "web_standin_start", json!({"path": out})).unwrap()["result"]["url"].as_str().unwrap().to_string();
        for _ in 0..3 {
            get(&url, "/asked/a-lot");
        }
        get(&url, "/asked/once");
        get(&url, "/asked/also-once");
        let page = call(&e, "web_standin_show", json!({"limit": 2})).unwrap();
        let n = &page["result"]["no_answer"];
        assert_eq!(n["total"], 3);
        assert_eq!(n["items"][0]["path"], "/asked/a-lot");
        assert_eq!(n["items"].as_array().unwrap().len(), 2);
        assert_eq!(n["next_offset"], 2);
        let rest = call(&e, "web_standin_show", json!({"limit": 2, "offset": 2})).unwrap();
        assert_eq!(rest["result"]["no_answer"]["items"].as_array().unwrap().len(), 1);
        assert!(rest["result"]["no_answer"]["next_offset"].is_null());
        assert_eq!(call(&e, "web_standin_show", json!({"offset": 99})).unwrap()["result"]["no_answer"]["items"], json!([]));
    });
}

#[test]
fn the_log_of_unanswered_requests_cannot_grow_without_end() {
    let replay = Replay { standin: StandIn::default(), state: Mutex::default() };
    let long = "x".repeat(10_000);
    for i in 0..(MAX_MISSING + 25) {
        let r = Request { method: "GET".into(), path: format!("/{i}/{long}"), query: String::new(), body: Vec::new() };
        assert_eq!(replay.answer(&r).status, 404);
    }
    let guard = replay.state.lock().unwrap();
    assert_eq!(guard.1.missing.len(), MAX_MISSING);
    assert_eq!(guard.1.missing_not_listed, 25);
    assert_eq!(guard.1.no_answer, (MAX_MISSING + 25) as u64);
    assert!(guard.1.missing.keys().all(|(_, p)| p.len() <= MAX_LOGGED_PATH + "…".len()));
}

#[test]
fn secret_shaped_paths_are_not_logged() {
    let replay = Replay { standin: StandIn::default(), state: Mutex::default() };
    let r = Request { method: "GET".into(), path: "/reset/sk-test-in-a-path-1234/done".into(), query: String::new(), body: b"sk-test-in-a-body-1234".to_vec() };
    let response = replay.answer(&r);
    assert!(!String::from_utf8_lossy(&response.body).contains("sk-test"));
    let guard = replay.state.lock().unwrap();
    assert!(guard.1.missing.keys().all(|(_, p)| p == "/reset/{id}/done"), "{:?}", guard.1.missing.keys());
}

#[test]
fn bad_inputs_are_plain_errors() {
    within(60, || {
        let dir = crate::testing::temp_dir();
        let e = Engine::new(crate::testing::session());
        let har = recording(&dir);
        assert_eq!(call(&e, "web_standin_build", json!({"path": "relative.har", "output_dir": dir})).unwrap_err().code, ErrorCode::BadInput);
        assert_eq!(call(&e, "web_standin_build", json!({"path": har, "output_dir": "relative"})).unwrap_err().code, ErrorCode::BadInput);
        assert!(call(&e, "web_standin_build", json!({"path": dir.join("missing.har"), "output_dir": dir})).is_err());
        let not_har = dir.join("x.har");
        std::fs::write(&not_har, "{}").unwrap();
        assert_eq!(call(&e, "web_standin_build", json!({"path": not_har, "output_dir": dir})).unwrap_err().code, ErrorCode::GarbledOutput);
        assert!(!standin_file(&dir).exists(), "nothing is written for a bad recording");
        assert_eq!(call(&e, "web_standin_start", json!({"path": dir.join("none")})).unwrap_err().code, ErrorCode::NotFound);
        let bad = dir.join("bad.json");
        std::fs::write(&bad, "not json").unwrap();
        assert_eq!(call(&e, "web_standin_start", json!({"path": bad})).unwrap_err().code, ErrorCode::GarbledOutput);
    });
}

#[test]
fn file_versions() {
    assert_eq!(parse_standin(br#"{"version": 1, "routes": []}"#).unwrap().version, STANDIN_VERSION);
    for bad in [&br#"{"routes": []}"#[..], br#"{"version": "1"}"#, br#"{"version": 0}"#, br#"{"version": -1}"#, br#"{"version": 99999999999}"#, b"[]", b""] {
        assert_eq!(parse_standin(bad).unwrap_err().code, ErrorCode::GarbledOutput, "{}", String::from_utf8_lossy(bad));
    }
    let newer = parse_standin(br#"{"version": 2, "routes": [], "from_the_future": true}"#).unwrap_err();
    assert_eq!(newer.code, ErrorCode::NotSupported);
    assert!(newer.remediation.as_deref().unwrap_or_default().contains("Update Craft Anything"), "{newer:?}");
}

#[test]
fn a_newer_file_is_not_written_over() {
    let dir = crate::testing::temp_dir();
    let e = Engine::new(crate::testing::session());
    let har = recording(&dir);
    let newer = r#"{"version": 2, "theirs": true}"#;
    std::fs::write(standin_file(&dir), newer).unwrap();
    assert_eq!(call(&e, "web_standin_build", json!({"path": har, "output_dir": dir})).unwrap_err().code, ErrorCode::NotSupported);
    assert_eq!(std::fs::read_to_string(standin_file(&dir)).unwrap(), newer);
}

#[test]
fn named_values_stay_out_of_the_file_and_the_evidence() {
    let dir = crate::testing::temp_dir();
    let e = Engine::new(crate::testing::session());
    let out = dir.join("s");
    let built = call(&e, "web_standin_build", json!({"path": recording(&dir), "output_dir": out, "hidden_values": ["Pat"]})).unwrap();
    assert!(!built.to_string().contains("Pat"), "{built}");
    assert!(!std::fs::read_to_string(standin_file(&out)).unwrap().contains("Pat"));
    assert!(built["result"]["dropped"]["hidden_values"].as_u64().unwrap() >= 1);
}

#[test]
fn the_routes_page() {
    let dir = crate::testing::temp_dir();
    let e = Engine::new(crate::testing::session());
    let out = dir.join("s");
    let built = call(&e, "web_standin_build", json!({"path": recording(&dir), "output_dir": out, "limit": 1, "offset": 1})).unwrap();
    assert_eq!(built["result"]["routes"].as_array().unwrap().len(), 1);
    assert_eq!(built["result"]["routes_total"], 4);
    assert_eq!(built["coverage"]["next_offset"], 2);
}

#[test]
fn these_need_deep_mode() {
    for id in ["web_standin_build", "web_standin_start", "web_standin_stop", "web_standin_show"] {
        assert!(!crate::clean_room::allows(id), "{id}");
    }
    let mut s = crate::testing::session();
    s.settings.deep_mode = false;
    let e = Engine::new(s);
    let refused = call(&e, "web_standin_show", json!({})).unwrap_err();
    assert!(crate::clean_room::is_refusal(&refused), "{refused:?}");
}

#[test]
fn starting_a_rebuilt_stand_in_answers_from_the_new_file() {
    within(60, || {
        let dir = tempfile::tempdir().unwrap();
        let e = Engine::new(crate::testing::session());
        let out = dir.path().join("out");
        let har = recording(dir.path());
        call(&e, "web_standin_build", json!({"path": har, "output_dir": out})).unwrap();
        let first = call(&e, "web_standin_start", json!({"path": out})).unwrap();
        let (id, url) = (first["result"]["id"].clone(), first["result"]["url"].as_str().unwrap().to_string());
        assert!(!http(&url, "GET /added HTTP/1.1\r\nHost: {HOST}\r\nConnection: close\r\n\r\n").contains("from the new recording"));
        assert_eq!(call(&e, "web_standin_start", json!({"path": out})).unwrap()["result"]["already_running"], true, "the file hasn't changed");

        let newer =
            json!({"log": {"version": "1.2", "entries": [entry("GET", "https://api.example.test/added", 200, r#"{"note":"from the new recording"}"#)]}});
        let har2 = dir.path().join("newer.har");
        std::fs::write(&har2, newer.to_string()).unwrap();
        call(&e, "web_standin_build", json!({"path": har2, "output_dir": out})).unwrap();
        let second = call(&e, "web_standin_start", json!({"path": out})).unwrap();
        assert_eq!(second["result"]["already_running"], false);
        assert_eq!(second["result"]["replaced"], id);
        assert_eq!(second["result"]["url"].as_str().unwrap(), url, "the address the front end has keeps working");
        assert!(http(&url, "GET /added HTTP/1.1\r\nHost: {HOST}\r\nConnection: close\r\n\r\n").contains("from the new recording"));

        // A broken file leaves what's running alone.
        std::fs::write(standin_file(&out), "not a stand-in").unwrap();
        assert!(call(&e, "web_standin_start", json!({"path": out})).is_err());
        assert!(http(&url, "GET /added HTTP/1.1\r\nHost: {HOST}\r\nConnection: close\r\n\r\n").contains("from the new recording"));
        call(&e, "web_standin_stop", json!({"all": true})).unwrap();
    });
}

#[test]
fn effects_are_honest() {
    let r = crate::Registry::with_all_tools();
    let start = r.get("web_standin_start").unwrap();
    assert!(start.effects.contains(Effects::ACCESSES_NETWORK) && start.effects.contains(Effects::MUTATES_SESSION));
    assert!(!start.effects.needs_consent(), "it runs nothing from the recording and changes no device");
    assert!(!start.effects.contains(Effects::IDEMPOTENT) && !start.effects.read_only_hint());
    let build = r.get("web_standin_build").unwrap();
    assert!(build.effects.contains(Effects::WRITES_FILESYSTEM) && build.effects.contains(Effects::CARRIES_TARGET_CONTENT));
    assert!(r.get("web_standin_show").unwrap().effects.contains(Effects::CARRIES_TARGET_CONTENT));
}

/// A rebuilt stand-in takes over its predecessor's port even while the system holds it a moment
/// longer; a new one doesn't wait (seen in CI as "Address already in use").
#[test]
fn a_takeover_waits_for_its_port_and_a_new_start_does_not() {
    let held = std::net::TcpListener::bind(("127.0.0.1", 0)).unwrap();
    let port = held.local_addr().unwrap().port();
    let answerer: Arc<dyn Answerer> = Arc::new(|_: &Request| Response::json(200, &json!({})));
    let err = serve_on(port, answerer.clone(), Duration::ZERO).map(|_| ()).unwrap_err();
    assert_eq!(err.kind(), std::io::ErrorKind::AddrInUse);
    let release = std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(300));
        drop(held);
    });
    let server = serve_on(port, answerer, TAKEOVER_WAIT).unwrap();
    assert_eq!(server.port, port);
    release.join().unwrap();
}
