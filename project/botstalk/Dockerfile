# 说明：本机无 docker daemon，未实跑验证；以下为可直接落盘的 Dockerfile 定义。
# 镜像目标：构建 Web 前端 + 网关，网关直出静态文件（PUBLIC_DIR=/app/public），单镜像运行整个聊天室。

# ---------- 构建阶段 ----------
FROM node:22-slim AS build
WORKDIR /app

# 先拷 package.json 体系以利用层缓存
COPY package.json package-lock.json ./
COPY packages/protocol/package.json ./packages/protocol/
COPY gateway/package.json ./gateway/
COPY adapters/base/package.json ./adapters/base/
COPY web/package.json ./web/
RUN npm ci --no-audit --no-fund

# 再拷源码并构建
COPY packages/protocol ./packages/protocol
COPY gateway ./gateway
COPY adapters/base ./adapters/base
COPY web ./web
RUN npm run build --workspace=@botstalk/protocol --workspace=botstalk-gateway --workspace=@botstalk/adapter-base --workspace=@botstalk/web

# ---------- 运行阶段 ----------
FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production
ENV GATEWAY_PORT=8765
ENV DATA_DIR=/data
ENV PUBLIC_DIR=/app/public

COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/packages/protocol ./packages/protocol
COPY --from=build /app/gateway/dist ./gateway/dist
COPY --from=build /app/gateway/package.json ./gateway/package.json
COPY --from=build /app/web/dist ./public

VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD node -e "fetch('http://127.0.0.1:8765/healthz').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"
CMD ["node", "gateway/dist/index.js"]
