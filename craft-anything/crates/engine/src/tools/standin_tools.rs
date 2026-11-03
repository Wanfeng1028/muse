//! A stand-in backend: answer a rebuilt front end's requests from a recording of the original's
//! network traffic, so the builder can test it without the real backend.
//!
//! `web_standin_build` writes the description (see `craft_anything_analysis::standin`), and is that
//! file's only writer. `web_standin_start` serves one on loopback, held by the session until
//! `web_standin_stop` or the session ends. `web_standin_show` says what was asked for and had no
//! recorded answer, which is what tells a builder what's still missing.

use super::artifact_tools::{abs_path, env, read_capped};
use super::native_common::spec;
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use crate::versioned::{Step, upgrade};
use craft_anything_analysis::standin::{self, Answer, BodyLeftOut, BuildOptions, NearbyRoute, NoMatchReason, STANDIN_VERSION, StandIn, Turns};
use craft_anything_evidence::{Authority, Confidence, Coverage, ErrorCode, EvidenceBuilder, Limitation, Location, Subject, ToolError, sha256_hex};
use craft_anything_platform::standin_server::{self, Answerer, Limits, LoopbackServer, Request, Response};
use craft_anything_platform::sync::Mutex;
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::BTreeMap;
#[cfg(test)]
use std::path::Path;
use std::path::PathBuf;
use std::sync::{Arc, PoisonError};

/// What `web_standin_build` writes in the folder it's given.
pub const STANDIN_FILE: &str = "standin.json";
const MAX_RECORDING_BYTES: u64 = 512 * 1024 * 1024;
const MAX_STANDIN_BYTES: u64 = 1024 * 1024 * 1024;
const MAX_RUNNING: usize = 16;
/// Different requests remembered as having no answer. Others are counted, not listed.
const MAX_MISSING: usize = 1_000;
const MAX_LOGGED_PATH: usize = 512;
const MAX_LOGGED_QUERY_NAMES: usize = 32;
/// Tells a client which kind of answer it got: a recorded 404 and "nothing recorded" look alike otherwise.
const ANSWER_HEADER: &str = "X-Craft-Anything-Stand-In";

/// Steps that bring an older file to the current version (none yet).
const STANDIN_STEPS: &[Step<Value>] = &[];
const FIRST_STANDIN_VERSION: u32 = 1;
const _: () = assert!(FIRST_STANDIN_VERSION as usize + STANDIN_STEPS.len() == STANDIN_VERSION as usize);

const REPLAY_LIMIT: &str = "Replay is read-only: POST, PUT, PATCH and DELETE answer what was recorded and don't change what later reads return. Nothing here models the backend's state.";

pub fn specs() -> Vec<ToolSpec> {
    vec![
        spec(
            "web_standin_build",
            "Build a stand-in backend",
            "Read a network recording (.har) of the original site and write standin.json into a folder: its routes (method and path template, with ids as {id}), and for each the status codes, content types, query names and a bounded set of recorded answers. It's for giving a rebuilt front end something to talk to. Credential headers, cookies and secret-shaped values are dropped and counted; pages, scripts and pictures are left out unless include_static is set. It only knows what was recorded. Returns a summary and a page of routes.",
            "Turn a recording of a website's traffic into a stand-in for its backend, so a rebuilt front end has something to talk to.",
            Toolset::Browser,
            Effects::EVIDENCE.union(Effects::WRITES_FILESYSTEM).union(Effects::CARRIES_TARGET_CONTENT),
            Requires::Nothing,
            schema_of::<BuildParams>,
            web_standin_build,
        ),
        spec(
            "web_standin_start",
            "Start a stand-in backend",
            "Answer HTTP requests on this computer from a file written by web_standin_build, and return its URL to point a rebuilt front end at. Listens on 127.0.0.1 only, refuses requests addressed to any other host and pages from other computers, and allows local pages through CORS. Stays running for this session, or until web_standin_stop. A request with no recorded answer gets a 404 with the nearest routes as JSON. Writes replay what was recorded and change nothing. Runs no code from the recording.",
            "Start a local stand-in for a website's backend, answering from a recording.",
            Toolset::Browser,
            Effects::MUTATES_SESSION.union(Effects::ACCESSES_NETWORK),
            Requires::Nothing,
            schema_of::<StartParams>,
            web_standin_start,
        ),
        spec(
            "web_standin_stop",
            "Stop a stand-in backend",
            "Stop a stand-in started by web_standin_start and free its port: by id, or all of them. With neither, stops the only one running. Returns what it answered.",
            "Stop a local stand-in backend.",
            Toolset::Browser,
            Effects::MUTATES_SESSION.union(Effects::IDEMPOTENT),
            Requires::Nothing,
            schema_of::<StopParams>,
            web_standin_stop,
        ),
        spec(
            "web_standin_show",
            "See what a stand-in was asked",
            "List the stand-ins running in this session with the requests they answered, and page through the requests that had no recorded answer, most asked first, each with why and the nearest recorded routes. This is how a builder finds out what its front end needs that the recording doesn't have.",
            "See which requests a stand-in backend could answer and which it couldn't.",
            Toolset::Browser,
            Effects::READ_ONLY.union(Effects::CARRIES_TARGET_CONTENT),
            Requires::Nothing,
            schema_of::<ShowParams>,
            web_standin_show,
        ),
    ]
}

// ---------------------------------------------------------------------------------------------
// Reading the file

/// A saved stand-in, brought to the current version. A newer file is refused, because serving what
/// we can only half read would give wrong answers that look right.
pub fn parse_standin(bytes: &[u8]) -> Result<StandIn, ToolError> {
    let not_one = |why: String| {
        ToolError::new(ErrorCode::GarbledOutput, format!("This isn't a stand-in file: {why}")).with_remediation("Make one with web_standin_build.")
    };
    let mut doc: Value = serde_json::from_slice(bytes).map_err(|e| not_one(e.to_string()))?;
    let version = doc.get("version").and_then(Value::as_u64).and_then(|v| u32::try_from(v).ok()).ok_or_else(|| not_one("it has no version".into()))?;
    if version > STANDIN_VERSION {
        return Err(ToolError::unsupported(format!("This stand-in file is version {version}; this build reads up to {STANDIN_VERSION}."))
            .with_remediation("Update Craft Anything, or make the file again with web_standin_build."));
    }
    upgrade(&mut doc, version, FIRST_STANDIN_VERSION, STANDIN_STEPS).map_err(not_one)?;
    let mut standin: StandIn = serde_json::from_value(doc).map_err(|e| not_one(e.to_string()))?;
    standin.version = STANDIN_VERSION;
    Ok(standin)
}

// ---------------------------------------------------------------------------------------------
// web_standin_build

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct BuildParams {
    /// Absolute path of the recording (.har).
    pub path: String,
    /// Absolute path of the folder to write standin.json in (made if missing). An earlier stand-in there is replaced.
    pub output_dir: String,
    /// Values to drop wherever they appear, in every encoding (emails, ids, tokens). Only their count is recorded.
    #[serde(default)]
    pub hidden_values: Vec<String>,
    /// Only these hosts, e.g. api.example.com (or with a port). Default: every host.
    #[serde(default)]
    pub only_hosts: Vec<String>,
    /// Also keep pages, scripts, styles, pictures, fonts and media.
    #[serde(default)]
    pub include_static: bool,
    #[serde(default)]
    pub offset: usize,
    /// Routes per page (1–1000).
    #[serde(default = "default_limit")]
    pub limit: usize,
}

fn default_limit() -> usize {
    50
}

fn route_row(r: &standin::StandInRoute) -> Value {
    json!({
        "method": r.method,
        "template": r.template,
        "hosts": r.hosts,
        "statuses": r.statuses,
        "content_types": r.content_types,
        "query_names": r.query_names,
        "requests": r.requests,
        "samples": r.samples.len(),
        "samples_left_out": r.samples_left_out,
        "bodies_left_out": r.samples.iter().filter(|s| s.body_left_out.is_some_and(|b| b != BodyLeftOut::NotRecorded)).count(),
    })
}

fn web_standin_build(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: BuildParams = parse_params(params)?;
    let path = abs_path(&p.path, "path")?;
    let dir = abs_path(&p.output_dir, "output_dir")?;
    let out = dir.join(STANDIN_FILE);
    // A file from a newer build holds what we can't read; it isn't ours to replace.
    if let Ok(existing) = std::fs::read(&out)
        && let Ok(v) = serde_json::from_slice::<Value>(&existing)
        && v.get("version").and_then(Value::as_u64).is_some_and(|n| n > u64::from(STANDIN_VERSION))
    {
        return Err(ToolError::unsupported(format!("{} was made by a newer Craft Anything, so it isn't replaced.", out.display()))
            .with_remediation("Update Craft Anything, or use another folder."));
    }
    ctx.report(None, format!("Reading {}", path.display()));
    let bytes = read_capped(&path, MAX_RECORDING_BYTES)?;
    let digest = sha256_hex(&bytes);
    let file_name = path.file_name().map(|n| n.to_string_lossy().into_owned());
    let opts = BuildOptions {
        hidden_values: p.hidden_values.clone(),
        only_hosts: p.only_hosts.clone(),
        include_static: p.include_static,
        source_name: file_name.clone(),
        source_sha256: Some(digest.clone()),
        ..Default::default()
    };
    let built = standin::build_from_bytes(&bytes, &opts).map_err(|e| {
        ToolError::new(ErrorCode::GarbledOutput, format!("{}: {e}", path.display()))
            .with_remediation("Pass a HAR 1.2 file (browser dev tools: Save all as HAR).")
    })?;
    let text = serde_json::to_vec(&built).map_err(|e| ToolError::internal(e.to_string()))?;
    std::fs::create_dir_all(&dir).map_err(|e| ToolError::io(dir.display(), e))?;
    // Bodies can hold personal data nobody named, so the file is only readable by this person.
    craft_anything_platform::write_atomic_private(&out, &text)?;

    let limit = p.limit.clamp(1, 1000);
    let total = built.routes.len();
    let rows: Vec<Value> = built.routes.iter().skip(p.offset).take(limit).map(route_row).collect();
    let dropped = built.dropped.total();
    let samples: usize = built.routes.iter().map(|r| r.samples.len()).sum();
    let summary = format!(
        "{total} route(s) on {} host(s) from {} recorded request(s), with {samples} recorded answer(s); {dropped} secret(s) dropped. Written to {}.",
        built.hosts.len(),
        built.source.entries_read,
        out.display()
    );
    let shown = rows.len() as u64;
    let result = json!({
        "file": out.display().to_string(),
        "bytes": text.len(),
        "version": built.version,
        "hosts": built.hosts,
        "routes_total": total,
        "routes": rows,
        "samples": samples,
        "dropped": built.dropped,
        "skipped": built.skipped,
        "source": built.source,
        "continue_with": "web_standin_start",
    });
    let hidden_in_name = file_name.as_ref().is_some_and(|n| p.hidden_values.iter().any(|h| !h.is_empty() && n.contains(h.as_str())));
    let mut b = EvidenceBuilder::new("web_standin_build", Subject { kind: "capture".into(), sha256: (!p.hidden_values.contains(&digest)).then_some(digest), name: file_name.filter(|_| !hidden_in_name) }, env(ctx))
        .params(json!({"offset": p.offset, "limit": limit, "include_static": p.include_static, "only_hosts": p.only_hosts.len(), "sensitive_value_declarations": p.hidden_values.len()}))
        .result(result)
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::EarlierRecord)
        .limitation(Limitation::new("only_what_was_recorded", "This knows only the requests in the recording. A page or action nobody used while recording has no answer here, and an {id} in a template is inferred from how paths varied."))
        .limitation(Limitation::new("read_only_replay", REPLAY_LIMIT))
        .limitation(Limitation::new("secrets_dropped", format!("{dropped} credential or secret-shaped value(s) were dropped, so anything that needs a real session won't work. Other response text is kept as recorded, and may hold personal data: name it in hidden_values, and don't commit this file.")))
        .coverage(Coverage::page(shown, total as u64, p.offset as u64))
        .location(Location::new("path", out.display().to_string()));
    if built.source.cut_short {
        b = b.limitation(Limitation::new(
            "cut_short",
            format!("Only the first {} of {} recorded requests were read.", built.source.entries_read, built.source.entries_declared),
        ));
    }
    if built.hosts.len() > 1 {
        b = b.limitation(Limitation::new("hosts_merged", "Requests to every host share one set of routes, because a stand-in has one address. The same path on two hosts answers from both; only_hosts keeps them apart."));
    }
    if total == 0 {
        b = b.limitation(Limitation::new("empty", "Nothing in the recording could be kept. If it only has pages and scripts, include_static keeps them."));
    }
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// The running servers

#[derive(Debug, Default)]
struct MissingRow {
    count: u64,
    query_names: Vec<String>,
    reason: Option<NoMatchReason>,
    nearest: Vec<NearbyRoute>,
}

/// What one stand-in has been asked. Bounded: it grows with the routes and [`MAX_MISSING`] only.
#[derive(Debug, Default)]
struct Log {
    answered: u64,
    answered_without_body: u64,
    by_route: BTreeMap<String, u64>,
    no_answer: u64,
    missing: BTreeMap<(String, String), MissingRow>,
    missing_not_listed: u64,
}

struct Replay {
    standin: StandIn,
    /// Which answer each repeated request is up to, and what's been asked: one lock, one request at a time.
    state: Mutex<(Turns, Log)>,
}

fn clip(s: &str, max: usize) -> String {
    if s.len() <= max {
        return s.to_string();
    }
    let mut end = max;
    while !s.is_char_boundary(end) {
        end -= 1;
    }
    format!("{}…", s.get(..end).unwrap_or_default())
}

impl Answerer for Replay {
    fn answer(&self, r: &Request) -> Response {
        let mut guard = self.state.lock().unwrap_or_else(PoisonError::into_inner);
        let (turns, log) = &mut *guard;
        match standin::answer(&self.standin, turns, &r.method, &r.path, &r.query, &r.body) {
            Answer::Found(f) => {
                log.answered = log.answered.saturating_add(1);
                if f.body_left_out.is_some_and(|b| b != BodyLeftOut::NotRecorded) {
                    log.answered_without_body = log.answered_without_body.saturating_add(1);
                }
                let counter = log.by_route.entry(f.route.clone()).or_insert(0);
                *counter = counter.saturating_add(1);
                let mut headers = f.headers.clone();
                if let Some(ct) = &f.content_type {
                    headers.push(("Content-Type".into(), ct.clone()));
                }
                headers.push((ANSWER_HEADER.into(), "recorded".into()));
                Response { status: f.status, headers, body: f.body }
            }
            Answer::NoMatch(n) => {
                log.no_answer = log.no_answer.saturating_add(1);
                // What a client asks for is only its names and path: never query values or bodies.
                let path = clip(&standin::safe_path(&r.path), MAX_LOGGED_PATH);
                let key = (r.method.to_ascii_uppercase(), path.clone());
                if log.missing.contains_key(&key) || log.missing.len() < MAX_MISSING {
                    let row = log.missing.entry(key).or_default();
                    row.count = row.count.saturating_add(1);
                    row.reason = Some(n.reason);
                    row.nearest.clone_from(&n.nearest);
                    for name in r.query.split('&').filter_map(|p| p.split('=').next()).filter(|k| !k.is_empty()).take(MAX_LOGGED_QUERY_NAMES) {
                        if row.query_names.len() < MAX_LOGGED_QUERY_NAMES && !row.query_names.iter().any(|x| x == name) {
                            row.query_names.push(clip(name, 64));
                        }
                    }
                } else {
                    log.missing_not_listed = log.missing_not_listed.saturating_add(1);
                }
                let mut response = Response::json(
                    404,
                    &json!({
                        "error": "no_recorded_answer",
                        "reason": n.reason,
                        "method": r.method,
                        "path": path,
                        "nearest": n.nearest,
                        "message": "The recording behind this stand-in has no answer for this request.",
                    }),
                );
                response.headers.push((ANSWER_HEADER.into(), "no-recorded-answer".into()));
                response
            }
        }
    }
}

struct Running {
    file: PathBuf,
    /// Of the file as it was loaded, to tell when it has been rebuilt since.
    sha256: String,
    replay: Arc<Replay>,
    server: LoopbackServer,
}

impl Running {
    fn describe(&self, id: &str) -> Value {
        let guard = self.replay.state.lock().unwrap_or_else(PoisonError::into_inner);
        let log = &guard.1;
        json!({
            "id": id,
            "url": self.server.url(),
            "port": self.server.port,
            "file": self.file.display().to_string(),
            "routes": self.replay.standin.routes.len(),
            "routes_used": log.by_route.len(),
            "requests_answered": log.answered,
            "answered_without_their_body": log.answered_without_body,
            "requests_with_no_answer": log.no_answer,
            "requests_refused": self.server.refused(),
        })
    }
}

/// The stand-ins this session is running. Dropped with the session, which stops them.
#[derive(Default)]
struct StandIns {
    running: Mutex<BTreeMap<String, Running>>,
    next: Mutex<u64>,
}

fn stand_ins(ctx: &mut Ctx<'_>) -> Arc<StandIns> {
    match ctx.session.ext.get::<StandIns>() {
        Some(s) => s,
        None => {
            let s = Arc::new(StandIns::default());
            ctx.session.ext.insert(s.clone());
            s
        }
    }
}

// ---------------------------------------------------------------------------------------------
// web_standin_start

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct StartParams {
    /// Absolute path of a file written by web_standin_build, or the folder holding it.
    pub path: String,
    /// The port to listen on. 0 (the default) picks a free one.
    #[serde(default)]
    pub port: u16,
    /// Keep this call going until it's cancelled, then stop and say what was answered. For a one-off
    /// command line, whose session would otherwise end and take the stand-in with it. No other tool
    /// can run in this session meanwhile.
    #[serde(default)]
    pub wait: bool,
}

fn standin_path(p: &str) -> Result<PathBuf, ToolError> {
    let path = abs_path(p, "path")?;
    let path = if path.is_dir() { path.join(STANDIN_FILE) } else { path };
    if !path.is_file() {
        return Err(ToolError::new(ErrorCode::NotFound, format!("There's no stand-in file at {}.", path.display()))
            .with_remediation("Make one with web_standin_build."));
    }
    std::fs::canonicalize(&path).map_err(|e| ToolError::io(path.display(), e))
}

/// How long a rebuilt stand-in waits for its predecessor's port.
const TAKEOVER_WAIT: std::time::Duration = std::time::Duration::from_secs(2);

/// Listen on `port`, trying a busy one again for up to `wait`: the port a replaced stand-in just
/// gave up can stay busy a moment, or be lent out briefly as another connection's local port.
fn serve_on(port: u16, answerer: Arc<dyn Answerer>, wait: std::time::Duration) -> std::io::Result<LoopbackServer> {
    let until = std::time::Instant::now() + wait;
    loop {
        match standin_server::serve(port, Limits::default(), answerer.clone()) {
            Err(e) if e.kind() == std::io::ErrorKind::AddrInUse && std::time::Instant::now() < until => {
                std::thread::sleep(std::time::Duration::from_millis(50));
            }
            r => return r,
        }
    }
}

fn web_standin_start(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: StartParams = parse_params(params)?;
    let file = standin_path(&p.path)?;
    let bytes = read_capped(&file, MAX_STANDIN_BYTES)?;
    let sha256 = sha256_hex(&bytes);
    let all = stand_ins(ctx);
    let stale = {
        let running = all.running.lock().unwrap_or_else(PoisonError::into_inner);
        let same = running.iter().find(|(_, r)| r.file == file && (p.port == 0 || r.server.port == p.port));
        if let Some((id, r)) = same.filter(|(_, r)| r.sha256 == sha256) {
            return Ok(ToolOutput::Value(json!({"already_running": true, "server": r.describe(id), "url": r.server.url()})));
        }
        if same.is_none() && running.len() >= MAX_RUNNING {
            return Err(ToolError::new(ErrorCode::OverLimit, format!("{MAX_RUNNING} stand-ins are already running."))
                .with_remediation("Stop one with web_standin_stop."));
        }
        same.map(|(id, _)| id.clone())
    };
    // Checked before the old one stops, so a bad file leaves what's running alone.
    let standin = parse_standin(&bytes)?;
    let routes = standin.routes.len();
    let replay = Arc::new(Replay { standin, state: Mutex::default() });
    let answerer: Arc<dyn Answerer> = replay.clone();
    // The file was rebuilt since it was loaded: answer from the new one, at the same address.
    let (port, taken_over) = match stale.as_ref().and_then(|id| all.running.lock().unwrap_or_else(PoisonError::into_inner).remove(id)) {
        Some(old) => {
            let port = old.server.port;
            drop(old);
            (port, true)
        }
        None => (p.port, false),
    };
    let server = serve_on(port, answerer, if taken_over { TAKEOVER_WAIT } else { std::time::Duration::ZERO })
        .map_err(|e| ToolError::io(format!("listening on port {port}"), e).with_remediation("Pick another port, or leave port out to use a free one."))?;
    let id = {
        let mut next = all.next.lock().unwrap_or_else(PoisonError::into_inner);
        *next = next.saturating_add(1);
        format!("standin-{next}")
    };
    let url = server.url();
    all.running.lock().unwrap_or_else(PoisonError::into_inner).insert(id.clone(), Running { file: file.clone(), sha256, replay, server });
    ctx.report(None, format!("Answering from {} on {url}", file.display()));
    if p.wait {
        while !ctx.cancel.is_cancelled() {
            std::thread::sleep(std::time::Duration::from_millis(100));
        }
        let ended = all.running.lock().unwrap_or_else(PoisonError::into_inner).remove(&id);
        let row = ended.as_ref().map(|r| r.describe(&id));
        drop(ended);
        return Ok(ToolOutput::Value(json!({"already_running": false, "replaced": stale, "id": id, "url": url, "routes": routes, "stopped": row})));
    }
    Ok(ToolOutput::Value(json!({
        "already_running": false,
        "replaced": stale,
        "id": id,
        "url": url,
        "routes": routes,
        "note": REPLAY_LIMIT,
        "continue_with": "web_standin_show",
    })))
}

// ---------------------------------------------------------------------------------------------
// web_standin_stop

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct StopParams {
    /// The id web_standin_start returned.
    #[serde(default)]
    pub id: Option<String>,
    /// Stop every stand-in in this session.
    #[serde(default)]
    pub all: bool,
}

fn web_standin_stop(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: StopParams = parse_params(params)?;
    if p.all && p.id.is_some() {
        return Err(ToolError::invalid("Pass id or all, not both."));
    }
    let all = stand_ins(ctx);
    let stopped: Vec<(String, Running)> = {
        let mut running = all.running.lock().unwrap_or_else(PoisonError::into_inner);
        if p.all {
            std::mem::take(&mut *running).into_iter().collect()
        } else if let Some(id) = &p.id {
            let r = running.remove(id).ok_or_else(|| {
                ToolError::new(ErrorCode::NotFound, format!("No stand-in {id:?} is running.")).with_remediation("web_standin_show lists the ones that are.")
            })?;
            vec![(id.clone(), r)]
        } else {
            if running.len() > 1 {
                let ids: Vec<&str> = running.keys().map(String::as_str).collect();
                return Err(ToolError::invalid(format!("{} stand-ins are running ({}): pass id, or all.", ids.len(), ids.join(", "))));
            }
            std::mem::take(&mut *running).into_iter().collect()
        }
    };
    // Described before it stops, and stopped outside the lock: stopping can take a moment.
    let rows: Vec<Value> = stopped.iter().map(|(id, r)| r.describe(id)).collect();
    drop(stopped);
    Ok(ToolOutput::Value(json!({"stopped": rows})))
}

// ---------------------------------------------------------------------------------------------
// web_standin_show

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ShowParams {
    /// Only this stand-in. Default: every one running.
    #[serde(default)]
    pub id: Option<String>,
    #[serde(default)]
    pub offset: usize,
    /// Requests with no answer per page (1–1000).
    #[serde(default = "default_limit")]
    pub limit: usize,
}

fn web_standin_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ShowParams = parse_params(params)?;
    let all = stand_ins(ctx);
    let running = all.running.lock().unwrap_or_else(PoisonError::into_inner);
    if let Some(id) = &p.id
        && !running.contains_key(id)
    {
        return Err(ToolError::new(ErrorCode::NotFound, format!("No stand-in {id:?} is running."))
            .with_remediation("web_standin_show with no id lists the ones that are."));
    }
    let chosen: Vec<(&String, &Running)> = running.iter().filter(|(id, _)| p.id.as_ref().is_none_or(|x| x == *id)).collect();
    let servers: Vec<Value> = chosen.iter().map(|(id, r)| r.describe(id)).collect();
    let mut rows: Vec<(u64, Value)> = Vec::new();
    let mut not_listed = 0u64;
    let mut answered_routes: Vec<Value> = Vec::new();
    for (id, r) in &chosen {
        let guard = r.replay.state.lock().unwrap_or_else(PoisonError::into_inner);
        let log = &guard.1;
        not_listed = not_listed.saturating_add(log.missing_not_listed);
        for ((method, path), m) in &log.missing {
            rows.push((
                m.count,
                json!({"server": id, "method": method, "path": path, "times": m.count, "query_names": m.query_names, "reason": m.reason, "nearest": m.nearest}),
            ));
        }
        for (route, n) in &log.by_route {
            answered_routes.push(json!({"server": id, "route": route, "times": n}));
        }
    }
    // Most asked first; the stable sort keeps the log's order among equals, so pages don't shift.
    rows.sort_by_key(|(count, _)| std::cmp::Reverse(*count));
    let total = rows.len();
    let limit = p.limit.clamp(1, 1000);
    let page: Vec<Value> = rows.into_iter().skip(p.offset).take(limit).map(|(_, v)| v).collect();
    let next = p.offset.saturating_add(page.len());
    Ok(ToolOutput::Value(json!({
        "servers": servers,
        "answered_routes": answered_routes,
        "no_answer": {
            "total": total,
            "offset": p.offset,
            "items": page,
            "next_offset": (next < total).then_some(next),
            "not_listed": not_listed,
        },
        "note": REPLAY_LIMIT,
    })))
}

/// The file a build writes in `dir`.
#[cfg(test)]
fn standin_file(dir: &Path) -> PathBuf {
    dir.join(STANDIN_FILE)
}

#[cfg(test)]
mod tests;
