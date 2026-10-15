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
