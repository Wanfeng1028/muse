# @playhouse/agent-canvas

剧坊 Playhouse 的可视化编排画布 POC：把 AI 短剧的编剧、分镜、视频生成、剪辑、质检五个环节摆成一张可拖拽的流程图，方便人工查看和调整流水线。

## 构建

```bash
npm install
npm run typecheck
npm run build
```

构建产物只有一个文件：`dist/agent-canvas.js`（IIFE 格式，CSS 已内联进 JS）。react、react-dom、@xyflow/react、zustand 全部打进这个 bundle，不依赖任何外部模块。

## 用法

宿主页面是 Spring Boot 直出的 vanilla 静态页，没有构建链、不能解析外部依赖，所以这里打包成自包含的单文件，直接用一个 script 标签引入，再用自定义元素挂载：

```html
<script src="/agent-canvas/agent-canvas.js"></script>
<agent-canvas src="/api/canvas/project"></agent-canvas>
```

`src` 指向返回 CanvasProject JSON 的接口（格式见 `project.schema.json`，示例见 `example.project.json`）。元素加载后会拉取数据并渲染画布；数据缺失或校验不通过时渲染空画布，不会抛错。

## 说明

- 包是 `private: true`，只在剧坊内部使用。
- 只支持 React 18（18.3.1），不要升级到 React 19。
- 节点类型与颜色定义在 `src/types.ts` 的 `NODE_KINDS`，均为实色，不用渐变。

## 并发冲突

`PUT /api/canvas/project` 请求体必须带 `base_version`（整数，等于 GET 到的 `revision`）。版本过期服务端返回 409，body 为 `{"status":409,"error":"Conflict","message":"...","current_version":<数字>,"updated_by":"editor"|"agent",...}`。前端收到 409 时弹窗：`updated_by` 为 `agent` 显示「内容已被 agent 修改，是否刷新？」，按钮「刷新」/「取消」。点刷新重拉服务端数据，点取消保留本地编辑——但取消后再点保存仍会 409。agent 写入走 service 层 `canvas.save_project` / `canvas.apply_patch` 接口（POC 阶段仅定接口，真实执行随网关 POC 落地，尚未接线）。

## 安全（本地限定）

`application.yml` 默认绑 `0.0.0.0`（`compose.yml` / `docker-compose.yml` 里 nginx 容器要通过服务名连主服务，全局写死 `127.0.0.1` 会让容器网络连不上）。POC 本地运行时加 `--spring.profiles.active=poc-local` 仅绑回环（加载 `application-poc-local.yml`）。Docker / 生产部署不许启用该 profile。POC 无鉴权，仅限本机访问时不许对外暴露。

## 存储切换触发条件

以下任一发生即触发切换：后端离开 localhost；出现第二个写入者（第二个浏览器 tab / 第二个 agent / 第二个用户）。触发后先把文件存储换掉（换 SQLite 或远端），再继续加功能。

## 主题定制（Shadow DOM + 白名单）

组件用 Shadow DOM 隔离样式。宿主页面可通过 CSS 自定义属性透传主题，但组件只认 `--ph-*` 前缀白名单：`--ph-canvas-bg`、`--ph-panel-bg`、`--ph-panel-border`、`--ph-text`、`--ph-accent`。白名单仅在 `connectedCallback` 读取一次。非白名单变量不会透传。
