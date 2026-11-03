use super::*;
use serde_json::json;

/// One entry: method, URL, status, JSON or text body.
fn entry(method: &str, url: &str, status: i64, body: &str) -> Value {
    json!({
        "request": {"method": method, "url": url, "headers": []},
        "response": {"status": status, "headers": [], "content": {"mimeType": "application/json", "text": body}}
    })
}

fn har_of(entries: Vec<Value>) -> Vec<u8> {
    serde_json::to_vec(&json!({"log": {"version": "1.2", "entries": entries}})).unwrap()
}

fn built(entries: Vec<Value>) -> StandIn {
    build_from_bytes(&har_of(entries), &BuildOptions::default()).unwrap()
}

fn templates(s: &StandIn) -> Vec<String> {
    s.routes.iter().map(|r| format!("{} {}", r.method, r.template)).collect()
}

fn found(a: Answer) -> Found {
    match a {
        Answer::Found(f) => *f,
        Answer::NoMatch(n) => panic!("no match: {n:?}"),
    }
}

fn missing(a: Answer) -> NoMatch {
    match a {
        Answer::NoMatch(n) => n,
        Answer::Found(f) => panic!("found: {f:?}"),
    }
}

fn get(s: &StandIn, t: &mut Turns, path: &str, query: &str) -> Answer {
    answer(s, t, "GET", path, query, b"")
}

fn body(f: &Found) -> String {
    String::from_utf8_lossy(&f.body).into_owned()
}

const A: &str = "https://api.example.test";

// ---- templates ----

#[test]
fn numeric_ids_uuids_and_long_hex_become_id() {
    let s = built(vec![
        entry("GET", &format!("{A}/users/42"), 200, "{}"),
        entry("GET", &format!("{A}/users/43"), 200, "{}"),
        entry("GET", &format!("{A}/orders/550e8400-e29b-41d4-a716-446655440000/items"), 200, "{}"),
        entry("GET", &format!("{A}/blobs/0123456789abcdef0123"), 200, "{}"),
        entry("GET", &format!("{A}/files/a1b2c3d4e5f6g7h8i9j0k1"), 200, "{}"),
    ]);
    assert_eq!(templates(&s), ["GET /blobs/{id}", "GET /files/{id}", "GET /orders/{id}/items", "GET /users/{id}"]);
    assert_eq!(s.routes[3].requests, 2);
}

#[test]
fn id_shapes() {
    for id in ["1", "0042", "550e8400-e29b-41d4-a716-446655440000", "0123456789abcdef", "a1b2c3d4e5f6g7h8i9j0"] {
        assert!(is_id_segment(id), "{id}");
    }
    for word in ["", "users", "v1", "facade", "decade", "deadbeef", "abcdefabcdefabcdefabcdef", "user-profile-settings-page", "item.json", "2fa", "oauth2"] {
        assert!(!is_id_segment(word), "{word}");
    }
}

#[test]
fn different_collections_are_not_merged() {
    let shape = r#"[{"id":1}]"#;
    let s = built(vec![
        entry("GET", &format!("{A}/users"), 200, shape),
        entry("GET", &format!("{A}/posts"), 200, shape),
        entry("GET", &format!("{A}/tags"), 200, shape),
        entry("GET", &format!("{A}/api/users"), 200, shape),
        entry("GET", &format!("{A}/api/posts"), 200, shape),
        entry("GET", &format!("{A}/api/tags"), 200, shape),
        entry("GET", &format!("{A}/v1/users"), 200, shape),
        entry("GET", &format!("{A}/v1/posts"), 200, shape),
        entry("GET", &format!("{A}/v1/tags"), 200, shape),
        entry("GET", &format!("{A}/api/users/list"), 200, shape),
        entry("GET", &format!("{A}/api/posts/list"), 200, shape),
    ]);
    assert_eq!(s.routes.len(), 11, "{:?}", templates(&s));
    assert!(s.routes.iter().all(|r| !r.template.contains(ID)), "{:?}", templates(&s));
}

#[test]
fn word_like_values_merge_when_the_recording_shows_they_vary() {
    let user = |name: &str| entry("GET", &format!("{A}/users/{name}"), 200, r#"{"name":"x","bio":"y"}"#);
    let s = built(vec![user("alice"), user("bob"), user("carol")]);
    assert_eq!(templates(&s), ["GET /users/{id}"]);
    // Text after them is stronger evidence: two are enough.
    let s = built(vec![entry("GET", &format!("{A}/users/alice/posts"), 200, "[]"), entry("GET", &format!("{A}/users/bob/posts"), 200, "[]")]);
    assert_eq!(templates(&s), ["GET /users/{id}/posts"]);
}

#[test]
fn siblings_that_answer_differently_stay_apart() {
    let s = built(vec![
        entry("GET", &format!("{A}/shop/cart"), 200, r#"{"items":[]}"#),
        entry("GET", &format!("{A}/shop/orders"), 200, r#"{"orders":[]}"#),
        entry("GET", &format!("{A}/shop/account"), 200, r#"{"email":"x"}"#),
    ]);
    assert_eq!(s.routes.len(), 3, "{:?}", templates(&s));
    // Two values aren't enough without text after them, and no JSON says nothing about shape.
    let s = built(vec![entry("GET", &format!("{A}/shop/a"), 200, r#"{"x":1}"#), entry("GET", &format!("{A}/shop/b"), 200, r#"{"x":1}"#)]);
    assert_eq!(s.routes.len(), 2);
    let s = built(vec![entry("GET", &format!("{A}/p/a"), 200, "x"), entry("GET", &format!("{A}/p/b"), 200, "x"), entry("GET", &format!("{A}/p/c"), 200, "x")]);
    assert_eq!(s.routes.len(), 3);
}

#[test]
fn procedure_names_and_file_names_are_not_ids() {
    let s = built(vec![
        entry("GET", &format!("{A}/trpc/post.list"), 200, r#"{"a":1}"#),
        entry("GET", &format!("{A}/trpc/post.get"), 200, r#"{"a":1}"#),
        entry("GET", &format!("{A}/trpc/user.get"), 200, r#"{"a":1}"#),
        entry("GET", &format!("{A}/data/a.json"), 200, r#"{"a":1}"#),
        entry("GET", &format!("{A}/data/b.json"), 200, r#"{"a":1}"#),
        entry("GET", &format!("{A}/data/c.json"), 200, r#"{"a":1}"#),
    ]);
    assert_eq!(s.routes.len(), 6, "{:?}", templates(&s));
}

#[test]
fn a_literal_sibling_of_an_id_route_stays_literal() {
    let s = built(vec![entry("GET", &format!("{A}/users/1"), 200, r#"{"id":1}"#), entry("GET", &format!("{A}/users/search"), 200, r#"{"results":[]}"#)]);
    assert_eq!(templates(&s), ["GET /users/search", "GET /users/{id}"]);
    let mut t = Turns::default();
    assert!(body(&found(get(&s, &mut t, "/users/search", ""))).contains("results"));
    assert!(body(&found(get(&s, &mut t, "/users/9", ""))).contains("id"));
}

#[test]
fn methods_are_separate_routes() {
    let s = built(vec![entry("GET", &format!("{A}/items/1"), 200, r#"{"a":1}"#), entry("delete", &format!("{A}/items/1"), 204, "")]);
    assert_eq!(templates(&s), ["DELETE /items/{id}", "GET /items/{id}"]);
}

#[test]
fn routes_note_statuses_types_query_names_and_hosts() {
    let mut other = entry("GET", "https://b.example.test/items/2?page=1&sort=asc", 404, "{}");
    other["response"]["content"]["mimeType"] = json!("application/problem+json");
    let s = built(vec![entry("GET", &format!("{A}/items/1?page=2"), 200, "{}"), other]);
    assert_eq!(s.routes.len(), 1);
    let r = &s.routes[0];
    assert_eq!(r.statuses, [200, 404]);
    assert_eq!(r.content_types, ["application/json", "application/problem+json"]);
    assert_eq!(r.query_names, ["page", "sort"]);
    assert_eq!(r.hosts, ["api.example.test", "b.example.test"]);
    assert_eq!(s.hosts, r.hosts);
    assert_eq!(s.version, STANDIN_VERSION);
}

// ---- secrets ----

/// A recording with secrets in every place one can be. Everything in it is an obvious fake.
fn secret_recording() -> Vec<u8> {
    har_of(vec![json!({
        "request": {
            "method": "POST",
            "url": "https://user:hunter2-fake@api.example.test/session/eyJhbGciOiJub25lIn0.eyJzdWIiOiJ4In0.c2ln?token=query-token-fake&page=1&access_token=query-access-fake&note=sk-test-in-query-1234",
            "headers": [
                {"name": "Cookie", "value": "sid=request-cookie-fake"},
                {"name": "Authorization", "value": "Bearer request-bearer-fake"},
                {"name": "X-Api-Key", "value": "sk-test"},
                {"name": "Accept", "value": "application/json"}
            ],
            "cookies": [{"name": "sid", "value": "request-cookie-fake"}],
            "postData": {"mimeType": "application/json", "text": "{\"password\":\"request-password-fake\",\"email\":\"person@example.test\"}"}
        },
        "response": {
            "status": 200,
            "headers": [
                {"name": "Set-Cookie", "value": "sid=response-cookie-fake; HttpOnly"},
                {"name": "Authorization", "value": "Bearer response-bearer-fake"},
                {"name": "X-CSRF-Token", "value": "csrf-fake"},
                {"name": "X-Session-Thing", "value": "session-thing-fake"},
                {"name": "X-Custom", "value": "carries sk-test-header-value-1234"},
                {"name": "Location", "value": "/next?token=location-token-fake&ok=1"},
                {"name": "X-Total-Count", "value": "12"}
            ],
            "cookies": [{"name": "sid", "value": "response-cookie-fake"}],
            "content": {"mimeType": "application/json", "text": "{\"access_token\":\"body-token-fake\",\"refreshToken\":\"body-refresh-fake\",\"profile\":{\"password\":\"body-password-fake\",\"name\":\"Pat\",\"note\":\"Bearer body-bearer-value-fake\",\"jwt\":\"eyJhbGciOiJub25lIn0.eyJzdWIiOiJ5In0.c2ln\",\"gh\":\"ghp_fakefakefakefake\"},\"sk-test-as-a-key-1234\":1,\"key\":\"react-key\",\"code\":\"GB\",\"max_tokens\":5}"}
        }
    })])
}

const FAKES: &[&str] = &[
    "hunter2-fake",
    "eyJhbGciOiJub25lIn0",
    "query-token-fake",
    "query-access-fake",
    "sk-test",
    "request-cookie-fake",
    "request-bearer-fake",
    "request-password-fake",
    "person@example.test",
    "response-cookie-fake",
    "response-bearer-fake",
    "csrf-fake",
    "session-thing-fake",
    "location-token-fake",
    "body-token-fake",
    "body-refresh-fake",
    "body-password-fake",
    "body-bearer-value-fake",
    "ghp_fakefakefakefake",
];

#[test]
fn no_secret_reaches_the_file() {
    let s = build_from_bytes(&secret_recording(), &BuildOptions::default()).unwrap();
    let text = serde_json::to_string(&s).unwrap();
    for fake in FAKES {
        assert!(!text.contains(fake), "{fake} is in the file: {text}");
    }
    let kept: Vec<String> = s.routes.iter().flat_map(|r| &r.samples).flat_map(|x| &x.headers).map(|(k, _)| k.to_ascii_lowercase()).collect();
    assert_eq!(kept, ["location", "x-total-count"], "{text}");
    let d = &s.dropped;
    assert_eq!(d.headers, 8, "{d:?}");
    assert_eq!(d.cookies, 2);
    assert_eq!(d.url_user_info, 1);
    assert_eq!(d.path_segments, 1);
    assert_eq!(d.query_values, 4, "three in the URL and one in the redirect: {d:?}");
    assert!(d.body_values >= 6, "{d:?}");
    assert!(d.total() > 15);
    for name in ["cookie", "authorization", "x-api-key", "set-cookie", "x-csrf-token", "x-custom"] {
        assert!(d.header_names.iter().any(|n| n == name), "{name}: {:?}", d.header_names);
    }
}

#[test]
fn everyday_values_survive_the_secret_checks() {
    let s = build_from_bytes(&secret_recording(), &BuildOptions::default()).unwrap();
    let sample = &s.routes[0].samples[0];
    let v: Value = serde_json::from_str(sample.text.as_deref().unwrap()).unwrap();
    assert_eq!(v["profile"]["name"], "Pat");
    assert_eq!(v["key"], "react-key", "`key` and `code` are everyday names in a body");
    assert_eq!(v["code"], "GB");
    assert_eq!(v["max_tokens"], 5);
    assert_eq!(v["access_token"], DROPPED);
    assert!(sample.headers.iter().any(|(k, v)| k == "X-Total-Count" && v == "12"));
    let location = sample.headers.iter().find(|(k, _)| k == "Location").unwrap();
    assert!(location.1.contains("ok=1") && location.1.contains(DROPPED), "{location:?}");
}

#[test]
fn a_recorded_secret_query_still_matches_a_request_with_any_value_there() {
    let s = built(vec![entry("GET", &format!("{A}/feed?token=recorded-fake&page=1"), 200, r#"{"a":1}"#)]);
    let mut t = Turns::default();
    let f = found(get(&s, &mut t, "/feed", "page=1&token=something-else"));
    assert_eq!(f.how, MatchKind::PathAndQuery);
}

#[test]
fn named_values_are_dropped_in_every_spelling() {
    let secret = "my secret/value";
    let mut e = entry("GET", &format!("{A}/a/my%20secret%2Fvalue/b?x=my+secret/value"), 200, "");
    e["response"]["content"]["text"] = json!(format!("{{\"say\":\"{secret}\"}}"));
    e["response"]["headers"] = json!([{"name": "X-Thing", "value": secret}]);
    let opts = BuildOptions { hidden_values: vec![secret.into()], ..Default::default() };
    let s = build_from_bytes(&har_of(vec![e]), &opts).unwrap();
    let text = serde_json::to_string(&s).unwrap();
    for spelling in [secret, "my%20secret", "my+secret"] {
        assert!(!text.contains(spelling), "{spelling}: {text}");
    }
    assert!(s.dropped.hidden_values >= 3, "{:?}", s.dropped);
}

#[test]
fn a_named_value_inside_a_binary_body_costs_the_body() {
    // "\xff" keeps it from being text; the rest is the named value.
    let encoded = "/3N0b3AtcGxlYXNl";
    assert_eq!(base64_decode(encoded).unwrap(), b"\xffstop-please");
    let mut e = entry("GET", &format!("{A}/bin"), 200, "");
    e["response"]["content"] = json!({"mimeType": "application/octet-stream", "encoding": "base64", "text": encoded});
    let har = har_of(vec![e]);
    let opts = BuildOptions { hidden_values: vec!["stop-please".into()], ..Default::default() };
    let s = build_from_bytes(&har, &opts).unwrap();
    assert_eq!(s.routes[0].samples[0].body_left_out, Some(BodyLeftOut::HeldSecret));
    assert!(s.routes[0].samples[0].base64.is_none());
    let plain = build_from_bytes(&har, &BuildOptions::default()).unwrap();
    assert_eq!(plain.routes[0].samples[0].base64.as_deref(), Some(encoded));
    assert_eq!(found(get(&plain, &mut Turns::default(), "/bin", "")).body, b"\xffstop-please");
}

#[test]
fn private_keys_cost_the_whole_body() {
    // Put together here so that no key-shaped text sits in the repository.
    let (begin, finish) = (format!("-----BEGIN RSA {} KEY-----", "PRIVATE"), format!("-----END RSA {} KEY-----", "PRIVATE"));
    let s = built(vec![entry("GET", &format!("{A}/k"), 200, &format!("{begin}\nfake\n{finish}"))]);
    assert_eq!(s.routes[0].samples[0].body_left_out, Some(BodyLeftOut::HeldSecret));
    assert!(!serde_json::to_string(&s).unwrap().contains("KEY-----"));
}

/// The first recorded answer's text for a body of this type.
fn cleaned(mime: &str, body: &str) -> (String, u64) {
    let mut e = entry("GET", &format!("{A}/page"), 200, body);
    e["response"]["content"]["mimeType"] = json!(mime);
    let opts = BuildOptions { include_static: true, ..BuildOptions::default() };
    let s = build_from_bytes(&har_of(vec![e]), &opts).unwrap();
    (s.routes[0].samples[0].text.clone().unwrap(), s.dropped.body_values)
}

#[test]
fn secrets_inside_urls_and_pairs_go_and_the_rest_stays() {
    let (text, n) =
        cleaned("application/json", r#"{"next":"https://x.example/cb?ref=ghp_fakefakefakefake","hook":"https://x.example/sk_live_fakefake1234/run"}"#);
    assert!(!text.contains("ghp_") && !text.contains("sk_live_"), "{text}");
    assert!(text.contains("ref=[dropped]") && text.contains("//x.example/[dropped]/run"), "{text}");
    assert_eq!(n, 2);
}

#[test]
fn a_url_keeps_its_host_and_loses_its_user_info() {
    for (mime, body) in
        [("text/plain", "see https://bob:hunter2@internal.example/app for it"), ("application/json", r#"{"u":"https://bob:hunter2@internal.example/app"}"#)]
    {
        let mut e = entry("GET", &format!("{A}/page"), 200, body);
        e["response"]["content"]["mimeType"] = json!(mime);
        let s = built(vec![e]);
        let text = s.routes[0].samples[0].text.as_deref().unwrap();
        assert!(!text.contains("hunter2") && !text.contains("bob") && text.contains("https://internal.example/app"), "{text}");
        assert_eq!(s.dropped.url_user_info, 1);
    }
    let (kept, _) = cleaned("text/plain", "mail pat@example.test or see https://example.test/a@b ok");
    assert_eq!(kept, "mail pat@example.test or see https://example.test/a@b ok");
}

#[test]
fn a_redirect_keeps_going_there_without_user_info() {
    for (location, want) in [
        ("https://bob:hunter2@internal.example/app?x=1", "https://internal.example/app?x=1"),
        ("https://bob:hunter2@internal.example/app", "https://internal.example/app"),
        ("//bob:hunter2@internal.example/app?x=1", "//internal.example/app?x=1"),
    ] {
        let mut e = entry("GET", &format!("{A}/old"), 302, "");
        e["response"]["headers"] = json!([{"name": "Location", "value": location}]);
        let s = built(vec![e]);
        let headers = &s.routes[0].samples[0].headers;
        assert!(headers.iter().any(|(k, v)| k.eq_ignore_ascii_case("location") && v == want), "{location}: {headers:?}");
        assert_eq!(s.dropped.url_user_info, 1, "{location}");
        assert!(!serde_json::to_string(&s).unwrap().contains("hunter2"));
    }
}

#[test]
fn everyday_words_after_basic_or_bearer_stay() {
    let body = r#"{"plan":"Basic Membership","title":"Basic settings","kind":"Basic self-service","note":"bearer authentication","loud":"BASIC MEMBERSHIP"}"#;
    let (text, n) = cleaned("application/json", body);
    assert_eq!((text.as_str(), n), (body, 0));
    for secret in ["Basic dXNlcjpwYXNz", "Basic Zm9vOmJhcg==", "Bearer body-bearer-value-fake", "bearer abcdefgh12345678"] {
        let (text, n) = cleaned("text/plain", secret);
        assert!(text.ends_with(" [dropped]") && n == 1, "{secret}: {text}");
    }
}

#[test]
fn code_stays_code() {
    for mime in ["application/javascript", "text/javascript; charset=utf-8", "text/css", "text/html"] {
        let code = "this.token=t;e.password=n;a&&token=b;var p=\"Basic settings\";";
        let (text, n) = cleaned(mime, code);
        assert_eq!((text.as_str(), n), (code, 0), "{mime}");
    }
    let (text, n) = cleaned("text/html", r#"<a href="/x?token=real-fake&amp;api_key=other-fake&ok=1">sk-test-free-text-1234</a>"#);
    assert_eq!(n, 3, "{text}");
    assert!(!text.contains("real-fake") && !text.contains("other-fake") && !text.contains("sk-test") && text.contains("ok=1"), "{text}");
    let (plain, _) = cleaned("text/plain", "this.token=t");
    assert_eq!(plain, "[dropped]", "free text is still read as text");
}

#[test]
fn free_text_bodies_are_scanned_too() {
    let mut e =
        entry("GET", &format!("{A}/page"), 200, "Your key is sk-test-free-text-1234 and access_token=plain-fake; Authorization: Bearer abcdefgh12345678 ok");
    e["response"]["content"]["mimeType"] = json!("text/plain");
    let s = built(vec![e]);
    let text = s.routes[0].samples[0].text.as_deref().unwrap();
    assert!(!text.contains("sk-test") && !text.contains("plain-fake") && !text.contains("abcdefgh12345678"), "{text}");
    assert!(text.starts_with("Your key is") && text.ends_with("ok"), "{text}");
}

#[test]
fn untouched_json_keeps_its_exact_bytes() {
    let original = "{ \"b\" : 1,\n  \"a\": [1, 2] }";
    let s = built(vec![entry("GET", &format!("{A}/x"), 200, original)]);
    assert_eq!(s.routes[0].samples[0].text.as_deref(), Some(original));
}

#[test]
fn request_bodies_are_never_kept_only_their_key() {
    assert_eq!(request_key(br#"{"operationName":"GetUser","query":"query GetUser { a }"}"#).as_deref(), Some("op:GetUser"));
    assert_eq!(request_key(br#"{"query":"query Named { a }"}"#).as_deref(), Some("op:Named"));
    assert_eq!(request_key(br#"[{"operationName":"A"},{"operationName":"B"}]"#).as_deref(), Some("op:A,B"));
    assert_eq!(request_key(br#"{"password":"nope-fake","email":"x"}"#).as_deref(), Some("keys:email,password"));
    assert_eq!(request_key(br#"{"query":"{ a }"}"#).as_deref(), Some("keys:query"), "an anonymous document names nothing");
    for none in [&b""[..], b"not json", b"{}", b"[]", b"[1,2]", b"42", b"\xff\xfe"] {
        assert_eq!(request_key(none), None, "{none:?}");
    }
    assert_eq!(request_key(&vec![b' '; MAX_KEY_BODY + 1]), None, "too large to read");
}

// ---- what's skipped ----

#[test]
fn entries_that_cannot_be_answered_are_counted_not_kept() {
    let mut page = entry("GET", &format!("{A}/index"), 200, "<html>");
    page["_resourceType"] = json!("document");
    let mut pic = entry("GET", &format!("{A}/a.png"), 200, "");
    pic["response"]["content"]["mimeType"] = json!("image/png");
    let har = har_of(vec![
        entry("GET", "data:text/plain,hi", 200, ""),
        entry("GET", "blob:https://x/1", 200, ""),
        entry("GET", "wss://x.test/socket", 101, ""),
        entry("GET", "chrome-extension://abc/x", 200, ""),
        entry("GET", &format!("{A}/failed"), 0, ""),
        entry("GET", &format!("{A}/switching"), 101, ""),
        page,
        pic,
        entry("BAD METHOD", &format!("{A}/x"), 200, ""),
        entry("GET", "https://other.example.test/x", 200, "{}"),
        entry("GET", &format!("{A}/kept"), 200, "{}"),
    ]);
    let opts = BuildOptions { only_hosts: vec!["api.example.test".into()], ..Default::default() };
    let s = build_from_bytes(&har, &opts).unwrap();
    assert_eq!(templates(&s), ["GET /kept"]);
    assert_eq!(s.skipped, Skipped { not_web: 4, no_response: 3, static_files: 2, other_hosts: 1, beyond_route_limit: 0 });
    let all = BuildOptions { include_static: true, ..Default::default() };
    let s = build_from_bytes(&har, &all).unwrap();
    assert!(templates(&s).contains(&"GET /index".to_string()) && templates(&s).contains(&"GET /a.png".to_string()));
}

#[test]
fn a_port_in_the_recording_counts_as_the_same_host_when_asked_by_name() {
    let har = har_of(vec![entry("GET", "http://localhost:3000/x", 200, "{}")]);
    let by_name = BuildOptions { only_hosts: vec!["LOCALHOST".into()], ..Default::default() };
    assert_eq!(build_from_bytes(&har, &by_name).unwrap().routes.len(), 1);
    let other = BuildOptions { only_hosts: vec!["localhost:4000".into()], ..Default::default() };
    assert_eq!(build_from_bytes(&har, &other).unwrap().routes.len(), 0);
}

// ---- malformed and huge ----

#[test]
fn malformed_recordings_are_errors_or_skipped_never_a_crash() {
    for bad in [&b""[..], b"nope", b"{}", b"[]", b"{\"log\":{}}", b"{\"log\":{\"entries\":3}}"] {
        assert!(build_from_bytes(bad, &BuildOptions::default()).is_err(), "{bad:?}");
    }
    let odd = br#"{"log":{"entries":[1,null,"x",{},{"request":3,"response":[]},
        {"request":{"method":"GET","url":"https://x.test/ok"},"response":{"status":99999999999,"content":{"text":3}}},
        {"request":{"method":"GET","url":"https://x.test/neg"},"response":{"status":-1}},
        {"request":{"method":"GET","url":""},"response":{"status":200}},
        {"request":{"method":"GET","url":"https://"},"response":{"status":200}},
        {"request":{"method":"GET","url":"https://x.test/n"},"response":{"status":200,"headers":[{"name":"X\r\nInjected","value":"a"},{"name":"X-Bad","value":"a\r\nb: c"},{"value":"no name"},7]}},
        {"request":{"method":"GET","url":"https://x.test/b"},"response":{"status":200,"content":{"encoding":"base64","text":"@@not base64@@"}}}
    ]}}"#;
    let s = build_from_bytes(odd, &BuildOptions::default()).unwrap();
    assert_eq!(templates(&s), ["GET /b", "GET /n"], "{s:?}");
    assert_eq!(s.routes[0].samples[0].body_left_out, Some(BodyLeftOut::Undecodable));
    let n = &s.routes[1].samples[0];
    assert!(n.headers.is_empty(), "no header that could start a new line: {:?}", n.headers);
    assert_eq!(n.body_left_out, Some(BodyLeftOut::NotRecorded));
}

#[test]
fn caps_hold_on_huge_inputs() {
    let opts = BuildOptions { max_entries: 50, max_routes: 10, max_samples_per_route: 3, max_body_bytes: 64, max_total_body_bytes: 200, ..Default::default() };
    let mut entries: Vec<Value> = (0..30).map(|i| entry("GET", &format!("{A}/same/{i}"), 200, &format!("{{\"i\":{i}}}"))).collect();
    entries.extend((0..40).map(|i| entry("GET", &format!("{A}/r{i}x"), 200, "{}")));
    let s = build_from_bytes(&har_of(entries), &opts).unwrap();
    assert!(s.source.cut_short);
    assert_eq!((s.source.entries_read, s.source.entries_declared), (50, 70));
    assert_eq!(s.routes.len(), 10);
    assert_eq!(s.skipped.beyond_route_limit, 11);
    let same = s.routes.iter().find(|r| r.template == "/same/{id}").unwrap();
    assert_eq!((same.requests, same.samples.len(), same.samples_left_out), (30, 3, 27));

    let big = "x".repeat(65);
    let s = build_from_bytes(&har_of(vec![entry("GET", &format!("{A}/big"), 200, &big)]), &opts).unwrap();
    assert_eq!(s.routes[0].samples[0].body_left_out, Some(BodyLeftOut::TooLarge));
    assert!(s.routes[0].samples[0].text.is_none(), "never half a body");

    let files: Vec<Value> = (0..5).map(|i| entry("GET", &format!("{A}/f{i}y"), 200, &"y".repeat(60))).collect();
    let s = build_from_bytes(&har_of(files), &opts).unwrap();
    let kept: usize = s.routes.iter().flat_map(|r| &r.samples).filter_map(|x| x.text.as_ref()).map(String::len).sum();
    assert!(kept <= 200, "{kept}");
    assert_eq!(s.routes.iter().flat_map(|r| &r.samples).filter(|x| x.body_left_out == Some(BodyLeftOut::FileLimit)).count(), 2);
}

#[test]
fn hostile_paths_and_queries_are_bounded() {
    let deep = format!("{A}/{}", "a/".repeat(20_000));
    let wide: String = (0..5_000).map(|i| format!("k{i}=v&")).collect();
    let s = built(vec![
        entry("GET", &deep, 200, "{}"),
        entry("GET", &format!("{A}/q?{wide}"), 200, "{}"),
        entry("GET", &format!("{A}/{}", "é/".repeat(50)), 200, "{}"),
    ]);
    assert_eq!(s.routes.len(), 3);
    let wide_route = s.routes.iter().find(|r| r.template == "/q").unwrap();
    assert!(wide_route.query_names.len() <= MAX_LISTED);
    let mut t = Turns::default();
    for (path, query) in [(deep.trim_start_matches(A), ""), ("/", ""), ("", ""), ("//", "&&&==&"), ("/é", "é=é")] {
        let _ = get(&s, &mut t, path, query);
    }
    let _ = answer(&s, &mut t, "", "/", "", &[0xff; 64]);
}

#[test]
fn deeply_nested_json_is_kept_or_refused_without_a_crash() {
    let deep = format!("{}1{}", "[".repeat(100_000), "]".repeat(100_000));
    let s = built(vec![entry("GET", &format!("{A}/deep"), 200, &deep)]);
    assert_eq!(s.routes.len(), 1);
    assert!(request_key(deep.as_bytes()).is_none());
}

// ---- answering ----

#[test]
fn the_best_match_wins_in_order() {
    let s = built(vec![
        entry("GET", &format!("{A}/items/1"), 200, r#"{"from":"path-no-query"}"#),
        entry("GET", &format!("{A}/items/1?a=1&b=2"), 200, r#"{"from":"path-and-query"}"#),
        entry("GET", &format!("{A}/items/2"), 200, r#"{"from":"other-item"}"#),
    ]);
    let mut t = Turns::default();
    let f = found(get(&s, &mut t, "/items/1", "b=2&a=1"));
    assert_eq!(f.how, MatchKind::PathAndQuery, "the order of a query doesn't matter");
    assert!(body(&f).contains("path-and-query"));
    let f = found(get(&s, &mut t, "/items/2", "z=9"));
    assert_eq!(f.how, MatchKind::Path);
    assert!(body(&f).contains("other-item"));
    let f = found(get(&s, &mut Turns::default(), "/items/999", ""));
    assert_eq!(f.how, MatchKind::Template);
    assert!(body(&f).contains("path-no-query"), "the first recorded answer");
    assert_eq!(f.route, "GET /items/{id}");
}

#[test]
fn repeated_requests_cycle_through_recorded_answers_in_order() {
    let s = built(vec![
        entry("GET", &format!("{A}/poll"), 200, r#"{"n":1}"#),
        entry("GET", &format!("{A}/poll"), 200, r#"{"n":2}"#),
        entry("GET", &format!("{A}/poll"), 503, r#"{"n":3}"#),
    ]);
    let mut t = Turns::default();
    let seen: Vec<(u16, String, usize, usize)> = (0..7)
        .map(|_| {
            let f = found(get(&s, &mut t, "/poll", ""));
            (f.status, body(&f), f.turn, f.of)
        })
        .collect();
    assert_eq!(seen[0], (200, r#"{"n":1}"#.to_string(), 1, 3));
    assert_eq!(seen[1], (200, r#"{"n":2}"#.to_string(), 2, 3));
    assert_eq!(seen[2], (503, r#"{"n":3}"#.to_string(), 3, 3));
    assert_eq!(seen[3], seen[0], "and round again");
    assert_eq!(seen[6], seen[0]);
    // Each caller's turns are its own, and a different request doesn't move them.
    assert_eq!(found(get(&s, &mut Turns::default(), "/poll", "")).turn, 1);
}

#[test]
fn identical_answers_in_a_row_collapse_into_one() {
    let s = built(vec![
        entry("GET", &format!("{A}/same"), 200, "{}"),
        entry("GET", &format!("{A}/same"), 200, "{}"),
        entry("GET", &format!("{A}/same"), 200, r#"{"a":1}"#),
    ]);
    assert_eq!(s.routes[0].requests, 3);
    assert_eq!(s.routes[0].samples.len(), 2);
}

#[test]
fn turns_do_not_grow_with_requests() {
    let s = built(vec![entry("GET", &format!("{A}/users/1"), 200, "{}"), entry("GET", &format!("{A}/users/2"), 200, "{}")]);
    let mut t = Turns::default();
    for i in 0..2_000 {
        let _ = get(&s, &mut t, &format!("/users/{i}"), &format!("x={i}"));
        let _ = get(&s, &mut t, &format!("/nothing/{i}"), "");
    }
    assert!(t.0.len() <= 3, "{}", t.0.len());
}

#[test]
fn writes_replay_and_do_not_change_later_reads() {
    let s = built(vec![
        entry("GET", &format!("{A}/notes"), 200, r#"{"notes":[]}"#),
        entry("POST", &format!("{A}/notes"), 201, r#"{"id":7}"#),
        entry("DELETE", &format!("{A}/notes/7"), 204, ""),
    ]);
    let before = s.clone();
    let mut t = Turns::default();
    let created = found(answer(&s, &mut t, "POST", "/notes", "", br#"{"text":"anything"}"#));
    assert_eq!((created.status, body(&created).as_str()), (201, r#"{"id":7}"#));
    assert_eq!(found(answer(&s, &mut t, "DELETE", "/notes/99", "", b"")).status, 204);
    assert_eq!(body(&found(get(&s, &mut t, "/notes", ""))), r#"{"notes":[]}"#, "the read still says what was recorded");
    assert_eq!(s, before);
}

#[test]
fn head_is_answered_as_get_and_methods_do_not_cross() {
    let s = built(vec![entry("GET", &format!("{A}/a"), 200, r#"{"x":1}"#)]);
    let mut t = Turns::default();
    assert_eq!(found(answer(&s, &mut t, "head", "/a", "", b"")).status, 200);
    let n = missing(answer(&s, &mut t, "POST", "/a", "", b""));
    assert_eq!(n.reason, NoMatchReason::MethodNotRecorded);
    assert_eq!(n.nearest[0], NearbyRoute { method: "GET".into(), template: "/a".into() });
}

#[test]
fn graphql_operations_are_told_apart_at_one_url() {
    let post = |op: &str, resp: &str| {
        let mut e = entry("POST", &format!("{A}/graphql"), 200, resp);
        e["request"]["postData"] = json!({"mimeType": "application/json", "text": json!({"operationName": op, "query": format!("query {op} {{ a }}"), "variables": {"secret": "variable-fake"}}).to_string()});
        e
    };
    let s = built(vec![post("GetUser", r#"{"data":{"user":1}}"#), post("GetFeed", r#"{"data":{"feed":2}}"#)]);
    assert!(!serde_json::to_string(&s).unwrap().contains("variable-fake"), "request bodies aren't kept");
    let ask = |t: &mut Turns, op: &str| answer(&s, t, "POST", "/graphql", "", json!({"operationName": op}).to_string().as_bytes());
    let mut t = Turns::default();
    for _ in 0..3 {
        assert!(body(&found(ask(&mut t, "GetFeed"))).contains("feed"));
        assert!(body(&found(ask(&mut t, "GetUser"))).contains("user"));
    }
    // Another operation's data would be the wrong answer, not a close one.
    let n = missing(ask(&mut t, "SaveUser"));
    assert_eq!(n.reason, NoMatchReason::OperationNotRecorded);
    assert_eq!(n.nearest[0].template, "/graphql");
    // A body that names no operation takes what there is.
    assert_eq!(found(answer(&s, &mut t, "POST", "/graphql", "", b"not json")).of, 2);
}

#[test]
fn json_bodies_prefer_the_same_names_but_accept_others() {
    let post = |body: &str, resp: &str| {
        let mut e = entry("POST", &format!("{A}/search"), 200, resp);
        e["request"]["postData"] = json!({"text": body});
        e
    };
    let s = built(vec![post(r#"{"q":"a"}"#, r#"{"by":"q"}"#), post(r#"{"tag":"b"}"#, r#"{"by":"tag"}"#)]);
    let mut t = Turns::default();
    assert!(body(&found(answer(&s, &mut t, "POST", "/search", "", br#"{"tag":"other"}"#))).contains("tag"));
    assert_eq!(found(answer(&s, &mut t, "POST", "/search", "", br#"{"new":1}"#)).of, 2);
}

#[test]
fn no_match_names_the_nearest_routes() {
    let s = built(vec![
        entry("GET", &format!("{A}/api/users/1"), 200, "{}"),
        entry("GET", &format!("{A}/api/users/1/posts"), 200, "{}"),
        entry("POST", &format!("{A}/api/users"), 201, "{}"),
        entry("GET", &format!("{A}/health"), 200, "{}"),
    ]);
    let mut t = Turns::default();
    let n = missing(get(&s, &mut t, "/api/users/1/comments", ""));
    assert_eq!(n.reason, NoMatchReason::PathNotRecorded);
    assert_eq!(n.nearest[0], NearbyRoute { method: "GET".into(), template: "/api/users/{id}/posts".into() });
    assert!(n.nearest.len() <= MAX_NEAREST);
    assert_eq!(n.nearest.last().unwrap().template, "/health");
    assert_eq!(missing(get(&StandIn::default(), &mut t, "/x", "")).nearest, []);
}

#[test]
fn a_template_id_needs_something_there() {
    let s = built(vec![entry("GET", &format!("{A}/users/1"), 200, "{}")]);
    let mut t = Turns::default();
    assert!(matches!(get(&s, &mut t, "/users/", ""), Answer::NoMatch(_)));
    assert!(matches!(get(&s, &mut t, "/users", ""), Answer::NoMatch(_)));
    assert!(matches!(get(&s, &mut t, "/users/1/2", ""), Answer::NoMatch(_)));
}

#[test]
fn a_304_with_its_cached_body_answers_as_200() {
    let s = built(vec![entry("GET", &format!("{A}/c"), 304, r#"{"cached":true}"#), entry("GET", &format!("{A}/e"), 304, "")]);
    let c = &s.routes[0].samples[0];
    assert_eq!((c.status, c.was_not_modified), (200, true));
    let e = &s.routes[1].samples[0];
    assert_eq!((e.status, e.was_not_modified), (304, false), "nothing to stand in for it");
}

#[test]
fn a_saved_stand_in_reads_back_the_same() {
    let opts = BuildOptions { source_name: Some("site.har".into()), source_sha256: Some("abc".into()), ..Default::default() };
    let s = build_from_bytes(&secret_recording(), &opts).unwrap();
    let text = serde_json::to_string(&s).unwrap();
    let back: StandIn = serde_json::from_str(&text).unwrap();
    assert_eq!(back, s);
    assert_eq!(back.version, STANDIN_VERSION);
    assert_eq!(back.source.file_name.as_deref(), Some("site.har"));
}

#[test]
fn a_hand_edited_file_cannot_crash_the_matcher() {
    let v = json!({"version": 1, "routes": [
        {"method": "GET", "template": "/a", "samples": []},
        {"method": "GET", "template": "/b", "samples": [{"path": "/b", "status": 200, "base64": "@@@"}]},
    ]});
    let s: StandIn = serde_json::from_value(v).unwrap();
    let mut t = Turns::default();
    assert!(matches!(get(&s, &mut t, "/a", ""), Answer::NoMatch(_)), "a route with no samples has nothing to say");
    assert_eq!(found(get(&s, &mut t, "/b", "")).body, b"");
}
