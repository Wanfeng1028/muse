# 方法来源与研究边界

## 项目归属

- **夏夏 Skill 核心架构、工作流整合与实现：栾意 <luanyi824@outlook.com>。** 核心架构包括剧本事实锁、时长预算、段落判型、生成组体系、中文导演分镜格式、Seedance 2.5 编译层与校验闭环。
- **底层电影视觉方法：造梦师开源项目。** Scene Master、摄影机观看位置、真实光源、构图、连续性 Bible / Shot Delta、反 AI 清理和提示词编译思想，基于并改编自 ZY / popopo-99 的《造梦师：AI时代电影视觉指南》（`zy-cinematic-realism`）。
- 夏夏不是造梦师官方发行版；它是在造梦师开放方法基础上，面向中文分镜与 AI 视频制作重新组织、扩展和实现的独立项目。

## 底层方法

- `zy-cinematic-realism`（《造梦师：AI时代电影视觉指南》）：底层方法来源，Copyright (c) 2026 ZY / popopo-99，采用 CC BY-NC 4.0；夏夏基于并改编其 Scene Master、导演四轴、摄影机观看位置、真实光源、连续性 Bible / Shot Delta、反 AI 清理和提示词编译思想。
- 项目主页：https://github.com/popopo-99/zy-cinematic-realism
- 夏夏没有打包、安装或执行其他第三方 Skill，也没有包含其他第三方仓库的代码、角色、剧本、示例资产或专有包装结构。

## Seedance 2.5 交叉参考

- ByteDance Seed 官方产品页：
  https://seed.bytedance.com/en/seedance2_5
- ByteDance Seed 官方介绍：
  https://seed.bytedance.com/en/blog/one-take-creation-flexible-referencing-introducing-seedance-2-5
- 火山方舟官方文档入口（实际提交前核对当前接口）：
  https://console.volcengine.com/ark/region:cn-beijing/docs/82379/2607689?lang=zh

## 使用原则

- 造梦师提供底层电影视觉方法，不是夏夏的运行时依赖；夏夏不会自动下载或执行外部仓库。
- 不复制或打包其他第三方 Skill 的原文、代码、专有示例、角色、剧本或包装逻辑。
- 时长、分辨率、素材数量、人物政策、首尾帧与参考素材兼容性可能随界面变化；实际提交前核对用户当前界面。
- 本 Skill 固定保留用户要求的生产规则：每组 4–30 秒、组标题写明时长、分镜格式完整、面向 AI 生成并保持组间连续。
