// 服务入口文件：创建并启动 Fastify 应用
import { buildApp } from './app';

// 读取端口，默认 3001
const port = Number(process.env.PORT ?? 3001);

// 构建应用实例，开启日志
const app = buildApp({ logger: true });

// 监听 0.0.0.0 以便容器/外部访问
app
  .listen({ port, host: '0.0.0.0' })
  .then(() => {
    // 启动成功，打印访问地址
    console.log(`Server listening on http://0.0.0.0:${port}`);
  })
  .catch((err) => {
    // 启动失败，打印错误并退出进程
    console.error(err);
    process.exit(1);
  });
