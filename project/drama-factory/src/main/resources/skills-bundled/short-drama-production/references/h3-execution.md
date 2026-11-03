# MiniMax H3 官方 API 执行合同

本页只在用户明确要求预检、提交、查询或下载 H3 视频时读取。API 会产生外部状态和费用；分镜完成不等于授权提交。

## 1. 当前接口

- 创建：`POST https://api.minimax.io/v2/video_generation`
- 查询：`GET https://api.minimax.io/v2/query/video_generation/{task_id}`
- 模型：`MiniMax-H3`
- 密钥：`MINIMAX_API_KEY`、`MINIMAX_API_KEY_FILE` 或 `~/.codex/secrets/minimax.key`

权威资料：

- <https://platform.minimax.io/docs/api-reference/video-generation-v2-create>
- <https://platform.minimax.io/docs/api-reference/video-generation-v2-query>

投产前重新核对官方页面；若参数发生变化，先更新适配器和测试。

## 2. 内置适配器

`scripts/h3-official.mjs` 直接读取 `production.json.jobs`，支持：

- `text`、`reference_image`、`reference_video`、`reference_audio`。
- `first_frame` / `last_frame`。
- 本地图片、视频、音频转 Data URL；请求体超过 64 MB 时拒绝并要求稳定公网 URL。
- 提示词 7000 字符、媒体格式、单文件大小、数量、时长和模式互斥预检。
- `16:9` 项目画幅贯穿 Ref2VA；首尾帧模式强制 `adaptive` 并由输入帧决定实际画幅。
- 提交、查询、轮询、下载、输出 SHA-256 和 `production.json` 状态回写。

本地媒体会进入请求体和外部 API。真实人物图像、视频和声音必须具备相应使用权。

## 3. 安全提交顺序

```bash
node scripts/production-kit.mjs validate <production.json>
node scripts/h3-official.mjs preflight <production.json> --id <job-id>
node scripts/h3-official.mjs dry-run <production.json> --id <job-id>
node scripts/production-kit.mjs job-approve <production.json> --id <job-id> --by user
node scripts/h3-official.mjs submit <production.json> --id <job-id> --confirm-submit <job-id>
node scripts/h3-official.mjs wait <production.json> --id <job-id> --poll 10 --timeout 3600
```

`--confirm-submit` 必须和 `job-id` 完全相同。默认只批准一个样片。接口已返回 `task_id` 后，连接中断也不得盲目再次提交；先查询原任务。

## 4. 状态语义

- 创建成功：`job.status=submitted`，记录 `execution.taskId`。
- `queued/running`：回写 `running`。
- `succeeded`：下载到 `outputPath`，计算 `outputSha256`。
- `failed/cancelled`：停止，不自动付费重试。

API 成功只证明文件生成完成。角色、声音、口型、台词、动作、镜头切点和画幅仍需执行后期与人工导演 QC。

