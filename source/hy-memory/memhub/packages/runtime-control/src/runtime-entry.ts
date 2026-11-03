#!/usr/bin/env node

import { runRuntimeCli } from "./runtime-cli.js";

runRuntimeCli(process.argv.slice(2)).then(
  (code) => {
    process.exitCode = code;
  },
  (error) => {
    process.stderr.write(
      `${error instanceof Error ? error.message : "MemHub Runtime failed"}\n`,
    );
    process.exitCode = 1;
  },
);
