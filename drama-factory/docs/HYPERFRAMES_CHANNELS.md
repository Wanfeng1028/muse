# HyperFrames 两条接入通道选型指南

这份文档写给两类人：一类是负责部署和排障的运维，一类是要在代码里接 HyperFrames 的二次开发者。目标很简单：让你在动手之前先搞清楚仓库里其实有两条完全不同的接入通道，它们各自怎么配、失败时会怎么样、什么场景该选哪条。

先给一个最重要的结论：这两条通道不是同一个东西的两种叫法，它们的入口、失败语义、配置范围都不一样。选错了，排障方向会完全跑偏。

## 两条通道一览

| 通道 | 入口 | 失败语义 | 适用场景 | 配置键 |
| --- | --- | --- | --- | --- |
| 独立通道 HyperFramesVideoProvider | bean 名 `hyperFramesVideoProvider`，`name()="hyperframes"`，是 VideoProviderRouter 优先级链上的一环（DEFAULT_ORDER = agnes, minimax, novai, doubao, hyperframes, htmlrender, painted） | submit() 先跑 `--version` 探活，CLI 不可用直接抛错；抛错后由 Router 交给下一环 provider 继续尝试。后台执行 `hyperframes render -c composition.html -o out/video.mp4 --resolution 1080p --fps <fps> --workers 2 --no-browser-gpu`（browserGpu=false 是默认值） | 你确实要 HyperFrames 的渲染能力，并且接受"CLI 不在就直接失败换人"这个前提；任务允许被 Router 调度到别的 provider | `drama.video.hyperframes.*`（enabled / cli / work-dir / resolution / fps / workers / timeout-minutes / browser-gpu） |
| 内嵌引擎 HtmlRenderVideoProvider | bean 名走 `htmlrender`，`name()="htmlrender"`；HyperFrames 只是 HTML 降级通道内部的一个引擎选项，由 `drama.video.htmlrender.engine` 选择，取值 `chromium`（默认）或 `hyperframes` | engine=hyperframes 时，探活失败或渲染失败会自动降级回 chromium 管道，只打 warn 日志，不抛错；poll() 和 TASK_PREFIX（`htmlrender:`）语义不变 | 你只是想给现有的 HTML 渲染加一个更真实的渲染引擎选项，但必须保证任务内部兜底、绝不因为引擎问题把整个任务打挂 | `drama.video.htmlrender.engine`；CLI 地址复用 `drama.video.hyperframes.cli` |

两条通道的差别，用一句话概括：独立通道是 Router 链上的一个 provider，失败就抛错走下一环；内嵌引擎是 htmlrender provider 内部的一个开关，失败就自己吞掉降级回 chromium。

## 选型决策树

按顺序问自己三个问题。

问题一：你是否需要确定性 HTML 渲染，但 chromium 截图管道已经够用？

如果你的答案是需要 HyperFrames 那套真实渲染，chromium 截图满足不了你，往下走问题二。如果你的答案是 chromium 截图已经够用，HyperFrames 只是锦上添花，那就别开内嵌引擎，保持 `drama.video.htmlrender.engine=chromium` 默认值即可，少一个变量少一份排障成本。

问题二：CLI 缺失时，你接受任务直接失败走下一 provider，还是必须内部兜底？

接受失败走下一环的，选独立通道 HyperFramesVideoProvider。它的语义就是"我尽力，不行就抛错让 Router 换人"，前提是你 Router 链上后面还有 htmlrender、painted 这些能接盘的 provider。

必须内部兜底的，选内嵌引擎。它的语义是"我尽力，不行就悄悄降级回 chromium"，任务不会因为引擎问题整体失败，代价是你在结果里可能看不出来这次到底用的哪个引擎，得靠日志。

问题三：运维能否保证 CLI 安装？

能保证 CLI 装好并且路径正确，两条通道都可以选，按问题二的偏好来。

不能保证 CLI 装好，或者部署环境经常变动、CLI 可能时有时无，那优先选内嵌引擎，因为它的降级是自动的、不抛错的。独立通道在这种情况下会频繁抛错，虽然 Router 能接住，但任务成功率会被拉低，日志里也会一直出现探活失败。

## 配置对照表

先说共用的键：

- `drama.video.hyperframes.cli`：CLI 地址。两条通道都用这个键。独立通道直接用它来执行渲染；内嵌引擎在 `engine=hyperframes` 时也复用它。也就是说，你改这一个键，两条通道的 CLI 指向会一起变。

再说各自独有的键：

独立通道独有：

- `drama.video.hyperframes.enabled`：是否启用独立通道。
- `drama.video.hyperframes.work-dir`：工作目录。
- `drama.video.hyperframes.resolution`：分辨率，实际命令里会传 `--resolution`。
- `drama.video.hyperframes.fps`：帧率，实际命令里会传 `--fps`。
- `drama.video.hyperframes.workers`：worker 数，独立通道默认 2，实际命令里会传 `--workers 2`。
- `drama.video.hyperframes.timeout-minutes`：超时时间。
- `drama.video.hyperframes.browser-gpu`：是否启用浏览器 GPU，默认 false，对应命令里的 `--no-browser-gpu`。

内嵌引擎独有：

- `drama.video.htmlrender.engine`：取值 `chromium`（默认）或 `hyperframes`。这是内嵌通道唯一的选择开关。

注意一个容易踩的点：内嵌引擎没有自己独立的 workers 配置键。当 `engine=hyperframes` 时，worker 数走 CLI 默认的 auto，不会读独立通道那个 `drama.video.hyperframes.workers`。也就是说独立通道默认 2 这个值，跟内嵌引擎没关系。

## 常见误区

误区一：把内嵌引擎当成 Router 链上独立的一环。

不是。内嵌引擎所在 provider 的 `name()` 仍然是 `htmlrender`，TASK_PREFIX 仍然是 `htmlrender:`，poll() 语义也没变。它在 Router 眼里就是 htmlrender 这一个 provider，HyperFrames 只是它内部的一个引擎选项。你在 Router 日志里不会看到一个叫 hyperframes 的独立环节来自内嵌通道。真正在链上叫 `hyperframes` 的，只有独立通道那个 provider。

误区二：`engine=hyperframes` 但 CLI 没装，会"静默失败"。

不是静默失败。探活失败或者渲染失败时，内嵌引擎会打 warn 日志，然后自动降级回 chromium 管道继续跑。任务不会因此抛错，但日志里会留下 warn 记录。如果你排查问题时只盯着最终结果不看日志，就会误以为什么都没发生，实际上引擎已经悄悄换了。

误区三：`--workers` 在内嵌引擎里也会按独立通道的默认值走。

不会。`--workers` 是独立通道命令里的参数，默认 2，由 `drama.video.hyperframes.workers` 控制。内嵌引擎没有配置这个参数，用 CLI 自己的默认 auto。两条通道在 worker 数上的行为不一致，不要想当然地认为配了独立通道的 workers 就能影响内嵌引擎。

误区四：以为改 `drama.video.hyperframes.cli` 只影响独立通道。

不是。内嵌引擎的 CLI 地址复用的就是这个键。你改了它，两条通道一起受影响。如果你只想动一条通道的 CLI 指向，当前配置结构做不到，需要改代码。

## 相关文档

- 降级语义：见 [DEGRADATION.md](DEGRADATION.md) 里的 "htmlrender 双引擎" 小节。
- 联调实测报告：见 [HYPERFRAMES_RENDER_PROBE_2026-10-20.md](HYPERFRAMES_RENDER_PROBE_2026-10-20.md)。这份报告记录了 hyperframes@0.8.176 的实测结果，`--version`、`--resolution`、`--no-browser-gpu` 全部真实可用，2 秒 1080p 真实渲染产物 16.2KB。
- 引擎落地任务：见 [dod-hyperframes-engine-20261020.md](dod-hyperframes-engine-20261020.md)。
- 一键探活工具：`scripts/hyperframes_probe.sh`，跑完会输出推荐的 engine 取值。
