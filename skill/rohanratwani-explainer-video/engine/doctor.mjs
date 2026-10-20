// Checks everything the pipeline needs and prints the fix for anything missing.
//   node engine/doctor.mjs
// Video only needs Node, ffmpeg and HyperFrames. Voice adds Python packages.
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

let bad = 0;
const ok = (m) => console.log(`  ok    ${m}`);
const no = (m, fix, required = true) => { if (required) bad++; console.log(`  ${required ? "MISS" : "skip"}  ${m}\n        fix: ${fix}`); };
// shell only for npx (a .cmd on Windows); a shell would split "import x" into two arguments
const run = (cmd, args) => spawnSync(cmd, args, { encoding: "utf8", shell: cmd === "npx" && process.platform === "win32" });

console.log("video");
const major = Number(process.versions.node.split(".")[0]);
major >= 20 ? ok(`node ${process.versions.node}`) : no(`node ${process.versions.node} (need 20+)`, "install Node 20 or newer from nodejs.org");
for (const t of ["ffmpeg", "ffprobe"]) {
  const r = run(t, ["-version"]);
  r.status === 0 ? ok(r.stdout.split("\n")[0].slice(0, 60)) : no(t, "install ffmpeg (winget install ffmpeg / brew install ffmpeg / apt install ffmpeg)");
}
const hf = run("npx", ["--yes", "hyperframes", "--version"]);
hf.status === 0 ? ok(`hyperframes ${hf.stdout.trim().split("\n").pop()}`) : no("hyperframes CLI", "npx --yes hyperframes --version (needs internet the first time)");

console.log("voice (optional: skip it and the video is timed at reading pace)");
const py = process.env.ONBEAT_PY || [process.platform === "win32" ? "python" : "python3", "python"].find((p) => run(p, ["--version"]).status === 0);
if (!py) no("python", "install Python 3.10+", false);
else {
  ok(`${py} ${run(py, ["--version"]).stdout.trim() || ""}`);
  const mods = { kokoro_onnx: "AI voice (Kokoro)", soundfile: "audio files", numpy: "mixing", faster_whisper: "word timings + your own voice" };
  for (const [m, why] of Object.entries(mods)) {
    run(py, ["-c", `import ${m}`]).status === 0 ? ok(`${m} (${why})`) : no(`${m} (${why})`, `${py} -m pip install -r requirements.txt`, false);
  }
  const cache = path.join(os.homedir(), ".cache", "hyperframes", "tts");
  fs.existsSync(path.join(cache, "models", "kokoro-v1.0.onnx")) && fs.existsSync(path.join(cache, "voices", "voices-v1.0.bin"))
    ? ok("Kokoro model downloaded")
    : no("Kokoro model", `npx --yes hyperframes tts "hello" -o hello.wav   (downloads it to ${cache})`, false);
}
console.log(bad ? `\n${bad} required item(s) missing.` : "\nready to make videos.");
process.exit(bad ? 1 : 0);
