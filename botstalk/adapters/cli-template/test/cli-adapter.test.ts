import { describe, it, expect } from "vitest";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { CliAdapter, expandHome } from "../src/index.js";
import { registry } from "@botstalk/registry";

// fake-cli.sh 的绝对路径，用于在测试中替换真实二进制
const fakeBin = join(dirname(fileURLToPath(import.meta.url)), "fixtures", "fake-cli.sh");

// 最小化子类，用于实例化 abstract CliAdapter 并调用其 public/protected 方法
class TestAdapter extends CliAdapter {}

// 以 claude 描述符为底构造 fake 描述符：替换 binary、清空默认 launch.args 与 check_ready/probe，再允许覆盖
function fakeDescriptor(over: any = {}): any {
  const base: any = registry.getByName("claude");
  return {
    ...base,
    install: {
      ...base.install,
      binary: fakeBin,
    },
    launch: {
      ...(base.launch ?? {}),
      args: [],
    },
    check_ready: null,
    probe: null,
    ...over,
  };
}

// 统一创建 adapter 实例的辅助函数
function createAdapter(descriptor: any, opts: any = {}): any {
  return new TestAdapter({
    adapterId: "test-adapter",
    descriptor,
    agentName: "tester",
    workingDir: process.cwd(),
    taskTimeoutMs: 5000,
    killGraceMs: 2000,
    extraEnv: {},
    intents: [],
    ...opts,
  });
}

describe("CliAdapter", () => {
  describe("A. buildCommand 行为对照", () => {
    it("claude 描述符 + agentName bob 时 buildCommand 追加系统提示", () => {
      const a = createAdapter(registry.getByName("claude"), { agentName: "bob" });
      expect(a.buildCommand()).toEqual({
        binary: "claude",
        args: ["--append-system-prompt", "Your agent name is 'bob'."],
      });
    }, 15000);

    it("codex 描述符 launch.args 中的 null 被丢弃，返回空 args", () => {
      const a = createAdapter(registry.getByName("codex"));
      expect(a.buildCommand()).toEqual({ binary: "codex", args: [] });
    }, 15000);

    it("openclaw 描述符 launch 为 null 时 buildCommand 抛出错误", () => {
      const a = createAdapter(registry.getByName("openclaw"));
      expect(() => a.buildCommand()).toThrow(/openclaw/);
    }, 15000);

    it("expandHome 将 ~ 展开为 HOME 前缀，绝对路径原样返回", () => {
      const home = process.env.HOME ?? "";
      expect(expandHome("~/x").startsWith(home)).toBe(true);
      expect(expandHome("/abs")).toBe("/abs");
    }, 15000);
  });

  describe("B. E2E", () => {
    it("runTask 默认 stdin 回显，exitCode 0 且 stdout 包含 prompt", async () => {
      const a = createAdapter(fakeDescriptor());
      const res = await a.runTask("hello-task", { timeoutMs: 10000 });
      expect(res.exitCode).toBe(0);
      expect(res.stdout).toContain("hello-task");
      expect(res.timedOut).toBe(false);
      expect(res.truncated).toBe(false);
    }, 15000);

    it("probe 使用 descriptor.probe.args 执行成功返回 true", async () => {
      const a = createAdapter(fakeDescriptor({
        probe: { args: ["--print", "hi"], timeout_s: 5 },
      }));
      expect(await a.probe()).toBe(true);
    }, 15000);

    it("checkReady 匹配 logged_in_pattern 时返回 ready true", async () => {
      const a = createAdapter(fakeDescriptor({
        check_ready: {
          status_args: ["auth", "status"],
          logged_in_pattern: "\"loggedIn\"\\s*:\\s*true",
          logged_out_pattern: "\"loggedIn\"\\s*:\\s*false",
        },
      }));
      expect(await a.checkReady()).toEqual({ ready: true });
    }, 15000);

    it("checkReady 缺少必需环境变量时返回 ready false 且 message 含变量名", async () => {
      const a = createAdapter(fakeDescriptor({
        check_ready: { env_vars: ["BOTSTALK_TEST_MISSING_ENV_XYZ"] },
      }));
      const res = await a.checkReady();
      expect(res.ready).toBe(false);
      expect(res.message).toContain("BOTSTALK_TEST_MISSING_ENV_XYZ");
    }, 15000);
  });

  describe("C. 失败注入", () => {
    it("binary 不存在时 runTask rejects 且 probe 返回 false", async () => {
      const a = createAdapter(fakeDescriptor({
        install: { binary: "/nonexistent-dir-xyz/fake-cli" },
        // 配上 probe 才能走到 spawn 失败路径（无 probe 配置时 probe() 按约定直接返回 true）
        probe: { args: ["--print", "hi"], timeout_s: 5 },
      }));
      await expect(a.runTask("x")).rejects.toThrow(/fake-cli/);
      expect(await a.probe()).toBe(false);
    }, 15000);

    it("runTask 超时后 timedOut true，且新任务可正常执行无僵尸占用", async () => {
      const a = createAdapter(fakeDescriptor({ launch: { args: ["--slow"] } }));
      const r1 = await a.runTask("slow", { timeoutMs: 300 });
      expect(r1.timedOut).toBe(true);

      const a2 = createAdapter(fakeDescriptor());
      const r2 = await a2.runTask("normal", { timeoutMs: 10000 });
      expect(r2.exitCode).toBe(0);
    }, 15000);

    it("SIGINT 被忽略时经 killGraceMs 升级 SIGKILL，15s 内结束", async () => {
      const a = createAdapter(fakeDescriptor({ launch: { args: ["--ignore-sigint"] } }), {
        taskTimeoutMs: 400,
        killGraceMs: 300,
      });
      const start = Date.now();
      const res = await a.runTask("x");
      expect(res.timedOut).toBe(true);
      expect(Date.now() - start).toBeLessThan(15000);
    }, 15000);

    it("任务运行中再次 runTask 被拒绝，stopCurrent 后清理", async () => {
      const a = createAdapter(fakeDescriptor({ launch: { args: ["--slow"] } }));
      const p1 = a.runTask("first", { timeoutMs: 10000 });
      await expect(a.runTask("second")).rejects.toThrow(/task already running/);
      await a.stopCurrent();
      await p1;
    }, 15000);

    it("输出超过 1MB 时 truncated true 且 stdout 长度受限", async () => {
      const a = createAdapter(fakeDescriptor({ launch: { args: ["--big"] } }));
      const r = await a.runTask("x", { timeoutMs: 15000 });
      expect(r.truncated).toBe(true);
      expect(r.stdout.length).toBeLessThanOrEqual(1048576 + 1024);
    }, 20000);

    it("非零退出码时 handleTaskMessage 抛错", async () => {
      const a = createAdapter(fakeDescriptor({ launch: { args: ["--boom"] } }));
      const r = await a.runTask("x", { timeoutMs: 10000 });
      expect(r.exitCode).toBe(3);
      // handleTaskMessage 为 protected，用 any 调用
      await expect((a as any).handleTaskMessage("x")).rejects.toThrow(/kaboom/);
    }, 15000);
  });
});
