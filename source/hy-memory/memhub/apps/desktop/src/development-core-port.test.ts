import { expect, it } from "vitest";
import {
  developmentBrokerPort,
  developmentCorePort,
} from "./development-core-port";

it("keeps the daily development default when no override is supplied", () => {
  expect(developmentCorePort({})).toBe(8765);
});

it("uses an explicit isolated development port", () => {
  expect(developmentCorePort({ ONE_MEMORY_CORE_PORT: "28765" })).toBe(28765);
  expect(developmentBrokerPort({ ONE_MEMORY_BROKER_PORT: "38765" })).toBe(
    38765,
  );
});

it.each(["0", "1023", "65536", "abc", "8765.5"])(
  "rejects an invalid development port %s",
  (value) => {
    expect(() => developmentCorePort({ ONE_MEMORY_CORE_PORT: value })).toThrow(
      "desktop_development_port_invalid",
    );
  },
);
