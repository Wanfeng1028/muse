# docs/pipeline-templates.md

## 一、13 个流水线模板一览

| 模板名 | 适用场景 |
|---|---|
| animated-explainer | 面向知识科普与概念讲解的动画视频流水线。 |
| animation | 面向动态图形、图解说明、动态排版、数学可视化、显式 Three.js 场景及风格化插画序列的动画优先流水线。 |
| avatar-spokesperson | 面向发言人视频、内部通报、新人入职、销售介绍及短脚本讲解的虚拟主播流水线。 |
| character-animation | 面向本地可复用卡通角色的角色动画流水线。 |
| cinematic | 面向品牌短片与电影感预告的流水线。 |
| clip-factory | 将长视频拆解为多平台短视频的流水线。 |
| documentary-montage | 以档案素材拼贴呈现单一主题的流水线。 |
| hybrid | 混合流水线，用于将原始素材与设计或生成的支持性资产相结合的视频。 |
| localization-dub | 以转写文本为先的本地化流水线，产出翻译字幕、配音音频及可选的口型同步语言版本。 |
| novel-to-drama | 把网络小说改编为竖屏短剧的流水线。 |
| podcast-repurpose | 播客转视频再利用流水线。 |
| screen-demo | 面向软件录屏演示的流水线。 |
| talking-head | 面向真人口播视频的流水线。 |

## 二、新增的 6 个模板介绍

本轮新增的 6 个模板由 OpenMontage/HyperFrames 工具链集成引入。

**animation**  
面向动态图形、图解说明、动态排版、数学可视化、显式 Three.js 场景及风格化插画序列的动画优先流水线。该模板在提案阶段需要显式选择渲染运行时，可选 remotion、hyperframes 或 ffmpeg。

**avatar-spokesperson**  
面向发言人视频、内部通报、新人入职、销售介绍及短脚本讲解的虚拟主播流水线。

**character-animation**  
面向本地可复用卡通角色的角色动画流水线。

**hybrid**  
混合流水线，用于将原始素材与设计或生成的支持性资产相结合的视频。

**localization-dub**  
以转写文本为先的本地化流水线，产出翻译字幕、配音音频及可选的口型同步语言版本。

**podcast-repurpose**  
播客转视频再利用流水线。

## 三、5 册风格手册

风格手册放在 `classpath:style-playbooks/*.yaml`，共 5 册：

- **anime-ghibli**：Anime Ghibli，warm whimsical 治愈系动画风。
- **clean-professional**：Clean Professional。
- **flat-motion-graphics**：Flat Motion Graphics。
- **minimalist-diagram**：Minimalist Diagram。
- **premium-minimalist**：Premium Minimalist。

## 四、9 个媒体预设

MediaProfileService 内置 9 个媒体预设：

| 预设 | 分辨率 | 用途 |
|---|---|---|
| youtube_landscape | 1920x1080 | YouTube 横屏 |
| youtube_4k | 3840x2160 | YouTube 4K 横屏 |
| youtube_shorts | 1080x1920 | YouTube Shorts 竖屏 |
| instagram_reels | 1080x1920 | Instagram Reels 竖屏 |
| instagram_feed | 1080x1080 | Instagram 方形帖子 |
| tiktok | 1080x1920 | TikTok 竖屏 |
| linkedin | 1920x1080 | LinkedIn 横屏 |
| cinematic | 2560x1080 | 电影宽银幕 21:9 |
| generic_hd | 1920x1080 | 通用高清 |

## 五、加载机制与 fail-fast 说明

13 个流水线模板放在 `classpath:pipeline-templates/*.yaml`，只读。服务启动时一次加载并缓存。任一模板缺 `name`、`version`、`stages` 必填字段，启动直接抛 `IllegalStateException`，fail-fast。

## 六、幻灯片风险评分器简介

SlideshowRiskScorer 给分镜打“幻灯片风险分”，用来评估分镜是否太像幻灯片。评分维度有 6 个：视觉重复、装饰性视觉、运镜薄弱、镜头意图薄弱、文字依赖、电影感声明缺乏支撑。分数越低越好。最终 verdict 分四档：strong、acceptable、revise、fail。