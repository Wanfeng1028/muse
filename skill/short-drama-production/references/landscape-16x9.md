# 16:9 横屏生产合同

## 1. 默认项目规格

新项目默认：

```json
{
  "aspectRatio": "16:9",
  "orientation": "landscape",
  "deliveryWidth": 1920,
  "deliveryHeight": 1080,
  "fps": 24,
  "compositionProfile": "landscape-ensemble",
  "safeArea": { "action": 0.95, "title": 0.90 },
  "generationResolution": "768P"
}
```

`generationResolution` 是 H3 生成档位，`deliveryWidth/Height` 是后期交付规格，两者不要混为一谈。样片默认 768P 控制成本；用户批准清晰度和成本后可改为 2K。成片粗剪统一装配为 1920×1080。

## 2. 横屏导演语法

16:9 的优势是关系、空间和调度，不要把竖屏方案简单扩边：

- 优先把冲突双方放在左右三分位，用距离、遮挡和负空间显示权力。
- 双人镜、过肩镜和前后景关系可以承担叙事；特写只留给认知、证据和反应。
- 人物横向移动要维护屏幕方向；进出画、视线和道具交接都必须写明左右关系。
- 群戏先建立空间层级，再用中近景转移权力；不要把所有人物排成横向合影。
- 横向运镜必须有可见触发、路径和停点。平移不是“电影感”，是关系变化。
- 关键文字、证据和脸避免贴近左右边缘；为播放器裁切和平台控件保留安全区。
- 手机、电脑或文件承载剧情关键信息时，不因横屏有更多空间就把内容留在小屏幕里。环境镜头之后使用占画面至少一半的插入镜头、全屏主观内容或后期合成，并明确切回人物反应。

导演阶段必须显式使用：

```bash
node <short-drama-director>/scripts/director-kit.mjs seed <script.json> --aspect 16:9
```

若导演包仍为 9:16，桥接器必须失败；不得在技术分镜阶段偷偷改横屏。

## 3. 分镜图和 H3

- 每张关键帧和分镜图使用 16:9，不接受“横屏项目 + 竖屏参考帧 + 后期裁切”的默认做法。
- Ref2VA 任务显式提交 `ratio=16:9`。
- I2VA / FL2VA 的官方接口会把 `ratio` 视为 `adaptive`，实际画幅由输入首帧/尾帧决定，因此这些帧本身必须是 16:9。
- 提示词的构图描述使用 left/right third、foreground/background plane、lateral separation、negative space 等横屏关系语言；不要沿用“人物居中、上下留字幕”的竖屏惯性。
- 同一项目的 `production.json`、导演包、storyboard、H3 job 和 edit plan 画幅必须一致。

## 4. 后期与衍生版

粗剪采用 `contain-pad` 统一输入尺寸，不直接拉伸。出现黑边说明上游片段画幅或构图未对齐，QC 必须记录。

9:16、1:1 等平台衍生版是新的交付制品，需要单独重构图、字幕安全区和审片；不能把 16:9 母版的中心裁切视为自动完成。若需要多画幅，从导演期就建立保护构图和版本依赖。
