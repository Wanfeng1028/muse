// Explicit opt-in live-model acceptance. Run against an isolated Studio project.
import { writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
const require = createRequire(new URL("../packages/core/package.json", import.meta.url));
const { Agent, setGlobalDispatcher } = require("undici");
const dispatcher = new Agent({ headersTimeout: 1_800_000, bodyTimeout: 1_800_000 });
setGlobalDispatcher(dispatcher);
const [base, evidencePath] = process.argv.slice(2);
if (!base || !evidencePath) throw new Error("Usage: node scripts/verify-live-studio.mjs <studio-url> <evidence.json>");
const evidence = [];
async function request(path, body) {
  const startedAt = new Date().toISOString();
  const response = await fetch(`${base}/api/v1${path}`, {
    method: body ? "POST" : "GET",
    headers: { "content-type": "application/json" },
    ...(body ? { body: JSON.stringify(body) } : {}),
    signal: AbortSignal.timeout(1_800_000),
  });
  const result = await response.json();
  evidence.push({ path, startedAt, completedAt: new Date().toISOString(), status: response.status, result });
  await writeFile(evidencePath, JSON.stringify(evidence, null, 2));
  if (!response.ok) throw new Error(`${path}: ${response.status} ${JSON.stringify(result)}`);
  return result;
}
async function create(kind, intent, instruction, actionPayload) {
  const { session } = await request("/sessions", { sessionKind: kind });
  await request("/agent", { sessionId: session.sessionId, sessionKind: kind, instruction, actionSource: "button", requestedIntent: intent, actionPayload });
  const result = await request(`/sessions/${session.sessionId}`);
  if (result.task?.execution.status !== "completed") throw new Error(`Incomplete task: ${JSON.stringify(result.task)}`);
  return result.session;
}
const cases = [
  ["script", () => create("script", "script_create", "生成两场中文现实悬疑短剧：失物招领员发现一把被两人认领的钥匙，通过不同人描述的磨痕识破谎言。总长约1000字，含动作、对白、场景标题和完整结尾。", { scriptCreate: { title: "钥匙的第二个主人", projectId: "acceptance-script", episodeCount: 1, targetFormat: "两场完整短剧" } })],
  ["storyboard", () => create("storyboard", "storyboard_create", "把作品 acceptance-script 的剧本改编成6个连续分镜，每镜包含景别、动作、对白与图像提示词。", { storyboardCreate: { title: "钥匙分镜", projectId: "acceptance-storyboard", sourcePath: "works/acceptance-script/source/script.md", maxShots: 6, aspectRatio: "9:16" } })],
  ["film", () => create("interactive-film", "interactive_film_create", "创建一个可完整玩到结局的中文互动悬疑短片。失物招领员需选择相信两个钥匙认领者中的谁；用可见证据做判断。约5个节点、至少2个不同结局，条件与变量定义一致，完整对白和场景，生成可播放包。", { interactiveFilmCreate: { title: "失物之门", projectId: "acceptance-film", episodeCount: 1 } })],
  ["play", async () => {
    const session = await create("play", "play_start", "创建一个可自由行动的现实失物招领室世界。玩家手持一把铜钥匙，面前有空抽屉和访客。保持物品状态连续。关闭自动配图。", { playStart: { title: "失物招领室", mode: "open", premise: "玩家是夜班失物招领员", worldContract: "玩家开场手持一把铜钥匙。抽屉为空。动作后更新物品所在位置，角色只知道亲眼见过的事。", language: "zh" } });
    for (const instruction of ["我把手里的铜钥匙放进抽屉，然后关上抽屉。", "我打开抽屉，拿回铜钥匙。"])
      await request("/agent", { sessionId: session.sessionId, sessionKind: "play", instruction, actionSource: "button", requestedIntent: "play_step", playMode: "open" });
    return request(`/sessions/${session.sessionId}`);
  }],
];
for (const [name, run] of cases) {
  try { await run(); console.log(`${name}: completed`); }
  catch (error) { evidence.push({ case: name, error: error.message }); await writeFile(evidencePath, JSON.stringify(evidence, null, 2)); console.error(`${name}: ${error.message}`); process.exitCode = 1; }
}
await dispatcher.close();
