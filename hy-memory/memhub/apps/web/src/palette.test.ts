import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

const stylesheet = readFileSync(
  new URL("./styles.css", import.meta.url),
  "utf8",
);

function luminance(hex: string) {
  const channels = [0, 2, 4].map((index) => {
    const value = Number.parseInt(hex.slice(index, index + 2), 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}

it("keeps text and semantic labels readable across the light shell surfaces", () => {
  for (const name of ["tx", "tx2", "tx3", "ac", "ok", "wn", "dg"]) {
    const hex = stylesheet.match(
      new RegExp(`--${name}: #([a-fA-F0-9]{6});`),
    )?.[1];
    expect(hex, name).toBeTruthy();
    for (const background of ["ffffff", "e7eaef", "e1e7ee", "f1f4f7"]) {
      const a = luminance(hex as string),
        b = luminance(background);
      expect(
        (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05),
        `${name} on ${background}`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  }
});
