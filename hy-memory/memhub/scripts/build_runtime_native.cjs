#!/usr/bin/env node
const { buildServiceObserver } = require("./build_service_observer.cjs");

// tsup has just cleared/rebuilt dist. Native assets are added afterwards, never
// compiled on application startup. Linux/Windows keep their existing build.
if (process.platform === "darwin") {
  buildServiceObserver().catch(() => {
    process.stderr.write("runtime_native_build_failed\n");
    process.exitCode = 1;
  });
}
