# Pitfalls

Mistakes made while building this project, what they cost, and the rule that prevents each one.
Read this before your first change; add to it when you make a new mistake worth not repeating.
Keep entries short: what happened, then the rule.

## Git and pull requests

**A commit landed on `main` without a PR.** `git switch main && git pull` was run with uncommitted
changes: the switch succeeded, the pull refused, and the failure was read as "still on my branch".
The next commit and `git push --force-with-lease` went to `main`.
- Check `git branch --show-current` before every commit and push.
- Push by name (`git push origin <branch>`), never a bare `git push` after switching around.
- Commit or stash before switching branches; read every line of a failed compound command.
- Maintainers: protect `main` (PRs required, squash only) so this can't happen.

**A PR merged with only its claim.** One shell command did commit, push, `gh pr create` and
`gh pr merge`; the pre-commit hook failed (it ran `cargo xtask secrets` on an older default Rust),
the `&&` chain stopped, but the next lines still ran, so #138 merged the claim commit under the
work's title. Run commit, push, create and merge as separate steps and read each result; run the
hook with the project's toolchain (`RUSTUP_TOOLCHAIN=1.99.0 git commit …`).

**A merge of commits no check ran on.** A script waited for one CI run of a PR, then merged
whatever the PR's head was by then; its author had pushed two more commits meanwhile, so #141
reached `main` with code neither CI nor review had seen. Merge with `--match-head-commit` set to
the commit the green run tested (`gh run view <id> --json headSha`), never to a head read later.

**A squash commit names the wrong PR number.** The subject was written as "(#12)" before the PR
existed; it became #11. Take the number from `gh pr create`'s output (`${URL##*/}`) and use it.

**Two PRs pass alone and break `main` together.** One tightened `cargo xtask layers`, the other
added an app the new rule rejected; both were green on their own branch.
- Before merging a PR that was rebased before another merge, build and test the merged result:
  `git merge-tree --write-tree origin/main origin/<branch>` for conflicts, then a temporary branch
  with the merge, `cargo test --workspace`, clippy and `cargo xtask layers`.
- After merging several PRs in a row, run the full checks on `main` once more.
- It happened again with translations: #117 added UI strings and #115, merged right after it,
  added a check that every string has a Chinese translation, so `cargo xtask ci` failed on
  `main`. A PR that adds a check, or adds what a check covers, is tested on top of the other.

**A dependency change merged without its lockfile.** Changes were staged with
`git add -A crates apps docs`, which leaves out the root `Cargo.lock`, so a new dependency reached
`main` without its lock entry. Stage by `git add -A` (then review `git status`), or list `Cargo.lock`
whenever a `Cargo.toml` changed.

**A superseded PR on someone else's branch.** Rebasing it means force-pushing their branch. Replay it
on a new branch, open a new PR that says it supersedes the old one, and comment on the old one.
Don't close or rewrite other people's work without asking.

## Tests

**A test started a real download on a contributor's machine.** A test called `engines_install` for
Unity; a later change made that download the vendor installer and open it on Windows. It also
created folders in the real config directory (`Session::default()` uses it).
- Tests never touch the network, never start installers or GUI programs, and never write outside a
  temp folder. Use ids that are refused before any I/O, or local stand-in servers.
- When you widen what a tool does (a new download, a launch), grep the tests that call it.
- Tests build their session with `craft_anything_engine::testing::session()` (config, plugin
  caches, engine store and projects in a temp folder); `cargo xtask layers` rejects
  `Session::default()`. CLI tests set `CRAFT_ANYTHING_CONFIG_DIR` to a temp folder.

**A demo app wired to the person's settings.** The headless app the UI tests use built its AI hub
with `AiHub::new`, which saves to the real `config.toml` and the system keychain; no test had
added or removed an AI yet, so nothing noticed. Everything a test app can save goes to a temp
folder (`AiHub::with_stores`), not only the engine's session.

**A test that passes only where a program is installed.** A tool's `Requires::Engine` is checked
before it runs, so a test of its input checks passed on a machine with ilspycmd and failed on one
without. Point the test session's `engines.tools` path at a stand-in file when the tool refuses
before running anything, and run new tests on a machine without the program.
It happened again when Clean room began refusing tools before their program is looked for: a
"missing adb" test returned early on a machine with adb and failed in CI without it. A test of
what happens without a program builds its session in the mode the tool runs in.
It happened a third time with Ghidra: the test session's engine store was empty, but the lookup
still searched PATH, `~/.local/bin` and `/opt/ghidra`, so two Deep-mode tests got Ghidra's answer
on a machine that had it. `testing::session()` now sets `engines.only_configured`, so it finds only
the engines its settings or store name.

**A failing crate hid the next crate's tests.** `cargo test -p a -p b` stopped after a failure in
`a`, so `b`'s tests never ran; the rerun was filtered to the failing test, and a broken engine id
reached `main`. Run with `--no-fail-fast`, and after a fix rerun the whole crates, not a filter.

**A test that changes the whole process.** A UI test raised the process-wide stuck-lock banner; in
CI the banner moved the layout under another test running beside it, and its click missed. It passed
25 runs on a Mac. Anything a test sets for the whole process goes in a test program of its own.

**Fixtures that leak into each other.** A "nothing here" path sat beside a fake game folder in the
same temp directory, and game detection walked up and found the game. Give each case its own
`tempfile::tempdir()`.

**Proving a refactor changed nothing.** Unit tests that check substrings can miss changed prompts.
For a refactor that must keep output identical, dump the outputs for every combination before and
after and compare them byte for byte (done for every brief across 162 combinations in R1.1).

## Building and running

**Rebuilding a binary that is running fails on Windows** ("Access is denied"), and the next command
silently used the old binary. Long-running binaries (live rebuilds, servers) get their own
`CARGO_TARGET_DIR`.

**A program started from a screen outlived the tests.** The Ghidra memory setting first asked
PowerShell for the computer's memory on a background thread while the screen drew; in UI tests
the test process ended first, the orphaned PowerShell kept the test runner's output pipe open,
and `cargo test | grep` never returned. Screens never start programs, not even "in the
background"; read a setting or a value a worker already has.

**Asking a process to stop isn't stopping it.** `RunningProcess::kill()` only raises a flag for the
supervisor thread; the window-capture tool returned and the CLI exited before the thread acted, so
the program it opened stayed open (and held the shell's pipe, so the command never returned). When
the caller may exit next, use `kill_and_wait`, and check after a live run that nothing was left
running.

**The newest program isn't the app.** Play started the newest executable in `target/`; a
workspace that builds an app and its CLI started the CLI, which printed help and quit with no
console, so the button did nothing, three times in a row. Pick what to start from what the project
declares (Cargo manifests: `default-run`, the package using a window library), never from file
dates, and make a start that exits at once say so.

**A launcher's exit read as the program's.** On some Windows machines `chrome.exe` hands the
browser to a second process and exits; the supervisor took that exit as the run ending and stopped
the whole group, so websites never opened ("closed after 0.3 s"). Where it didn't hand off, the
browser outlived the CLI (the job isn't killed when closed) and held the shell's output pipe, so
the command hung and old browsers piled up. Start programs that hand off with `.hands_off()`, and
after a live run check that the command returned and nothing it started is still running.

**A separate config folder hides the agent's own settings.** To keep a live run from touching the
real `config.toml`, `XDG_CONFIG_HOME` was pointed at a scratch folder; the agent CLI we start reads
the same variable, lost its own provider settings, and failed with "unsupported provider". Back up
`config.toml` and restore it after the run instead, and leave the agent's environment as it is.

**A renamed CLI can't start the builder's tools.** To keep a live run's binary from being locked, it
was copied as `cli-r25.exe`; the CLI finds itself by name (`craft-anything-cli`) to start the
builder's MCP server, so Claude Code saw no tools and stopped. Copy it under its own name into a
folder of its own.
It happened again in a release: the macOS app bundle had only `craft-anything`, with the CLI in
a separate zip, so every Claude Code build from the 0.2.0 DMG failed the same way (#91). Every
package that ships the app ships the CLI beside its executable, and the packaging script runs
the CLI from the finished package before it's published.
Its symptom misled people too: Claude Code's MCP log says `Executable not found in $PATH: "stdio"`
for any command that won't start, so #64 went looking for a bad config. Reproduce with the real
program before believing what a log's wording suggests.

**A Windows path with forward slashes read as nothing.** rtl_433 decoded a recording in the shell
but found no messages, and exited 0, when the test passed `C:/…/x.cu8`; it only reads Windows
paths with backslashes. Hand external programs native paths (`\` on Windows), and give each
external tool a live test that checks it really produced output, not just that it exited 0.
It happened again with Explorer: project folders are kept as `D:/Projects/…\name`, and "Open
folder" opened Documents. Paths for the system's programs go through `platform::native_path`.

**A message on the command line.** Claude Code was handed the whole task as `-p <message>`; a
34,641-character brief passed Windows' 32,767-character command-line limit, so the build never
started ("The filename or extension is too long", os error 206, #402). Give a program anything
that can grow (messages, briefs, lists of files) on stdin or in a file, never in argv.

**Console windows popping up over the app.** Only the detached launcher hid the console; the
supervised runner didn't, so Ghidra's `.bat` and PowerShell each opened a console window during a
real Deep-mode run (the CLI never shows it: it already has a console). Every child started from
the windowed app gets `CREATE_NO_WINDOW`; check the desktop app, not only the CLI, after adding a
program.

**A graphics backend that crashed before it was chosen.** We ranked GL last when picking an
adapter, but eframe starts every backend first, and starting GL loaded an old Intel OpenGL driver
that crashed the app before any window or error box (#196). Ranking can't protect you from a
backend that's started at all: start only the backends the app may use.
It happened again with Vulkan on Windows (#394): starting Vulkan loaded an Intel Vulkan driver
(`igvk64.dll`) that crashed with `0xc0000005` on startup. Windows now starts DX12 only by default
(which includes WARP); `WGPU_BACKEND` still allows choosing other backends.

**A Mac app that couldn't find Claude Code, and offered a GitHub key instead.** An app opened from
the Dock gets the system's short `PATH`, not the shell's, so `claude` in `~/.local/bin` wasn't
found; "Built by" then fell back to "Claude Code on github.com-work", an `~/.ssh/config` alias
for a second GitHub key, read as a computer to build on. Look programs up and start them with
`which::search_path` (`Process` and `Launch` do), and leave git servers out of SSH hosts.

**Found on Windows, but "isn't on your PATH" when run.** npm installs Gemini CLI, Codex and often
Claude Code as `gemini.cmd`-style shims; `which` finds them through `PATHEXT`, but Rust starts
only `.exe` files by bare name, so every build failed (#18). Through `cmd.exe` a prompt with line
breaks or over 8191 characters wouldn't arrive anyway. `Process` runs an npm shim's script with
Node directly (`which::launch_target`); test a new program on Windows with a multi-line argument.
npm also writes an extensionless POSIX script beside each shim, and `which` returned that first,
so OpenCode was offered and then every run said it wasn't installed (#41): look up the kinds
Windows can start (`PATHEXT`) before the bare name.

**A first analysis that waited for a lock it could never take.** Ghidra's analysis lock is created
with `create_new` in `ghidra-cache/`, which only existed on machines that had used it before; on a
fresh store the create failed and the loop read that as "someone else holds it" until the
deadline. Create a lock's folder first, and treat any error but "already exists" as a failure.

**A bridge that didn't compile.** A helper in the Ghidra bridge was named like a public
`GhidraScript` method, so Ghidra refused the script and the run only said the bridge stopped.
Compile the `.java` against Ghidra's jars (`javac -proc:none -cp <Ghidra/**/lib/*.jar>`) before a
live run. Ghidra also rejects project paths with a folder starting with a dot, as
`tempfile::tempdir()`'s do: give live-test temp folders a plain prefix.

**Stopping a long run leaves children behind** unless every program goes through
`craft_anything_platform::process`. After stopping one, check that its child processes are gone.

**Separate target folders fill the disk.** Agents given their own `CARGO_TARGET_DIR` under
`target/` (to avoid locking a running exe) left them behind; one reached 79 GB and the disk filled
mid-build ("not enough space", os error 112). Delete an agent's target folder when its work is
merged, and check `du -sh target/*` when a build fails to write.
It happened again from a commit: the pre-commit hook builds `cargo xtask secrets`, and in a new
worktree with no `CARGO_TARGET_DIR` set that is a whole fresh build in its `target/`, which filled
the disk under a person's running build. Commit with the same `CARGO_TARGET_DIR` you built with,
and check free space (`df -h`) before a build next to someone else's work.
And again from the main `target/`: its incremental cache alone had reached 46 GB (81 GB in
`target/debug`) and the drive hit 0 bytes mid-test. Delete `target/debug/incremental` when it
grows, and build checks with `CARGO_INCREMENTAL=0`.

**A green PR that ran nothing.** `gh pr view` said `CLEAN`/`MERGEABLE`, but while the repository is
private every CI job is skipped, so nothing had been checked. Read the checks' conclusions, not the
merge state. Without CI, run its steps locally with `--locked`; a Mac can compile for the other
systems with `cargo check --target`, with zig as the C compiler for `ring` (a wrapper that drops the
`--target=` flag `cc` adds), but that only proves it compiles.

**Unformatted code reached `main`.** A test was edited by script after `cargo fmt --all` had run,
so #53 merged with a long line rustfmt rewraps. Run `cargo fmt --all --check` last, after every
edit, right before committing.

## Design

**Reading literals and skipping the rest.** The Electron window reader skipped a spread inside
`webPreferences`, so a window whose preferences came partly from another object was reported as
"contextIsolation is not set; the default applies", which nobody had checked until a live run on
an installed app. When a reader takes literal values, anything that may add or replace them
(spreads, computed keys, later writes) makes the result unknown, never the default; and check new
readers on real, minified inputs, not only on the shapes the tests were written for.

**A naming scheme that clients can't accept.** Dotted tool ids (`web.page.capture`) were decided
before checking that MCP clients and model APIs allow only `[A-Za-z0-9_-]` in tool names. Check
external constraints (protocols, APIs, file systems) before fixing a public contract.

**A tool planned in a layer that can't reach what it needs.** Rebuild control as engine tools (L4)
can't call `RebuildRun` (L5). Before planning a tool, check which crate owns what it calls; if a
higher layer owns it, it needs a way for that layer to register tools (R1.7).

**An event queue drained in the middle of a run.** A scripted browser session's `goto` step
cleared the CDP event queue to "start fresh", so every network request before and during the
navigation vanished from the run's network capture. Only the code that owns a run's results
drains its event queue; steps leave events where they are, and the run keeps them all, tagged
with the step they arrived in.

**Two writers to one file.** The app and the rebuild run both wrote `feed.json`. Give each persisted
file one owner; when another writer is unavoidable (an answer given from the CLI while a run is
going), merge what's on disk before saving instead of overwriting it.
The same happened in `craft.json`: a run saved from the copy it started with and undid a budget
the person raised meanwhile (and any "always allow" answer). Fields the person owns change only
through `Workspace::set_person`; `save` keeps them as they are on disk.
And again inside one process: the engine had its own `write_atomic` whose temp file was named
by process only, so two threads saving `craft.json` wrote the same temp file and one rename found
it gone (#273). There is one atomic writer, `craft_anything_platform::fs::write_atomic`; don't
write another.

**Keywords that only some code paths honour.** "…in Rust" picked Rust for apps but not for games, so
a headless game rebuild stopped at once for want of Unity. It was found only by a live run. Run the
real flow end to end after changing how requests are read, and add the case as a test.

**A default given as an order.** "A notes app in Electron" was built in Rust: the brief quoted the
request, then said "Use Rust with eframe/egui… create a cargo project" with nothing saying which
wins, and the builder followed the later, more specific line; the app, the build check and Play
followed the stack picked at the start too. Say that the person's words come first and phrase a
default as one ("unless their request says otherwise"); let what acts on the result (checks,
Play, the recorded stack) look at what was built, not at what was planned.

**More than one way to build the engine.** The CLI's `commands` listing built its own engine
from default settings, so it missed the plugins (and the person's settings) every other command
had. Build the engine through one function per app (`make_engine` in the CLI) and add new layers'
tools and plugins there.

**A best-effort step that hides its errors.** Capturing a site's extra pages used `.is_ok()`, so a
missing parent folder made every page silently drop out; only a live run showed "Photographing more
pages" followed by nothing. When a step may fail without stopping the run, still say why (the feed,
a note, a log line), and test the success path end to end, not just the picking.
The fix then made the check create `checks/round-N/routes/` first, which made `round-N` exist, and
`web_site_capture` (which refuses an existing folder) stopped the run. Create a tool's output parent
right before that tool runs, never a folder that another tool must create itself.

**A size measured after drawing, used a frame late.** The prompt box's height was measured each
frame and used to size the feed on the next, so every time it grew or shrank one frame showed it
100 px too low, and typing looked like flicker. When a layout uses a size from the last frame,
call `ctx.request_discard` when it changed, so egui lays the frame out again before showing it.
The same layout then came out 17 points taller than the space it was given: it left out the item
spacing after the feed, and `ui.horizontal` centred the 85-point box 12 points down in its row.
The agent console's panel grows to fit its content, so it grew 17 points every frame until its
maximum, and then the top of its tabs was cut off. When a part is sized to fill what's left, count
the item spacing and use `horizontal_top` for tall rows, and test that the panel's size holds still
over several frames.

**A library default that blinked over a text field.** egui's scroll areas fade their edge when
there's more below; the prompt box's one measured a few points of overflow on the frame after each
keystroke, so a dark gradient blinked over the line being typed. Unit tests look at text, not at
what's painted over it. When something flickers, render the frames (`Harness::render` at a
fractional scale) and diff them, then list the shapes painted over the spot.

**A tool that locked the session it was called with.** `rebuild_question_ask` read the settings
with `hub.engine.session()`, but a tool runs while its call holds the session, so the CLI waited
forever before starting anything (found by the first live run, not by tests, which stopped
earlier with no AI set up). Inside a tool, read what you need from `ctx.session` and hand it on;
test a tool through `Engine::call` with a time limit on a thread.

**A forked session's cost is the session's.** Claude Code's `total_cost_usd` for a
`--fork-session` run is the whole session's running total ($22.67 for a question that cost cents).
Don't show a cost you can't attribute to the thing it's shown beside.

**An option that offered nothing new.** Asked for "a shallow live copy", the pin dialog got a
Live choice that copied nothing and opened the project's app, which is exactly Play, under a
name that suggested something was kept. It was merged, tested and installed before anyone asked
what it was for. Before adding a choice, write one sentence on what it gives that the existing
path doesn't; if there's no such sentence, ask what was meant.
Its replacement nearly repeated it: hard-linking dependencies saved almost nothing on real
projects, because 85% of a Rust pin was a `.pdb` nothing needs. Measure on real data before
designing around where you assume the size is.

**Long content above a fixed prompt box.** Answers to questions were cards between the feed and
the prompt box, sized to their text; the feed got what was left, so a long answer squeezed it and
pushed the box off the window. Content of any length belongs inside the scroll area. And an X on
something that can't be brought back is a delete: offer folding instead, and keep the data.

**A library default that hid the scroll bars.** egui's thin scroll bars paint the thumb in the
button fill and the track in the field colour; our theme made those the same, and the thin
preset narrows the bar to 2 px at rest, so the thumb showed only on hover. When a theme sets a
library's colours, check every widget that borrows them, in both themes, and test contrast with
numbers (3:1 for parts you interact with), not by eye.

**Files read while drawing.** The Project screen parsed `package.json` 2–4 times a frame, listed
the reference pictures and checked screenshot files on every repaint, and read the side panel's
files on every frame a build event arrived; on a slow or network drive the window would freeze.
Drawing reads only memory: anything from disk is read on a worker when something changes, and
the screen shows the last result.

**A non-blocking read that falls back to defaults.** The app read the person's settings with
`try_session().unwrap_or_default()` at startup, so a busy engine meant Clean room and no AI, and
the next settings change saved those defaults over theirs. Seen once in a live run. A fallback
must never stand in for data that gets saved back: wait (it's startup), or keep what's on disk.

**A save that changed memory first.** Adding an AI in the app put it in the session's settings,
then the file write failed (on Windows, likely a virus scan holding config.toml), so the app showed
the AI and its role while nothing was saved, and the error sat in the message bar behind the Settings
window. Save to disk first and change memory only after it worked; replace files with a short retry
on Windows (`write_atomic`); show errors where the person is looking.

**Showing settings shows their secrets.** `settings_show` returned the whole settings, plugins'
`env` values included, which can hold API keys; a tool's output reaches the journal and MCP
clients. The journal only redacts by field name. When a setting can hold a secret, hide its value
in every tool that prints settings, and test that it doesn't appear.

**Secret files kept out only by one person's gitignore.** `.env` files and
`.claude/settings.local.json` were ignored by a contributor's global gitignore, not the repo's, so
anyone else could have committed them. Ignore secret and local files in the repo's `.gitignore`,
and run `cargo xtask secrets` before every commit (the `.githooks/pre-commit` hook does it).

**An empty float sum is `-0.0`.** `iter().map(..).sum::<f64>()` over nothing gives `-0.0`, which
`{:.2}` shows as "$-0.00". Sum money with `fold(0.0, ..)`.

**Docs that drift.** `STATUS.md` described a branch 25 commits old and the tool count was stale.
Update STATUS, the roadmap and generated docs (`cargo xtask tools`, `cargo xtask schemas`) in the
same PR as the change.

**A second lock in one statement.** `CliSpec { deep: !engine.session().clean_room(), logs: engine.session().config_dir(), … }`
looked like two quick reads, but an unbound guard lives to the end of the statement, so the second
waited on the first forever. Every build froze after studying its target while the card calmly
said "This is a big one", and no test ran that line. Read the session once; `cargo xtask locks`
and `platform::sync` now catch this. A wait message must not reassure about what it can't see:
say how long it's been since anything happened. Find a hang with `sample <pid>`: it names the lock.

**An error that points at nothing.** "Check the output below; run Claude Code by hand" came with no
output below (the event carried only message and remediation) and no command, and the program
that failed was really ssh, talking to a git alias from `~/.ssh/config` that had been offered as a
computer. Say what ran and what it printed, write the rest to a log the person can open (a failed
agent run does: `crate::failure_log`), and never name a next step you don't spell out. Exit 255
from ssh is ssh's own failure: don't blame the remote program. Test a message by causing the failure.

**A retry that took "no message" for "brand new".** A run with no message and no `continuing`
flag was read as a first build, and Try again starts exactly that run. A browser that died during
the final check failed a finished build; Try again then studied the original again and gave the
builder the first brief. A run decides what's left from what the project records, not from which
button started it, and a check that couldn't look says nothing about the build.

**A filter written for one kind of text, run on another.** The stand-in's secret scan was written for
API answers, then also ran on recorded scripts: `this.token=t` became `[dropped]` and the scripts
broke, and "Basic Membership" lost a word. It also tested whole tokens, so a secret inside a URL or
after `ref=` passed. Test a scrubber on what must survive as well as what must go, and on each
kind of content it can receive.

**A strict tool that sent an AI off to write its own.** `game_pak_extract` refused an output
whose folder didn't exist and took one file per call; the extractor model hit that twice, then
wrote its own pak reader in Python for a large archive. Tools an AI drives make what they
can (folders), take whole sets in one call, and every brief says to fix the call rather than
replace the tool. Read an AI run's transcript for tools it gave up on.

**Two engines, two address spaces.** Ghidra loads a position-independent ELF (lowest segment at
0) at 0x100000, while the built-in engine reads it where its headers say. Handing Ghidra our
address found nothing there, and Deep mode quietly fell back to the built-in decompiler for every
PIE program and shared library. Whenever an address crosses between engines, move it by their
image bases (`ghidra::Rebase`, from the base the bridge reports) and say in the evidence which
space each address is in.

**An id that only means something on one computer, kept in a folder that travels.** The project
saved Claude Code's session id, but the session itself lives in `~/.claude/projects/` on the
computer (and under the folder) that started it; a project synced to another computer stopped at
"No conversation found" (#452), and the retry for a cut-off turn asked for the same missing session
three more times. Anything a project keeps must still work where the folder goes: keep what the id
points to as well (`agent-session.jsonl`), tell "not here" apart from a failure by a typed signal
(`Conversation::session_lost`), and never retry what can't succeed.

## Agent tooling

**Shell quoting breaks generated edits.** Heredocs carrying Python with quotes, `'''` or `\n` were
mangled by the shell several times. Write multi-line edit scripts to a file and run the file.

**A Python edit that turned every line into CRLF.** `Path.write_text` on Windows writes CRLF
line endings, so a scripted size change rewrote 19 LF files with CRLF (git only warned). Write
with `write_bytes(s.encode())` and check `git ls-files --eol -m` after scripted edits.

**A process search that found itself.** Looking for a helper by a word in its command line, with
that word in the search's own command, listed the search: "a helper is left behind" after every
run, with a new pid each time. The new pid was the clue. Build the pattern from parts
(`'Set' + 'Thread'`), and don't stop processes by pattern on a machine where real builds may run.

**A command that waits for a terminal.** `git stash show -p` opened a pager and an empty
`python - <<'EOF'` heredoc opened the interactive interpreter; both sat waiting for input until
the tool timed out, with work left in a stash. Never run anything that can page or prompt: pass
`--no-pager` (or `GIT_PAGER=cat`), never feed an interpreter an empty script, and check
`git stash list` and `git status` after a timeout before carrying on.
It happened again from a leftover first line (`python -I - <<'X'` with nothing before `X`) in a
command that then wrote and ran a script: 10 minutes lost. Write the script with the editor
tool and run only `python -I <file>`.
And twice more in one night, each time a `python -I - <<'X'` with an empty body typed as a
throwaway step in a longer command. There is no safe use of `python -` here: never type it.

**A search that ran no search.** `timeout 40 find … 2>/dev/null` on a Mac: there's no `timeout` there,
the error went to `/dev/null`, and the empty result read as "no such files on this computer". Don't
hide a command's errors when an empty result means something; set the time limit on the tool call.

**A file list in a variable that zsh didn't split.** `F=$(grep -l …); sed -i '' … $F` handed sed all the
names as one path; it failed, the tests that followed passed on the old code, and it read as done.
Pipe lists into `xargs`, and check the edit landed (`git status`) before reading the test result.

**A scripted edit that stops half-way.** One script deleted a file, then failed an assertion on a
later file, leaving the tree half-edited. Make edit scripts check every anchor before writing
anything, and run `git status` after any failure before trying again.

**A scripted edit that deletes more than it meant to.** A roadmap update found the end of an item
by searching for the next `- [` line; the item was the last in its section, so the search ran into
the next section and deleted its heading. Read `git diff` of every scripted edit before committing,
and bound searches to the section (stop at the next heading).

**A time limit that also covers the build.** A live browser test was run under `timeout`; the
first build of the test binary used most of the time, the limit killed the test mid-run and its
private browser was left running. Build first (`cargo test --no-run`), then run the test under the
limit, and don't kill test processes by hand to clean up after it.

**A UI tree that showed a password.** The Windows UI tree skipped values of password fields, but
.NET's UI Automation client hadn't loaded its Win32 proxies, so every WinForms control was a plain
pane, nothing was flagged as a password, and a password box's text came back as its title. Register
the client-side providers, never read a password field's title or value, treat an unrecognised edit
box as one, and test against a real window with a secret in it.

**A list of tool names that drifted.** The MCP server marked results as untrusted by a list of
tool names; two of its names no longer existed, so nothing failed and the gap went unseen. Put
such facts on the tool itself (`Effects::CARRIES_TARGET_CONTENT`), compare `Registry::canonical`
ids (which cover old ids and `mcp__…__` names) instead of raw names, and keep tool ids that other
code depends on in one constant next to the tool.

**A new tool named the old way.** Two new tools got ids outside the scheme although new tools use
`<area>_<object>_<action>` from the start, and had to be renamed. Read docs/tool-ids.md before
naming a tool.

**A stash that left a new file behind.** Work in progress was stashed to fix something on another
branch; `git stash` keeps only tracked files, so a new file stayed in the tree and `git add -A`
put it into the other PR. Use `git stash -u` (or commit the work in progress on its own branch),
and read `git status` before `git add -A`.
