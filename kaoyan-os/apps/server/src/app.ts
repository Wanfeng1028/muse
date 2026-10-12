import Fastify, { FastifyInstance } from 'fastify';
import cors from '@fastify/cors';
import fastifyStatic from '@fastify/static';
import path from 'node:path';
import fs from 'node:fs';
import { createDb } from './db';
import { seedIfEmpty } from './seed';
import { registerPlansRoutes } from './routes/plans';
import { registerFocusRoutes } from './routes/focus';
import { registerMistakesRoutes } from './routes/mistakes';
import { registerWordsRoutes } from './routes/words';
import { registerExamsRoutes } from './routes/exams';
import { registerSettingsRoutes } from './routes/settings';

// 构建 Fastify 应用实例
export function buildApp(opts?: { dbPath?: string; logger?: boolean }): FastifyInstance {
  // 数据库路径：显式传入 > 环境变量 > 默认 data/kaoyan.db
  const dbPath =
    opts?.dbPath ||
    process.env.DATABASE_PATH ||
    path.join(process.cwd(), 'data', 'kaoyan.db');

  const db = createDb(dbPath);
  // 首次启动时填充示例数据
  seedIfEmpty(db);

  const app = Fastify({ logger: opts?.logger ?? false });

  // 允许跨域
  app.register(cors, { origin: true });

  // 健康检查
  app.get('/api/health', async () => {
    return { status: 'ok', time: new Date().toISOString() };
  });

  // 注册各业务路由
  registerPlansRoutes(app, db);
  registerFocusRoutes(app, db);
  registerMistakesRoutes(app, db);
  registerWordsRoutes(app, db);
  registerExamsRoutes(app, db);
  registerSettingsRoutes(app, db);

  // 若配置了前端构建产物目录且存在，则挂载静态资源并做 SPA 兜底
  const webDist = process.env.WEB_DIST;
  if (webDist && fs.existsSync(webDist)) {
    const root = path.resolve(webDist);
    app.register(fastifyStatic, { root, prefix: '/' });

    app.setNotFoundHandler((request, reply) => {
      // API 路径返回 404 JSON，其余走 index.html 兜底
      if (request.url.startsWith('/api')) {
        reply.code(404).send({ error: 'not found' });
        return;
      }
      reply.sendFile('index.html');
    });
  }

  return app;
}
