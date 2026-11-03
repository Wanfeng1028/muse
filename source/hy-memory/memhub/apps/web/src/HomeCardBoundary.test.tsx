// @vitest-environment jsdom

import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { HomeCardBoundary } from "./HomeCardBoundary";

function Boom(): never {
  throw new Error("boom");
}

it("单卡渲染出错只塌这一张卡，兄弟区域不受影响", () => {
  const spy = vi.spyOn(console, "error").mockImplementation(() => {});
  render(
    <div>
      <HomeCardBoundary label="记忆概览">
        <Boom />
      </HomeCardBoundary>
      <p>正常区域</p>
    </div>,
  );
  expect(screen.getByText(/记忆概览暂时显示不了/)).toBeTruthy();
  expect(screen.getByText("正常区域")).toBeTruthy();
  spy.mockRestore();
});

it("正常卡片原样渲染", () => {
  render(
    <HomeCardBoundary label="运行状态">
      <p>后台运行中</p>
    </HomeCardBoundary>,
  );
  expect(screen.getByText("后台运行中")).toBeTruthy();
});
