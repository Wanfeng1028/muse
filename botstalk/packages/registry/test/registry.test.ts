import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { registry, Registry, DEFAULT_SUPPORT } from "../src/index.js";

const DESCRIPTORS_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "descriptors");

describe("registry 行为对照（OpenAgents 原版规格）", () => {
  it("加载 22 个描述符且全部合法", () => {
    const catalog = registry.getCatalog();
    expect(catalog).toHaveLength(22);
    for (const d of catalog) {
      expect(registry.validateDescriptor(d), d.name).toEqual([]);
    }
  });

  it("排序：featured 按 order 在前，其余按 label 字母序", () => {
    const names = registry.getCatalog().map((d) => d.name);
    expect(names.slice(0, 7)).toEqual(["claude", "openclaw", "codex", "cursor", "opencode", "hermes", "kimi"]);
    expect(names[7]).toBe("aider");
    // 非 featured 段按 (label || name) 字母序（照抄原版 Python 语义；注意 copilot 的 label 是 "GitHub Copilot CLI"，排在 gemini 之后）
    expect(names.slice(7)).toEqual([
      "aider", "amp", "antigravity", "cline", "codearts", "codebuddy",
      "commandcode", "deepseek", "gemini", "copilot", "goose",
      "mini-swe-agent", "nanoclaw", "openworker", "pi",
    ]);
  });

  it("support 空对象的描述符内存补齐 DEFAULT_SUPPORT，且不改写 JSON 原文", () => {
    expect(registry.getByName("cursor")!.support).toEqual(DEFAULT_SUPPORT);
    expect(registry.getByName("opencode")!.support).toEqual(DEFAULT_SUPPORT);
    expect(DEFAULT_SUPPORT).toEqual({ install: true, workspace: false, collaboration: false });
    const raw = JSON.parse(readFileSync(join(DESCRIPTORS_DIR, "cursor.json"), "utf8"));
    expect(raw.support).toEqual({});
  });

  it("查询 API", () => {
    expect(registry.getByName("claude")!.install.binary).toBe("claude");
    expect(registry.findByBinary("codex")!.name).toBe("codex");
    expect(registry.getByName("不存在")).toBeUndefined();
    expect(registry.findByBinary("不存在")).toBeUndefined();
    expect(registry.count()).toBe(22);
    expect(registry.featured().map((d) => d.name)).toEqual(["claude", "openclaw", "codex", "cursor", "opencode", "hermes", "kimi"]);
    expect(registry.byTag("cli").length).toBeGreaterThan(0);
  });

  it("validateDescriptor 拒绝非法输入", () => {
    const good = registry.getByName("claude")!;
    expect(registry.validateDescriptor({ ...good, name: "" })[0]).toMatch(/name/);
    expect(registry.validateDescriptor({ ...good, tags: [] })[0]).toMatch(/tags/);
    expect(registry.validateDescriptor({ ...good, launch: { args: "x" } })[0]).toMatch(/launch/);
    expect(registry.validateDescriptor({ ...good, adapter: { module: "", class: "X" } })[0]).toMatch(/adapter/);
    // 上游真实形态：launch/adapter 为 null 不报错
    expect(registry.validateDescriptor({ ...good, launch: null, adapter: null })).toEqual([]);
    // 未知扩展字段不报错
    expect(registry.validateDescriptor({ ...good, models: { provider: "x" }, catalog: {} })).toEqual([]);
  });

  it("claude/codex 描述符关键字段符合原版", () => {
    const claude = registry.getByName("claude")!;
    expect(claude.launch!.args).toEqual(["--append-system-prompt", "Your agent name is '{agent_name}'."]);
    expect(claude.check_ready!.env_vars).toContain("ANTHROPIC_API_KEY");
    const codex = registry.getByName("codex")!;
    expect(codex.launch!.args).toEqual([null]);
    expect(codex.check_ready!.login_command).toBe("codex login");
  });
});