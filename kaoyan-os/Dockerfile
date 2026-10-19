# 构建阶段：安装依赖并编译 monorepo 中的所有包
FROM node:26-alpine AS build

# 启用 corepack 以使用 package.json 中声明的 pnpm 版本
RUN corepack enable

WORKDIR /repo

# 复制整个 monorepo（构建上下文为 kaoyan-os 目录）
COPY . .

# 安装依赖（不强制使用冻结锁文件，便于 monorepo 构建）
RUN pnpm install --no-frozen-lockfile

# 递归构建所有 workspace 包（shared、server、web）
RUN pnpm -r run build

# 运行阶段：仅保留运行时所需内容
FROM node:26-alpine

RUN corepack enable

WORKDIR /app

# 从构建阶段复制完整仓库，保留已安装的 node_modules 与构建产物
COPY --from=build /repo /app

# 生产环境与运行时配置
ENV NODE_ENV=production
ENV PORT=3001
ENV DATABASE_PATH=/app/data/kaoyan.db
ENV WEB_DIST=/app/apps/web/dist

# 创建数据目录并声明为卷，便于持久化 SQLite 数据库
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 3001

# 启动 Fastify 后端服务
WORKDIR /app/apps/server
CMD ["node", "dist/index.js"]
