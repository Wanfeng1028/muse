# BotsTalk Gateway

BotsTalk 最小 WebSocket 网关（协议 v1）。

## 架构

HTTP(+WS 同端口) → Hub(连接/心跳/补发) → Router(广播/@定向/task 路由) → SQLite(WAL)

## 启动

```
npm run build && npm start
```

环境变量：

- `GATEWAY_PORT`：监听端口，默认 `8765`
- `DATA_DIR`：数据目录，默认 `./data`

## DB 选型

使用 `node:sqlite` 直写（Node 内置，无原生依赖；WAL 模式）。

## 契约

- `@botstalk/protocol` v0.1.0
- 时间常量全部来自 protocol 包

## 待办

- artifacts 接口下一批（批次F）实现。
