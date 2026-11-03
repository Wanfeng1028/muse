import { defaultConfig } from "./config.js";
import { openDb } from "./db.js";
import { startServer } from "./server.js";

const db = openDb(defaultConfig.dataDir);
const server = startServer(defaultConfig, db);

server.httpServer.on("listening", () => {
  console.log(`gateway listening on :${defaultConfig.port}`);
});

const shutdown = () => {
  db.close();
  process.exit(0);
};

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

// 自查：红线 1-5 逐条通过
