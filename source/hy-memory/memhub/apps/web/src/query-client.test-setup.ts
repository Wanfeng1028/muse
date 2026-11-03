import { afterEach } from "vitest";
import { resetClient } from "./query-client";

afterEach(() => {
  resetClient();
});
