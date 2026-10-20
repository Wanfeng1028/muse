import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const args = process.argv.slice(2);
if (args.includes("--help") || args.includes("-h")) {
  console.log("Usage: node timeline_json.mjs <projectDir>\nWrites public/timeline.json from src/timeline.ts. Requires Node 24+.");
} else {
  try {
    if (args.length !== 1) throw new Error("Usage: node timeline_json.mjs <projectDir>");
    const project = resolve(args[0]);
    const { SCENES, TOTAL_FRAMES, CUES, FPS = 30 } = await import(pathToFileURL(resolve(project, "src/timeline.ts")).href);
    if (!Number.isInteger(FPS) || FPS <= 0 || !Array.isArray(SCENES) || SCENES.length === 0) {
      throw new Error("Expected positive integer FPS and nonempty SCENES.");
    }
    let total = 0;
    const ids = new Set();
    const scenes = SCENES.map(({ id, name, from, dur }) => {
      if (typeof id !== "string" || !/^[A-Za-z0-9_-]+$/.test(id) || ids.has(id) ||
          typeof name !== "string" || from !== total || !Number.isInteger(dur) || dur <= 0) {
        throw new Error(`Invalid or noncontiguous scene ${id}.`);
      }
      ids.add(id);
      total += dur;
      return { id, name, from, dur };
    });
    if (total !== TOTAL_FRAMES) throw new Error(`TOTAL_FRAMES ${TOTAL_FRAMES} differs from duration sum ${total}.`);
    if (!CUES || typeof CUES !== "object") throw new Error("Expected scene-local CUES.");
    for (const [id, cues] of Object.entries(CUES)) {
      const scene = scenes.find((entry) => entry.id === id);
      if (!scene || !cues || typeof cues !== "object") throw new Error(`Invalid cue scene ${id}.`);
      for (const value of Object.values(cues).flat()) {
        if (!Number.isInteger(value) || value < 0 || value >= scene.dur) throw new Error(`Out-of-range cue in ${id}.`);
      }
    }
    const output = resolve(project, "public/timeline.json");
    await mkdir(resolve(project, "public"), { recursive: true });
    await writeFile(output, `${JSON.stringify({ fps: FPS, total, scenes, cues: CUES }, null, 2)}\n`);
    console.log(`${output}\n${FPS} fps, ${total} frames, ${scenes.length} scenes`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
