//! Our own clean-room bridge to Ghidra's headless analyzer (Deep mode).
//!
//! Each target is analysed once: `analyzeHeadless -import` analyses it and saves it in a project
//! cached on disk, keyed by the target's sha256 plus the analysis settings hash, under the engine
//! store. A big program can take hours, so every later session opens that saved program with
//! `-process -noanalysis -readOnly` and **our own** post-script, which opens a loopback TCP socket,
//! authenticates every request against a random per-run token, and answers newline-delimited JSON
//! (NDJSON) requests: decompile a function, list functions, get a function's details. We never
//! reuse another project's code, scripts or wording.
//!
//! Everything here is bounded and cancellable and can never hang:
//! - the external process runs through [`craft_anything_platform::process`], so its group is killed
//!   on timeout, cancel or drop;
//! - the one-time analysis, and opening the analysed program, each have a deadline, with a
//!   progress ping every few seconds;
//! - each request has a deadline and honours a cancel flag;
//! - the socket uses short read timeouts and a loop, so a silent Ghidra never blocks a caller.

mod client;
pub mod get;
mod protocol;

pub use client::Client;
pub use protocol::{GhidraError, Request, Response, ct_eq};

use craft_anything_platform::process::{Process, RunningProcess, StdinMode};
use craft_anything_platform::sync::Mutex;
use craft_anything_platform::write_atomic_private;
use serde::Serialize;
use serde_json::Value;
use std::ffi::OsString;
use std::net::{Ipv4Addr, SocketAddr};
use std::path::{Path, PathBuf};
use std::sync::PoisonError;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant, SystemTime};

/// The Java post-script we ship and run inside Ghidra (our own code).
pub const BRIDGE_SCRIPT_NAME: &str = "CraftAnythingBridge.java";
const BRIDGE_SCRIPT: &str = include_str!("CraftAnythingBridge.java");
/// Our pre-script for the one-time analysis: skips Ghidra's slowest whole-program passes.
const FAST_SCRIPT_NAME: &str = "CraftAnythingFastAnalysis.java";
const FAST_SCRIPT: &str = include_str!("CraftAnythingFastAnalysis.java");

/// A function as the deep engine sees it.
#[derive(Debug, Clone, Serialize)]
pub struct DeepFunction {
    pub entry: u64,
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub signature: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pseudocode: Option<String>,
    /// The saved analysis had no function here; the bridge made one for this run only.
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    pub created: bool,
}

/// A deep (external-engine) source of decompilation, consulted by the native tools when Deep mode
/// is on and an engine is available. Clean-room analysis never touches this.
pub trait DeepDecompiler: Send + Sync {
    /// Engine id recorded in evidence (`ghidra`).
    fn engine(&self) -> &'static str;
    fn engine_version(&self) -> Option<String>;
    /// The processor/language the engine was pinned to, when one was forced (a Ghidra language id).
    /// `None` for the usual auto-detected case.
    fn language_id(&self) -> Option<String> {
        None
    }
    /// Where the engine loaded the program (its image base), when it said. Ghidra puts a
    /// position-independent ELF at 0x100000, not at the 0 its program headers give, so its
    /// addresses differ from ours by that much; see [`Rebase`].
    fn image_base(&self) -> Option<u64> {
        None
    }
    /// Decompile the function at `entry` (an address in the engine's own space). `Ok(None)` means
    /// the engine has no better answer.
    fn decompile(&self, entry: u64) -> Result<Option<DeepFunction>, GhidraError>;
    /// List the functions the engine found.
    fn list_functions(&self) -> Result<Vec<DeepFunction>, GhidraError>;
}

/// Moves addresses between our built-in engine's view of a program and the Deep engine's, which
/// may have loaded it somewhere else: Ghidra puts a position-independent ELF (lowest segment at 0)
/// at 0x100000. Both sides keep the same offsets from their image base, so moving an address is
/// one subtraction and one addition. An address below the base it's moved from stays as it is.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Rebase {
    ours: u64,
    theirs: u64,
}

impl Rebase {
    /// `ours`: our image base; `theirs`: the engine's, `None` when it didn't say (then no move).
    pub fn new(ours: u64, theirs: Option<u64>) -> Rebase {
        Rebase { ours, theirs: theirs.unwrap_or(ours) }
    }

    /// Our image base.
    pub fn ours(&self) -> u64 {
        self.ours
    }

    /// The engine's image base (ours when it didn't say).
    pub fn theirs(&self) -> u64 {
        self.theirs
    }

    /// Whether both sides use the same addresses.
    pub fn is_identity(&self) -> bool {
        self.ours == self.theirs
    }

    /// Our address as the engine knows it.
    pub fn to_engine(&self, a: u64) -> u64 {
        a.checked_sub(self.ours).and_then(|o| o.checked_add(self.theirs)).unwrap_or(a)
    }

    /// The engine's address as we know it.
    pub fn from_engine(&self, a: u64) -> u64 {
        a.checked_sub(self.theirs).and_then(|o| o.checked_add(self.ours)).unwrap_or(a)
    }
}

/// Where Ghidra and its JDK live, and how long to wait.
#[derive(Debug, Clone)]
pub struct Config {
    /// Path to `support/analyzeHeadless` (or `.bat`).
    pub analyze_headless: PathBuf,
    /// A JDK to run Ghidra with (its `bin/java`), when one must be set explicitly.
    pub java_home: Option<PathBuf>,
    /// How long the one-time analysis of a target may take, and separately how long opening the
    /// analysed program and connecting to the bridge may take.
    pub startup_timeout: Duration,
    /// Where analysed projects and runtime roots are cached.
    pub store_dir: PathBuf,
    /// A Ghidra language id to force (e.g. `RISCV:LE:64:RV64GC`), passed as `-processor`. Lets
    /// Deep mode target processors our clean-room engine doesn't cover, with no per-arch code.
    /// `None` lets Ghidra auto-detect from the file.
    pub language_id: Option<String>,
    /// A compiler-spec id paired with `language_id`, passed as `-cspec` (ignored without one).
    pub compiler_spec: Option<String>,
    /// Java's memory for Ghidra in GB ([`HEAP_GB`] bounds it); `None`: half this computer's memory.
    pub memory_gb: Option<u64>,
}

impl Config {
    pub fn startup_timeout(&self) -> Duration {
        self.startup_timeout
    }
}

/// The longest a Ghidra session lives; it normally ends long before, when it's dropped.
const SESSION_LIFETIME: Duration = Duration::from_secs(7 * 24 * 3600);
/// The longest one request (decompile a function, list functions) may take.
const REQUEST_TIME: Duration = Duration::from_secs(15 * 60);

/// The project every analysed target lives in (one per cache directory).
const PROJECT_NAME: &str = "craft-anything-project";
/// Written into the cache directory once Ghidra finished analysing and saved the program.
const ANALYSED_MARKER: &str = "analysed.ok";

/// `analyzeHeadless` arguments for the one-time analysis: import the snapshot, analyse it and save
/// it in the cached project (no bridge yet), with the optional processor/compiler-spec pin. A
/// `-cspec` is only emitted alongside a `-processor`, matching Ghidra's requirement. Pure, so it
/// can be unit-tested without a Ghidra install.
pub(crate) fn analyse_args(
    project_dir: &Path,
    snapshot: &Path,
    log: &Path,
    script_dir: &Path,
    language_id: Option<&str>,
    compiler_spec: Option<&str>,
) -> Vec<OsString> {
    let mut a: Vec<OsString> =
        vec![project_dir.as_os_str().to_owned(), OsString::from(PROJECT_NAME), OsString::from("-import"), snapshot.as_os_str().to_owned()];
    if let Some(lang) = language_id.map(str::trim).filter(|s| !s.is_empty()) {
        a.push(OsString::from("-processor"));
        a.push(OsString::from(lang));
        if let Some(cspec) = compiler_spec.map(str::trim).filter(|s| !s.is_empty()) {
            a.push(OsString::from("-cspec"));
            a.push(OsString::from(cspec));
        }
    }
    for (flag, v) in [("-log", log.as_os_str()), ("-scriptPath", script_dir.as_os_str()), ("-preScript", std::ffi::OsStr::new(FAST_SCRIPT_NAME))] {
        a.push(OsString::from(flag));
        a.push(v.to_owned());
    }
    a
}

/// The memory Java may give Ghidra, in GB: at least 4 (Ghidra's own default of 2 GB crawls or runs
/// out on a big game), at most 31 (past that Java loses its compressed pointers).
pub const HEAP_GB: std::ops::RangeInclusive<u64> = 4..=31;

/// A rough guide to the memory a program of a given size wants: (programs up to this many MB,
/// GB). Bigger than the last row: [`BIG_PROGRAM_GB`].
pub const HEAP_FOR_PROGRAM: &[(u64, u64)] = &[(50, 4), (200, 8), (1024, 16)];
pub const BIG_PROGRAM_GB: u64 = 24;

/// The memory a program of `bytes` wants, from [`HEAP_FOR_PROGRAM`].
pub fn suggested_heap_gb(bytes: u64) -> u64 {
    let mb = bytes >> 20;
    HEAP_FOR_PROGRAM.iter().find(|(up_to, _)| mb <= *up_to).map_or(BIG_PROGRAM_GB, |(_, gb)| *gb)
}

/// Ghidra's memory when the person hasn't set it: half of `machine_gb` (16 GB assumed when
/// unknown), within [`HEAP_GB`].
fn auto_heap_gb(machine_gb: Option<u64>) -> u64 {
    (machine_gb.unwrap_or(16) / 2).clamp(*HEAP_GB.start(), *HEAP_GB.end())
}

/// The Java heap setting for a run.
fn ghidra_heap(cfg: &Config) -> String {
    let gb = cfg.memory_gb.map(|g| g.clamp(*HEAP_GB.start(), *HEAP_GB.end())).unwrap_or_else(|| auto_heap_gb(machine_memory_gb()));
    format!("{gb}G")
}

/// This computer's memory in GB, looked up once (only when Ghidra starts with the automatic
/// amount: asking the system starts a program).
fn machine_memory_gb() -> Option<u64> {
    static MACHINE_GB: std::sync::OnceLock<Option<u64>> = std::sync::OnceLock::new();
    *MACHINE_GB.get_or_init(physical_memory_gb)
}

/// This computer's memory in GB, from the system.
fn physical_memory_gb() -> Option<u64> {
    let ask = |prog: &str, args: &[&str]| Process::new(prog).args(args).timeout(Duration::from_secs(15)).run().ok().map(|o| o.stdout_text());
    let bytes: u64 = if cfg!(windows) {
        ask("powershell", &["-NoProfile", "-NonInteractive", "-Command", "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"])?.trim().parse().ok()?
    } else if cfg!(target_os = "macos") {
        ask("sysctl", &["-n", "hw.memsize"])?.trim().parse().ok()?
    } else {
        let info = std::fs::read_to_string("/proc/meminfo").ok()?;
        info.lines().find_map(|l| l.strip_prefix("MemTotal:"))?.trim().trim_end_matches("kB").trim().parse::<u64>().ok()? * 1024
    };
    Some(bytes >> 30)
}

/// `analyzeHeadless` arguments to open the already-analysed program read-only (no re-analysis)
/// and run our bridge post-script on it.
pub(crate) fn bridge_args(project_dir: &Path, program: &str, log: &Path, script_log: &Path, script_dir: &Path, descriptor_path: &Path) -> Vec<OsString> {
    let mut a: Vec<OsString> = vec![project_dir.as_os_str().to_owned(), OsString::from(PROJECT_NAME), OsString::from("-process"), OsString::from(program)];
    for x in ["-noanalysis", "-readOnly"] {
        a.push(OsString::from(x));
    }
    for (flag, v) in [("-log", log), ("-scriptlog", script_log), ("-scriptPath", script_dir)] {
        a.push(OsString::from(flag));
        a.push(v.as_os_str().to_owned());
    }
    a.push(OsString::from("-postScript"));
    a.push(OsString::from(BRIDGE_SCRIPT_NAME));
    a.push(descriptor_path.as_os_str().to_owned());
    a
}

/// Whether the target in this cache directory was already analysed and saved.
pub fn is_analysed(project_dir: &Path) -> bool {
    project_dir.join(ANALYSED_MARKER).is_file()
}
/// Progress reports during the (sometimes long) startup.
pub type Progress<'a> = dyn Fn(f32, &str) + Send + Sync + 'a;
/// A cancel check shared with the caller.
pub type Cancel<'a> = dyn Fn() -> bool + Send + Sync + 'a;

fn random_token() -> String {
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let n = COUNTER.fetch_add(1, Ordering::Relaxed);
    let nanos = SystemTime::now().duration_since(SystemTime::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    let seed = format!("{}|{nanos}|{n}|ghidra-bridge", std::process::id());
    craft_anything_evidence::sha256_hex(seed.as_bytes())
}

/// A descriptor our post-script reads: where to listen and the token to require.
#[derive(Debug, Clone, Serialize)]
struct Descriptor {
    transport: &'static str,
    host: String,
    port: u16,
    token: String,
    run_id: String,
    target_sha256: String,
    settings_hash: String,
    /// The endpoint file the bridge writes once it is listening.
    endpoint_path: String,
}

/// A live Ghidra session: an owned headless process plus an authenticated socket to our bridge.
pub struct Session {
    client: Mutex<Client>,
    /// Kept alive so its drop kills the process group. In a `Mutex` so the session is `Sync`.
    _process: Mutex<RunningProcess>,
    runtime_root: PathBuf,
    version: Option<String>,
    /// The forced language id, when Deep mode was pinned to a processor.
    language_id: Option<String>,
    /// Where Ghidra loaded the program, from the bridge's handshake.
    image_base: Option<u64>,
}

impl std::fmt::Debug for Session {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("GhidraSession").field("runtime_root", &self.runtime_root).finish()
    }
}

impl Drop for Session {
    fn drop(&mut self) {
        // Ask the bridge to shut down cleanly; the process-group kill (RunningProcess drop) is the
        // backstop. Then remove the runtime root.
        if let Ok(mut c) = self.client.lock() {
            c.shutdown();
        }
        // Stop Ghidra before removing its folder: on Windows it holds its files open.
        if let Ok(p) = self._process.lock() {
            p.kill();
        }
        remove_soon(&self.runtime_root);
    }
}

/// The cache directory for an analysed target, keyed by content and profile.
pub fn project_cache_dir(store: &Path, target_sha256: &str, settings_hash: &str) -> PathBuf {
    let key = format!("{}-{}", target_sha256.get(..16).unwrap_or(target_sha256), settings_hash.get(..16).unwrap_or(settings_hash));
    // Ghidra rejects project path elements that start with a dot.
    store.join("ghidra-cache").join(key)
}

/// Create a fresh private directory under `base`.
fn private_dir(base: &Path, prefix: &str) -> Result<PathBuf, GhidraError> {
    let nanos = SystemTime::now().duration_since(SystemTime::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    let name = format!("{prefix}-{}-{nanos}", std::process::id());
    let p = base.join(name);
    make_private_dir(&p)?;
    Ok(p)
}

fn make_private_dir(p: &Path) -> Result<(), GhidraError> {
    let mut b = std::fs::DirBuilder::new();
    b.recursive(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt as _;
        b.mode(0o700);
    }
    b.create(p).map_err(|e| GhidraError::Launch(format!("creating {}: {e}", p.display())))
}

/// A private working folder removed when dropped (also on every error path).
struct Scratch(PathBuf);

impl Scratch {
    fn new(store: &Path, prefix: &str) -> Result<Scratch, GhidraError> {
        let root = private_dir(store, prefix)?;
        for sub in ["home", "tmp", "project"] {
            make_private_dir(&root.join(sub))?;
        }
        Ok(Scratch(root))
    }

    /// Hand the folder over (the session removes it when it ends).
    fn keep(self) -> PathBuf {
        let p = self.0.clone();
        std::mem::forget(self);
        p
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        remove_soon(&self.0);
    }
}

/// Copy the logs of a bridge that stopped early to `dest` beside the saved analysis (the runtime
/// folder they're in is removed with the error), and return where to read them: `dest`, or the
/// first log if nothing could be copied.
fn keep_log(logs: &[&Path], dest: &Path) -> PathBuf {
    let text: Vec<u8> = logs.iter().filter_map(|p| std::fs::read(p).ok()).collect::<Vec<_>>().join(&b"\n"[..]);
    if !text.is_empty() && std::fs::write(dest, &text).is_ok() {
        return dest.to_path_buf();
    }
    logs.first().map(|p| p.to_path_buf()).unwrap_or_else(|| dest.to_path_buf())
}

/// Remove a folder, retrying briefly: on Windows a Ghidra that was just stopped can still hold
/// its files open for a moment.
fn remove_soon(dir: &Path) {
    for _ in 0..20 {
        if std::fs::remove_dir_all(dir).is_ok() || !dir.exists() {
            return;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}

/// Start `analyzeHeadless` with its home and temp folders inside `runtime_root`.
fn headless(cfg: &Config, runtime_root: &Path, args: Vec<OsString>, lifetime: Duration) -> Result<RunningProcess, GhidraError> {
    let mut proc = Process::new(&cfg.analyze_headless)
        .args(&args)
        .env("HOME", runtime_root.join("home"))
        .env("TMPDIR", runtime_root.join("tmp"))
        .env("XDG_CACHE_HOME", runtime_root.join("tmp"))
        .env("XDG_CONFIG_HOME", runtime_root.join("home"))
        .env("XDG_DATA_HOME", runtime_root.join("home"))
        // Ghidra's launcher reads this for the headless Java heap.
        .env("GHIDRA_HEADLESS_MAXMEM", ghidra_heap(cfg))
        .stdin(StdinMode::Closed)
        .timeout(lifetime)
        .stdout_cap(4 * 1024 * 1024)
        .stderr_cap(1024 * 1024)
        .label("Ghidra headless");
    if let Some(home) = &cfg.java_home {
        proc = proc.env("JAVA_HOME", home);
    }
    proc.spawn().map_err(|e| GhidraError::Launch(e.message))
}

/// Held while one process analyses a target; others wait for its result. Refreshed every few
/// seconds, so one left behind by a process that died goes stale and is taken over.
const LOCK_STALE: Duration = Duration::from_secs(90);

/// The analysis lock this process holds, released when dropped (also on every error path).
struct HeldLock(PathBuf);

impl Drop for HeldLock {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
    }
}

fn lock_path(project_dir: &Path) -> PathBuf {
    project_dir.with_extension("analysing")
}

fn lock_is_fresh(lock: &Path) -> bool {
    std::fs::metadata(lock).and_then(|m| m.modified()).is_ok_and(|t| t.elapsed().is_ok_and(|age| age < LOCK_STALE))
}

/// Make sure the target is analysed and saved in its cached project, analysing it now if no one
/// has (a big program can take hours; it happens once). If another process is already analysing
/// it, wait for that instead of starting over. Returns the cached project folder.
pub fn analyse(
    cfg: &Config,
    target_bytes: &[u8],
    target_sha256: &str,
    settings_hash: &str,
    cancel: &Cancel<'_>,
    progress: &Progress<'_>,
) -> Result<PathBuf, GhidraError> {
    let started = Instant::now();
    let minutes = || started.elapsed().as_secs() / 60;
    let deadline = started + cfg.startup_timeout;
    let project_dir = project_cache_dir(&cfg.store_dir, target_sha256, settings_hash);
    let lock = lock_path(&project_dir);
    // The lock sits beside the project, in the cache folder a fresh store doesn't have yet.
    make_private_dir(lock.parent().unwrap_or(&cfg.store_dir))?;
    loop {
        if is_analysed(&project_dir) {
            return Ok(project_dir);
        }
        if cancel() {
            return Err(GhidraError::Cancelled);
        }
        if Instant::now() >= deadline {
            return Err(GhidraError::Timeout(format!("Ghidra's analysis didn't finish within {} s", cfg.startup_timeout.as_secs())));
        }
        if lock_is_fresh(&lock) {
            progress(0.05, &format!("waiting for Ghidra's analysis of this program, started earlier ({} min so far)", minutes()));
            std::thread::sleep(Duration::from_secs(2));
            continue;
        }
        // Stale or none: take it (create_new, so only one of two racing processes wins).
        let _ = std::fs::remove_file(&lock);
        match std::fs::OpenOptions::new().write(true).create_new(true).open(&lock) {
            Ok(_) => break,
            Err(e) if e.kind() != std::io::ErrorKind::AlreadyExists => {
                return Err(GhidraError::Launch(format!("taking the analysis lock {}: {e}", lock.display())));
            }
            Err(_) => {}
        }
    }
    let held = HeldLock(lock.clone());
    let scratch = Scratch::new(&cfg.store_dir, "ghidra-analysis")?;
    let program = format!("target-{}", target_sha256.get(..12).unwrap_or(target_sha256));
    // Beside the saved analysis, so it can be read after a failure.
    let log = project_dir.with_extension("log");
    remove_soon(&project_dir);
    make_private_dir(&project_dir)?;
    let script_dir = scratch.0.join("scripts");
    make_private_dir(&script_dir)?;
    write_atomic_private(&script_dir.join(FAST_SCRIPT_NAME), FAST_SCRIPT.as_bytes())
        .map_err(|e| GhidraError::Launch(format!("writing the analysis script: {e}")))?;
    let snapshot = scratch.0.join(&program);
    write_atomic_private(&snapshot, target_bytes).map_err(|e| GhidraError::Launch(format!("copying the target: {e}")))?;
    if craft_anything_evidence::sha256_hex(target_bytes) != target_sha256 {
        return Err(GhidraError::Launch("target bytes do not match the expected sha256".into()));
    }
    progress(0.02, "Ghidra is analysing the program (once per program; a big one can take hours)");
    let remaining = deadline.saturating_duration_since(Instant::now());
    let mut running = headless(
        cfg,
        &scratch.0,
        analyse_args(&project_dir, &snapshot, &log, &script_dir, cfg.language_id.as_deref(), cfg.compiler_spec.as_deref()),
        remaining,
    )?;
    let mut last_progress = Instant::now();
    let done = loop {
        if cancel() {
            return Err(GhidraError::Cancelled);
        }
        if let Some(r) = running.wait_timeout(Duration::from_millis(500)) {
            break r.as_ref().map(|o| o.success).map_err(|e| e.message.clone());
        }
        if last_progress.elapsed() >= Duration::from_secs(10) {
            // Keeps the lock fresh, so waiters know this analysis is alive.
            let _ = std::fs::write(&lock, minutes().to_string());
            let frac = (started.elapsed().as_secs_f32() / cfg.startup_timeout.as_secs_f32()).min(0.9);
            progress(frac.max(0.05), &format!("Ghidra is analysing the program ({} min so far; once per program)", minutes()));
            last_progress = Instant::now();
        }
    };
    match done {
        Ok(true) => write_atomic_private(&project_dir.join(ANALYSED_MARKER), program.as_bytes())
            .map_err(|e| GhidraError::Launch(format!("saving the analysis: {e}")))?,
        Ok(false) => return Err(GhidraError::Launch(format!("Ghidra's analysis failed; see {}", log.display()))),
        Err(m) => return Err(GhidraError::Timeout(m)),
    }
    drop(held);
    Ok(project_dir)
}

impl Session {
    /// Launch Ghidra on `target_bytes` and connect: analyse it first if no one has (see
    /// [`analyse`]), then open the saved analysis with our bridge. Never hangs past its deadlines.
    pub fn start(
        cfg: &Config,
        target_bytes: &[u8],
        target_sha256: &str,
        settings_hash: &str,
        cancel: &Cancel<'_>,
        progress: &Progress<'_>,
    ) -> Result<Session, GhidraError> {
        let run_id = random_token();
        let token = random_token();
        let project_dir = analyse(cfg, target_bytes, target_sha256, settings_hash, cancel, progress)?;
        let scratch = Scratch::new(&cfg.store_dir, "ghidra-runtime")?;
        let runtime_root = scratch.0.clone();
        let program = format!("target-{}", target_sha256.get(..12).unwrap_or(target_sha256));
        let log = runtime_root.join("ghidra.log");
        let minutes = |since: Instant| since.elapsed().as_secs() / 60;
        // Ship our post-script into the runtime root (Ghidra loads scripts from -scriptPath).
        let script_dir = runtime_root.join("scripts");
        make_private_dir(&script_dir)?;
        write_atomic_private(&script_dir.join(BRIDGE_SCRIPT_NAME), BRIDGE_SCRIPT.as_bytes())
            .map_err(|e| GhidraError::Launch(format!("writing the bridge script: {e}")))?;

        // The bridge listens on a loopback port it chooses; it reports the port in the endpoint
        // file. We pass a descriptor with the token and the endpoint path.
        let endpoint_path = runtime_root.join("bridge-address.json");
        let descriptor = Descriptor {
            transport: "loopback-tcp-token",
            host: Ipv4Addr::LOCALHOST.to_string(),
            port: 0,
            token: token.clone(),
            run_id: run_id.clone(),
            target_sha256: target_sha256.to_string(),
            settings_hash: settings_hash.to_string(),
            endpoint_path: endpoint_path.display().to_string(),
        };
        let descriptor_path = runtime_root.join("session.json");
        write_atomic_private(&descriptor_path, &serde_json::to_vec(&descriptor).unwrap_or_default())
            .map_err(|e| GhidraError::Launch(format!("writing the session descriptor: {e}")))?;

        progress(0.92, "opening the analysed program in Ghidra");
        let script_log = runtime_root.join("script.log");
        // The bridge lives as long as this session (its drop stops it), not a fixed time.
        let mut running =
            headless(cfg, &runtime_root, bridge_args(&project_dir, &program, &log, &script_log, &script_dir, &descriptor_path), SESSION_LIFETIME)?;
        let opened = Instant::now();

        // Poll for the endpoint file, honouring the deadline and cancel.
        let deadline = Instant::now() + cfg.startup_timeout;
        let mut last_progress = Instant::now();
        let addr = loop {
            if cancel() {
                return Err(GhidraError::Cancelled);
            }
            if let Some(a) = read_endpoint(&endpoint_path) {
                break a;
            }
            if running.is_finished() {
                // The saved analysis didn't open (moved, damaged): analyse again next time.
                let _ = std::fs::remove_file(project_dir.join(ANALYSED_MARKER));
                let kept = keep_log(&[&log, &script_log], &project_dir.with_extension("bridge.log"));
                return Err(GhidraError::Launch(format!("Ghidra stopped before the bridge started; see {}", kept.display())));
            }
            if Instant::now() >= deadline {
                return Err(GhidraError::Timeout(format!("Ghidra did not become ready within {} s", cfg.startup_timeout.as_secs())));
            }
            if last_progress.elapsed() >= Duration::from_secs(10) {
                progress(0.95, &format!("Ghidra is opening the analysed program ({} min)", minutes(opened)));
                last_progress = Instant::now();
            }
            std::thread::sleep(Duration::from_millis(100));
        };
        progress(0.97, "connecting to the analysis bridge");
        let mut client = Client::connect(addr, &token, deadline)?;
        // First ping proves the token and that analysis finished.
        let info = client.ping(cancel, deadline)?;
        let version = info.get("provider").and_then(|p| p.get("version")).and_then(Value::as_str).map(String::from);
        let image_base = image_base_of(&info);
        if info.get("analysis_cut_short").and_then(Value::as_bool) == Some(true) {
            return Err(GhidraError::Timeout("Ghidra reported that analysis timed out".into()));
        }
        progress(1.0, "Ghidra is ready");

        Ok(Session {
            client: Mutex::new(client),
            _process: Mutex::new(running),
            runtime_root: scratch.keep(),
            version,
            language_id: cfg.language_id.as_deref().map(str::trim).filter(|s| !s.is_empty()).map(String::from),
            image_base,
        })
    }

    fn lock(&self) -> craft_anything_platform::sync::MutexGuard<'_, Client> {
        self.client.lock().unwrap_or_else(PoisonError::into_inner)
    }

    /// The deadline for one request: a huge function in a big program can take Ghidra minutes.
    fn request_deadline() -> Instant {
        Instant::now() + REQUEST_TIME
    }
}

impl DeepDecompiler for Session {
    fn engine(&self) -> &'static str {
        "ghidra"
    }

    fn engine_version(&self) -> Option<String> {
        self.version.clone()
    }

    fn language_id(&self) -> Option<String> {
        self.language_id.clone()
    }

    fn image_base(&self) -> Option<u64> {
        self.image_base
    }

    fn decompile(&self, entry: u64) -> Result<Option<DeepFunction>, GhidraError> {
        let never_cancel = || false;
        let v = self.lock().request(
            "native_function_pseudocode",
            serde_json::json!({"address": format!("{entry:#x}")}),
            &never_cancel,
            Self::request_deadline(),
        )?;
        Ok(decompiled(entry, &v))
    }

    fn list_functions(&self) -> Result<Vec<DeepFunction>, GhidraError> {
        let never_cancel = || false;
        let v = self.lock().request("native_functions_list", serde_json::json!({}), &never_cancel, Self::request_deadline())?;
        let mut out = Vec::new();
        for f in v.get("functions").and_then(Value::as_array).into_iter().flatten() {
            let entry = f.get("address").and_then(Value::as_str).and_then(parse_hex).unwrap_or(0);
            out.push(DeepFunction {
                entry,
                name: f.get("name").and_then(Value::as_str).unwrap_or_default().to_string(),
                signature: None,
                pseudocode: None,
                created: false,
            });
        }
        Ok(out)
    }
}

/// The bridge's `native_function_pseudocode` reply as a function (`null` means no answer).
fn decompiled(entry: u64, v: &Value) -> Option<DeepFunction> {
    if v.is_null() {
        return None;
    }
    Some(DeepFunction {
        entry,
        name: v.get("name").and_then(Value::as_str).unwrap_or_default().to_string(),
        signature: v.get("signature").and_then(Value::as_str).map(String::from),
        pseudocode: v.get("pseudocode").and_then(Value::as_str).map(String::from),
        created: v.get("created").and_then(Value::as_bool).unwrap_or(false),
    })
}

/// Where the bridge's handshake says Ghidra loaded the program (`None` when it didn't say).
fn image_base_of(ping: &Value) -> Option<u64> {
    ping.get("target").and_then(|t| t.get("image_base")).and_then(Value::as_str).and_then(parse_hex)
}

fn parse_hex(s: &str) -> Option<u64> {
    let t = s.trim();
    let h = t.strip_prefix("0x").or_else(|| t.strip_prefix("0X")).unwrap_or(t);
    u64::from_str_radix(h, 16).ok()
}

/// Read the endpoint file the bridge writes once listening: `{"host":"127.0.0.1","port":N}`.
fn read_endpoint(path: &Path) -> Option<SocketAddr> {
    let bytes = std::fs::read(path).ok()?;
    let v: Value = serde_json::from_slice(&bytes).ok()?;
    let host: Ipv4Addr = v.get("host").and_then(Value::as_str)?.parse().ok()?;
    let port = u16::try_from(v.get("port").and_then(Value::as_u64)?).ok()?;
    if port == 0 {
        return None;
    }
    Some(SocketAddr::from((host, port)))
}

#[cfg(test)]
mod tests;
