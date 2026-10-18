import { describe, it, expect } from "vitest";
import { loadConfig } from "../src/config.js";

describe("config.r3 loadConfig", () => {
  it("全默认值时返回默认端口、默认数据目录、无静态目录与默认房间上限和节流", () => {
    const cfg = loadConfig({}, "/pkg");
    expect(cfg.port).toBe(8765);
    expect(cfg.dataDir).toBe("/pkg/data");
    expect(cfg.publicDir).toBeUndefined();
    expect(cfg.roomMaxMembersWorkroom).toBe(50);
    expect(cfg.roomMaxMembersPlayroom).toBe(200);
    expect(cfg.gameBroadcastThrottleMs).toBe(500);
  });

  it("设置 GATEWAY_PORT 为合法数字时端口取该值", () => {
    const cfg = loadConfig({ GATEWAY_PORT: "9001" }, "/pkg");
    expect(cfg.port).toBe(9001);
  });

  it("GATEWAY_PORT 为非数字时 parseInt 得到 NaN 并回落默认端口 8765", () => {
    const cfg = loadConfig({ GATEWAY_PORT: "abc" }, "/pkg");
    expect(cfg.port).toBe(8765);
  });

  it("DATA_DIR 为绝对路径时 dataDir 原样返回", () => {
    const cfg = loadConfig({ DATA_DIR: "/var/lib/bt" }, "/pkg");
    expect(cfg.dataDir).toBe("/var/lib/bt");
  });

  it("DATA_DIR 为相对路径时相对 pkgDir 解析", () => {
    const cfg = loadConfig({ DATA_DIR: "mydata" }, "/pkg");
    expect(cfg.dataDir).toBe("/pkg/mydata");
  });

  it("未设置 PUBLIC_DIR 时 publicDir 为 undefined", () => {
    const cfg = loadConfig({}, "/pkg");
    expect(cfg.publicDir).toBeUndefined();
  });

  it("PUBLIC_DIR 为相对路径时相对 pkgDir 解析", () => {
    const cfg = loadConfig({ PUBLIC_DIR: "web/dist" }, "/pkg");
    expect(cfg.publicDir).toBe("/pkg/web/dist");
  });

  it("ROOM_MAX_MEMBERS_WORKROOM 为非数字时抛出含键名与原始值的错误", () => {
    expect(() => loadConfig({ ROOM_MAX_MEMBERS_WORKROOM: "abc" }, "/pkg")).toThrow(
      "[config] invalid ROOM_MAX_MEMBERS_WORKROOM=abc",
    );
  });

  it("ROOM_MAX_MEMBERS_WORKROOM 低于下限抛范围错误，空串则回落默认 50", () => {
    expect(() => loadConfig({ ROOM_MAX_MEMBERS_WORKROOM: "0" }, "/pkg")).toThrow(
      "expected integer in [1, 10000]",
    );
    const cfg = loadConfig({ ROOM_MAX_MEMBERS_WORKROOM: "" }, "/pkg");
    expect(cfg.roomMaxMembersWorkroom).toBe(50);
  });

  it("GAME_BROADCAST_THROTTLE_MS 允许 0，超过上限 60000 抛错", () => {
    const cfg = loadConfig({ GAME_BROADCAST_THROTTLE_MS: "0" }, "/pkg");
    expect(cfg.gameBroadcastThrottleMs).toBe(0);
    expect(() => loadConfig({ GAME_BROADCAST_THROTTLE_MS: "60001" }, "/pkg")).toThrow(
      "expected integer in [0, 60000]",
    );
  });
});