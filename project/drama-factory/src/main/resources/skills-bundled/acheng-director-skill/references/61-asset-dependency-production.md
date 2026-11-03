# 61｜全资产需求、版本与参考生产顺序

## 从剧本建立需求

H3 段内引用按[114 合同](114-reference-binding-delivery-v4.3.6.md)衔接：shots 提出确需引用的对象/状态，assets 提供批准版本，model 完成请求局部绑定，continuity 核查污染。制作所需 required_assets 不自动等于全部上传；不要强制每段带 STYLE_MOTHER。

逐场盘点出场角色及身份版本、服装/发型/伤势、场景与补充视角、可操作道具、载具、特效形态和关键帧。每镜required_assets列实际需要的资产ID；required_prop_ids列关键道具。扫描文字并人工检查漏项，机器随后核对声明的角色/场景/道具覆盖；机器不声称自然语言中任何隐含资产都能自动发现。

asset_plan每项id、kind、entity_id（绑定角色/场景/道具时）、version、purpose、depends_on、status。kind支持character/costume/injury/scene/prop/vehicle/keyframe/effect/style。planned项必须有同ID的asset_cards和相同asset_version；approved项必须有真实file和sha256。生成图经核对才批准，不能因文件存在就自动批准。

## 依赖与独立正文

基础身份图、场景母图和独立道具图可以先纯文字创建。换装、伤势变体和叙事关键帧在依赖基础图后创建。依赖图无环，编号只是管理ID；模型正文展开实际脸、体型、服装、动作和场景。

资产卡的references可用asset_id、asset_version代替尚未存在的file，同时保留image编号、role、subject、preserve、exclude。卡片依赖与depends_on必须一致。参考图批准后，resolve_card按版本解析成真实文件，导出副本与哈希。

比如关键帧依赖两个人物、一张场景、一件道具：逐图说明谁提供身份、谁提供空间、谁提供几何；人物参考的姿态和灯光不自动继承。关键帧prompt同时重新描述当前伤势、道具所有权和单一相位。姿势参考不能覆盖身份图。

关键帧节点的目标镜头由 shot_ids、将该关键帧列为 required_assets 的镜头，或指向镜头的 entity_id 确定。存在 ShotSpec 时不能留空或指向未知镜头；目标范围不能漏掉实际消费镜头。目标镜头 required_assets 中的人物、场景、道具、服装/伤势/效果等实际需求，必须成为关键帧的直接 depends_on，并在图像卡中有同一资产版本的编号参考。风格依赖另由62合同补齐；其他关键帧不自动相互依赖。不要把无关物件写进 required_assets 后再靠删除引用绕过覆盖门。

制作孤立关键帧而尚无 ShotSpec 时，只能证明清单里声明的素材被绑定，不能声称整场资产需求已经覆盖。补齐镜头后再执行覆盖校验。四视图身份板可供 Ref2VA 提取人物身份，不能因其是图片就当作 I2VA/FL2VA 的单一剧情起止帧。

资产卡 asset_kind 必须与计划 kind 一致。同一 asset_id 同时填写 file、sha256、entity_id、state_label 或 state_version 时，必须与批准节点一致；解析器不再静默覆盖冲突值。批准锚点和所有参考必须是真实图片文件，而不是 .image.txt。

## 两种交付状态

`python scripts/compile_assets.py production.json --out output/images`要求本次所有参考齐全。缺图时停止导出，输入不变。

`python scripts/compile_assets.py production.json --draft --out output/asset-plan`允许交付完整生产设计：可提交的基础资产为.image.txt；等待参考的项为.draft.txt，首行标明不可提交，UPLOAD列缺少的资产、版本、用途和编号。即使同一包内有已就绪项，整个包也标dependencies-pending。

完成上游图后将其node标approved并登记file/sha256，然后重新导出新的目录；不把草案改名冒充就绪。生成模型的实际尺寸、质量和版本在调用设置中核实，不以提示词里写路径代替上传。

## 变更影响

检查结果中的production_order给出制作顺序；impact列出修改任一资产后受影响的后继资产、镜头与片段。改变version后，所有绑定旧版本的参考会被拒绝，须明确重绑或保留旧版。档案同时保存批准素材、草案、源数据与引用，恢复后不依赖原工程路径。

## 清洁与重建

仍使用IM2七步和单变量修正：先身份/结构，再媒介、构图、光材、密度、受控细节和当前风险。干净不等于抹平旧化与手工痕迹。一个局部修复不得改变人物骨相、道具拓扑或场景入口；变换机位时明确REBUILD受影响的遮挡与新露出表面。

最终验收分别记录资产规划完整、参考就绪、提示词合规、实际画面通过。四种状态不能互相替代。
