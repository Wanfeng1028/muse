# 截图 Harness 文档

## 为什么需要这个 harness

以前截图脚本散落在外部目录、服务没就绪就截图，出过空白页事故；本 harness 将启动→就绪→播种→截图→清理收敛为一条命令，杜绝此类问题。

## 一键运行

```bash
# 先构建前端产物，保证 dist 最新
pnpm --filter @kaoyan/web run build

# 执行截图
node scripts/shots/run-shots.mjs

# 可选：指定端口（默认 18131）
node scripts/shots/run-shots.mjs --port 19132
```

也可使用 package.json 中注册的快捷脚本：

```bash
pnpm shot          # 直接截图（需先构建）
pnpm shot:build    # 先构建前后端，再截图
```

## 流程四步

1. **起服务** — `spawnServer` 以临时演示 DB 启动后端，端口默认 18131；若 DB 文件已存在则先删除，保证每次数据新鲜。
2. **等就绪** — `waitForHealth` 轮询 `/api/health`，直到服务完全启动才继续。
3. **播种演示数据** — `registerAndLogin` 注册 `shotbot` 用户并登录拿 token；`seedDemoData` 向服务注入一组覆盖各页面的演示数据。
4. **拦截路由截图** — `createShotContext` 创建带认证拦截的浏览器上下文；`runShotPlan` 按 plan 逐项导航页面、等待关键 selector、执行交互动作后落盘截图。

## 路由注册顺序铁律

后端路由注册顺序决定匹配优先级：**静态资源先注册、/api 路由后注册**。后注册的路由匹配优先级更高，确保 `/api/*` 不会被静态文件中间件吞掉。新增路由时必须遵守此顺序。

## playwright-core 解析顺序

harness 按以下优先级查找 `playwright-core`：

1. **裸 require** — 先尝试 `require('playwright-core')`，若 Node 已能解析则直接使用。
2. **`PLAYWRIGHT_CORE_PATH` 环境变量** — 若设置，从该路径加载。
3. **兜底路径** — `/home/hatch/workspace/muse-build/shot/node_modules/playwright-core`。

三者均失败时抛出明确错误提示。

## 截图输出

所有截图写入 `docs/screenshots/`，文件名由 shot-plan 中 `shotName` 字段决定：

| 文件名 | 页面 | 说明 |
|---|---|---|
| dashboard.png | / | 仪表盘 |
| plans-light.png | /plans | 复习计划浅色 |
| plans-dark.png | /plans | 复习计划深色 |
| mistakes.png | /mistakes | 错题本 |
| words.png | /words | 单词 |
| exams.png | /exams | 真题记录 |
| heatmap.png | /heatmap | 自律热力图（含当日详情弹出） |
| weekly.png | /weekly | 周报 |
| data-transfer.png | /data | 数据导入导出 |

## 截图计划格式

`scripts/shots/shot-plan.mjs` 导出 `defaultShotPlan` 数组，每项：

```js
{
  name: '自律热力图',          // 中文短名（日志用）
  route: '/heatmap',           // 页面路由
  waitFor: '.hm-grid',         // 关键 selector，15s 内不出现则整轮失败（防空白页）
  actions: [                   // 可选：截图前执行的交互
    { click: '.theme-toggle', waitMs: 800 },      // 点唯一元素
    { clickLast: '.hm-cell.hm-clickable', waitMs: 900 }, // 点匹配集的最后一个
  ],
  shotName: 'heatmap.png',     // 落盘文件名
}
```

注意：`:last-child` 是 CSS 伪类（相对父元素），不能用来取"匹配集最后一个"，这种情况用 `clickLast`。

## 验收标准

每张截图必须由编排者**亲眼看**，逐项确认：

- 布局撑满视口，无大片空白或错位
- 无空白页（关键 selector 均已出现后才触发截图）
- 浏览器 console 无红色错误（runShotPlan 会自动收集 pageerror/console error，有则整轮失败并列出前 5 条）
