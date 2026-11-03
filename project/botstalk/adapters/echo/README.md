测试用 Echo adapter：收到 message 原样回显 `echo: <text>`，收到 task 先回执再流式返回 `echo result: <text>`。

## 环境变量

- `ADAPTER_ID`：adapter 标识，默认 `echo`。
- `GATEWAY_URL`：网关地址，默认 `ws://127.0.0.1:8765`。
- `ROOM`：房间名，默认 `lobby`。

## 运行

```
npm run build
node dist/index.js
```

这是测试用 adapter，不连任何 AI。
