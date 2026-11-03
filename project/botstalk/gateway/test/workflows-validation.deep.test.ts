import { describe, expect, it } from "vitest";
import { validateScheduledTaskInput, validateTriggerRuleInput } from "../src/workflows.js";

describe("validateScheduledTaskInput", () => {
  it("1. name 为空字符串 -> 返回\"名称不能为空\"", () => {
    expect(validateScheduledTaskInput({ name: "", interval_sec: 60, prompt: "内容" })).toBe("名称不能为空");
  });

  it("2. name 为全空格 -> 返回\"名称不能为空\"", () => {
    expect(validateScheduledTaskInput({ name: "   ", interval_sec: 60, prompt: "内容" })).toBe("名称不能为空");
  });

  it("3. name 为数字 123 -> 返回\"名称不能为空\"", () => {
    expect(validateScheduledTaskInput({ name: 123, interval_sec: 60, prompt: "内容" })).toBe("名称不能为空");
  });

  it("4. name 缺失 -> 返回\"名称不能为空\"", () => {
    expect(validateScheduledTaskInput({ interval_sec: 60, prompt: "内容" })).toBe("名称不能为空");
  });

  it("5. interval_sec=59 -> 返回\"间隔秒数须为 60~2592000 的整数\"", () => {
    expect(validateScheduledTaskInput({ name: "任务", interval_sec: 59, prompt: "内容" })).toBe("间隔秒数须为 60~2592000 的整数");
  });

  it("6. interval_sec=60 -> 返回 null（合法下限）", () => {
    expect(validateScheduledTaskInput({ name: "任务", interval_sec: 60, prompt: "内容" })).toBeNull();
  });

  it("7. interval_sec=2592000 -> 返回 null（合法上限）", () => {
    expect(validateScheduledTaskInput({ name: "任务", interval_sec: 2592000, prompt: "内容" })).toBeNull();
  });

  it("8. interval_sec=2592001 -> 返回错误", () => {
    expect(validateScheduledTaskInput({ name: "任务", interval_sec: 2592001, prompt: "内容" })).toBe("间隔秒数须为 60~2592000 的整数");
  });

  it("9. interval_sec=60.5 -> 返回错误（非整数）", () => {
    expect(validateScheduledTaskInput({ name: "任务", interval_sec: 60.5, prompt: "内容" })).toBe("间隔秒数须为 60~2592000 的整数");
  });

  it("10. interval_sec=\"3600\"（字符串数字） -> 返回 null", () => {
    expect(validateScheduledTaskInput({ name: "任务", interval_sec: "3600", prompt: "内容" })).toBeNull();
  });

  it("11. interval_sec=\"abc\" -> 返回错误", () => {
    expect(validateScheduledTaskInput({ name: "任务", interval_sec: "abc", prompt: "内容" })).toBe("间隔秒数须为 60~2592000 的整数");
  });

  it("12. interval_sec=-1 -> 返回错误", () => {
    expect(validateScheduledTaskInput({ name: "任务", interval_sec: -1, prompt: "内容" })).toBe("间隔秒数须为 60~2592000 的整数");
  });

  it("13. prompt 为空字符串 -> 返回\"任务内容不能为空\"", () => {
    expect(validateScheduledTaskInput({ name: "任务", interval_sec: 60, prompt: "" })).toBe("任务内容不能为空");
  });

  it("14. prompt 为全空格 -> 返回\"任务内容不能为空\"", () => {
    expect(validateScheduledTaskInput({ name: "任务", interval_sec: 60, prompt: "   " })).toBe("任务内容不能为空");
  });

  it("15. name/interval_sec/prompt 全部合法 -> 返回 null", () => {
    expect(validateScheduledTaskInput({ name: "任务", interval_sec: 3600, prompt: "内容" })).toBeNull();
  });

  it("16. prompt 超长（5000 字符） -> 返回 null（无长度限制）", () => {
    expect(validateScheduledTaskInput({ name: "任务", interval_sec: 3600, prompt: "x".repeat(5000) })).toBeNull();
  });
});

describe("validateTriggerRuleInput", () => {
  it("17. match_type=\"KEYWORD\"（大写） -> 返回\"匹配类型须为 keyword/sender/event\"", () => {
    expect(validateTriggerRuleInput({ name: "规则", match_type: "KEYWORD", pattern: "abc", prompt: "回复" })).toBe("匹配类型须为 keyword/sender/event");
  });

  it("18. match_type=\"sms\" -> 返回错误", () => {
    expect(validateTriggerRuleInput({ name: "规则", match_type: "sms", pattern: "abc", prompt: "回复" })).toBe("匹配类型须为 keyword/sender/event");
  });

  it("19. keyword 类型 pattern=\"  ,  \"（逗号+空格） -> 返回\"关键词不能为空\"", () => {
    expect(validateTriggerRuleInput({ name: "规则", match_type: "keyword", pattern: "  ,  ", prompt: "回复" })).toBe("关键词不能为空");
  });

  it("20. keyword 类型 pattern=\"早报,日报\" -> 返回 null", () => {
    expect(validateTriggerRuleInput({ name: "规则", match_type: "keyword", pattern: "早报,日报", prompt: "回复" })).toBeNull();
  });

  it("21. cooldown_sec=-1 -> 返回\"冷却秒数须为非负整数\"", () => {
    expect(validateTriggerRuleInput({ name: "规则", match_type: "sender", pattern: "user-1", prompt: "回复", cooldown_sec: -1 })).toBe("冷却秒数须为非负整数");
  });

  it("22. cooldown_sec=1.5 -> 返回错误", () => {
    expect(validateTriggerRuleInput({ name: "规则", match_type: "sender", pattern: "user-1", prompt: "回复", cooldown_sec: 1.5 })).toBe("冷却秒数须为非负整数");
  });

  it("23. cooldown_sec=\"300\"（字符串） -> 返回 null", () => {
    expect(validateTriggerRuleInput({ name: "规则", match_type: "sender", pattern: "user-1", prompt: "回复", cooldown_sec: "300" })).toBeNull();
  });

  it("24. cooldown_sec=0 -> 返回 null", () => {
    expect(validateTriggerRuleInput({ name: "规则", match_type: "sender", pattern: "user-1", prompt: "回复", cooldown_sec: 0 })).toBeNull();
  });

  it("25. cooldown_sec 缺失 -> 返回 null", () => {
    expect(validateTriggerRuleInput({ name: "规则", match_type: "sender", pattern: "user-1", prompt: "回复" })).toBeNull();
  });

  it("26. sender 类型 pattern 非空 -> 返回 null", () => {
    expect(validateTriggerRuleInput({ name: "规则", match_type: "sender", pattern: "user-1", prompt: "回复" })).toBeNull();
  });
});