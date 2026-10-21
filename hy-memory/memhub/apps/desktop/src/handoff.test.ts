import { describe, expect, it } from "vitest";

import { canHandOff, HANDOFF_WITHOUT_PROMPT, handoffUrl } from "./handoff";

const HOME = "/Users/someone";

describe("handoffUrl", () => {
  it("never launches Claude desktop under the Claude Code identity", () => {
    expect(handoffUrl("claude-code", "context", HOME)).toBeNull();
  });

  it("refuses an oversized URL instead of silently losing context", () => {
    expect(handoffUrl("cursor", "界".repeat(5000), HOME)).toBeNull();
  });
  it("把提示词编码进各家自己的 scheme", () => {
    const prompt = "记得我们聊过的 axios 那件事吗？&继续";

    expect(handoffUrl("cursor", prompt, HOME)).toBe(
      `cursor://anysphere.cursor-deeplink/prompt?text=${encodeURIComponent(prompt)}&mode=ask`,
    );
    expect(handoffUrl("claude-code", prompt, HOME)).toBeNull();
  });

  it("不为尚未核验输入框的宿主提供推测链接", () => {
    expect(handoffUrl("codex", "问题", HOME)).toBeNull();
    expect(handoffUrl("opencode", "问题", HOME)).toBeNull();
  });

  it("& 和 ? 不会把链接截断成两半", () => {
    const url = handoffUrl("cursor", "a&b=c?d", HOME);

    expect(url).not.toContain("a&b=c?d");
    expect(new URL(url ?? "").searchParams.get("text")).toBe("a&b=c?d");
  });

  it("不认识的 app 一律不给链接", () => {
    // 这条是白名单的守卫：主进程只按这张表拼 URL，表外的东西
    // 走不到 shell.openExternal。
    expect(handoffUrl("evil", "x", HOME)).toBeNull();
    expect(handoffUrl("file", "x", HOME)).toBeNull();
    expect(canHandOff("evil")).toBe(false);
  });

  it("认识的 app 才给", () => {
    // 上一条的正面对照：同样一个函数，表内的能拿到链接，
    // 否则「一律返回 null」也能让上一条通过。
    expect(canHandOff("cursor")).toBe(true);
    expect(handoffUrl("cursor", "x", HOME)).not.toBeNull();
  });

  it("空提示词不开窗", () => {
    expect(handoffUrl("cursor", "   ", HOME)).toBeNull();
  });

  it("接得上但填不进去的 app 单独列出来，不假装能填", () => {
    expect(HANDOFF_WITHOUT_PROMPT.has("workbuddy")).toBe(true);
    expect(canHandOff("workbuddy")).toBe(false);
  });
});
