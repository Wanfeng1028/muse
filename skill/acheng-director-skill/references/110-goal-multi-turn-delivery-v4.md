# 110｜Acheng Director `/goal` 多轮交付合同 v4

## 这份合同解决什么问题

`/goal` 保存一个跨回合持续目标，不能把“完成全部生产”解释成“本轮把全部正文塞进一条回复”。真正决定交付方式的是 `execution_mode`：

- 数字 `1`：`autonomous_file_batch`，默认/推荐。宿主有工作区写入能力时，自动把长正文逐段写成独立文件，聊天直接展示逐段上传操作卡，并附 manifest、文件与验收结果。
- 数字 `2`：`interactive_segment`。每轮只交付一个完整 Segment，提交后停止，方便用户即时调整角色、空间、动作、镜头和连续性。

核心 Skill 不依赖 Antigravity IDE；Antigravity 的工作区路径、文件查看和工具执行方式只写在下面的用户模板中。换用其他宿主时，只需替换工作区和工具能力部分。

## `/goal` 的硬回合协议

以下规则优先于“完成全部”“不要停”“连续输出”等泛化表达：

1. 新建一次目标时，第一响应只发送固定的 1/2 选择题，不输出剧本、资产、分镜或 H3 正文。数字 `1` 是默认/推荐模式，但仍应由用户明确回复 `1` 或 `2`，避免宿主误判当前运行状态。
2. 收到 `1` 后写入 `autonomous_file_batch`：先创建计划、状态文件和输出目录，再按顺序写独立 artifact；每份文件必须通过内容门禁、哈希和状态提交。
3. 收到 `2` 后写入 `interactive_segment`：每个助手回合最多提交一个完整 Segment；提交后立刻停止，并输出 `WAIT_FOR_USER_CONTINUE`。
4. 交互模式中，用户回复 `继续` 或 `下一段` 后才允许进入下一个未提交 Segment；用户提出修改意见时，先修复对应字段，再继续保存的游标。
5. 如果一个 Segment 超过单次输出上限，只提交当前字段边界以前的 partial 内容，并返回 `continuation_required=true`、`current_cursor` 和下一节名称；下一回合继续同一 Segment，不能压缩或改写成摘要。
6. 自动文件模式可以连续调用工具，但不是无限后台任务；工具、权限、时间、上下文或磁盘受限时保存已提交产物并暂停，不能声称全部完成。
7. 两种模式都必须遵守按本段时长与复杂度动态计算的 Ref2VA 密度门（默认 10 秒段最低 2,000、目标约 2,400 个英文词），并保留六字段顺序、逐镜空间事实和动作因果。长度不足时返回失败或 partial，不能以 `PASS` 掩盖不足。
8. 每个 Segment 写入 manifest 或交给用户前，必须执行一次 `111-h3-final-format-pass-v4.md`。该 pass 只修字段、标签、Shot 标题、speaker/对白绑定和全局声音结构，不删除工程参数、动作细节、对白或长文；失败只能保存 `format_pass=FAILED`、证据和游标，不能 accepted。

## Antigravity IDE 推荐 `/goal` 模板：默认自动文件批处理

这个模板适合你在 Antigravity IDE 中一次提交后让模型持续产出。它要求模型使用当前打开的工作区或你指定的绝对目录写文件，并在聊天直接展示逐段上传操作卡，并附 manifest、文件与验收结果；不要把“后台运行”理解成脱离宿主的无限任务。

```text
/goal

goal:
  name: [项目名称]
  objective: 使用 Acheng Director 完成从剧本、人物弧光、分镜、资产到 MiniMax H3 的完整 prompt_only 生产包，并把每个长产物保存到 Antigravity IDE 当前工作区。

host:
  environment: Antigravity IDE
  workspace: [当前 IDE 工作区绝对路径；留空表示使用当前打开工作区]
  file_write: 如果宿主提供文件写入工具，直接使用；不要把长正文重复贴回聊天。
  file_read: 写入后重新读取每个文件进行门禁检查，并在聊天返回可点击的相对路径或绝对路径。
  runtime: 允许连续工具调用，但受当前宿主会话、权限、上下文、磁盘和运行时长限制；受限时保存已提交文件并暂停。

delivery_protocol:
  first_response: 只发送固定的 1/2 交付方式选择题，未选择前不要输出正文。
  selected_mode: autonomous_file_batch
  default_choice: 1
  after_user_selects_1: 创建 workflow_state.json、计划文件和输出目录；逐段生成、读取、验收、计算 SHA-256 并提交独立文件。
  per_segment_files: [SEGMENT_ID.h3.txt、资产提示词文件、上传清单、QA 记录]
  chat_output: 直接展示每份 H3 的简洁上传操作卡，附 manifest、正文链接、状态、哈希、未决项、current_cursor 和 visual_status；长正文留文件。
  partial_rule: 任何未达到完整字段或 Ref2VA 长度门禁的文件只能是 partial，必须保存 current_cursor，不能 accepted。
  final_format_gate: 写入或提交前执行 references/111-h3-final-format-pass-v4.md；保持所有工程参数与正文细节，逐句核验 speaker、语言标签、原始对白、口型/停顿/声音方向和声音句数。
  completion_rule: 只有所有计划内文件通过门禁并写入 manifest 后才报告 COMPLETED；工具中断时报告 PAUSED 或 PARTIAL。

project:
  type: [原创动画 / 实拍风格化 / 其他]
  style: [例如 3渲2、电影感、手绘等]
  genre: [喜剧 / 动作 / 悬疑 / 混合]
  story: [完整故事创意]
  total_duration: [目标总时长]
  segment_duration: 每段 8–12 秒，根据动作和对白自然分段。
  image_model: GPT Image 2/2.5
  video_model: MiniMax H3
  references: [真实参考文件路径；没有就写无，先原创资产设计]
  paid_media_models: 不调用付费图像、视频或音频生成模型。

capability_triggers:
  必须把以下词落实为字段、可见动作、镜头路径或验收证据：角色灵动表演、微动作、微表情、五轨表演（gaze、breath、shoulder、body_hands、dialogue）、空间位置关系、身体朝向、视线方向、场景美学、氛围感、连续性账本、提醒校验逻辑、镜头实际路径、切镜承接、连续尾态。
  如果有打戏或追逐，再启用：打戏逻辑链、打戏因果链、攻应果续、direction_facts、speed_profile、approach、commit、contact、recovery、reset、force_source、trajectory、resistance、impact_hold、transfer、recoil、合法慢动作接触窗口。
  每个触发词都必须在产物中对应字段、可见动作、镜头路径或 QA evidence，不能只出现在标题。

h3_contract:
  mode: 有真实参考资产时默认 Ref2VA，并锁定 mode、mode_lock、mode_selection_reason；没有真实参考文件时不得伪造 Picture/Video 标签。
  ref2va_fields: subject_definitions、summary、retention_analysis、detailed_description、overall_soundscape、non_diegetic_music，顺序不可改变。
  detail: detailed_description 按时长与复杂度动态计算最低词数（默认 10 秒段为 2,000）和目标词数（默认约 2,400），极限值 2900 词硬性封顶（处于 2200-2900 词区间，剔除无上限输出）；每个镜头独立展开角色外观、场景空间、位置、朝向、动作因果、微动作、微表情、相机路径、声音和尾态。
  short_output: 不得用通用短模板压缩；长度不足只能 partial + current_cursor。 

deliverables:
  先完成导演总控台、能力触发图、完整剧本、人物弧光和闭合时间轴，再生成资产提示词和逐段 H3 文件。
  资产任务先制作并批准 STYLE_MOTHER，再生成角色、场景、道具和关键帧资产提示词。
  每个资产和每个 H3 文件必须脱离聊天独立使用；禁止“同上”“沿用前段”“见角色设定”。
  每个文件附参考图上传清单、机器验收结果、未决项和 visual_status=UNVERIFIED。

stop_conditions:
  自动模式只在文件写入、读取和提交能力实际可用时继续；受限时保存已提交产物、状态和游标并暂停。
  不声称真实图像、视频或音频已经生成。
```

## Antigravity IDE 交互制作模板：数字 2

当你想边看边调整时，把项目内容接到这个模板末尾，然后在固定选择题中回复 `2`：

```text
/goal

使用 Acheng Director 完成这个项目，但本次选择交互制作模式。

delivery_protocol:
  selected_mode: interactive_segment
  mode_number: 2
  每轮最多交付一个完整 Segment；完成后输出 WAIT_FOR_USER_CONTINUE 并停止。
  我回复“继续”或“下一段”后才开始下一个 Segment。
  当前 Segment 未完成时，从 current_cursor 继续；禁止摘要、缩写、“同上”和“沿用前段”。
  每轮结束时报告已锁定事实、可调整项、参考图上传清单、机器验收和 visual_status=UNVERIFIED。

host:
  environment: Antigravity IDE
  workspace: [当前 IDE 工作区绝对路径]
  可以把已完成 Segment 同步保存为独立文件，但聊天必须显示当前 Segment 的完整正文。

project_input:
  [在这里粘贴项目类型、风格、故事、角色、场景、总时长、资产模型、视频模型和能力触发词。]
```

## 用户选择哪种模式

选择 `1`：想一次提交后自动写入多个独立文件，聊天直接展示逐段上传操作卡，并附 manifest、文件与验收结果，之后在 Antigravity 工作区验收。选择 `2`：想在聊天中逐段看到完整内容并即时修改。两种模式不会静默互换；新建另一项任务才重新询问。
