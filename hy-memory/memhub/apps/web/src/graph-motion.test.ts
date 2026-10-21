import { expect, it } from "vitest";
import { graphEase } from "./graph-motion";

it("S1 graph interpolation has bounded monotonic motion and exact endpoints", () => {
  expect(graphEase(-1)).toBe(0);
  expect(graphEase(1)).toBe(1);
  expect(graphEase(10)).toBe(1);
  let previous = 0;
  for (let i = 0; i <= 180; i++) {
    const value = graphEase(i / 180);
    expect(value).toBeGreaterThanOrEqual(previous);
    expect(value).toBeLessThanOrEqual(1);
    previous = value;
  }
});
