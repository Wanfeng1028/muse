# Acheng Director v3.5.4 会话交接文档

## 交接目的

本文件用于在新的 Codex 会话继续维护 `acheng-director`。新会话先读取本文件，再读取 `SKILL.md`、相关合同和当前工作树，不要依赖旧会话的口头历史。

## 当前基线

- 最新可交付包：`3.5.4`（本次会话已完成发布准备）
- 工作树：`C:\Users\dcf\.codex\worktrees\0668\codex工作区\deliverables\acheng-director`
- 历史基线包：`D:\codex工作区\deliverables\acheng-director-v3.5.3.zip`
- 3.5.4正式包：`D:\codex工作区\deliverables\acheng-director-v3.5.4.zip`
- 3.5.4包 SHA-256：见交付目录根部 `SHA256SUMS.txt`（哈希不写回包内，避免自引用）。
- 3.5.4包验收报告：`reports/package-acceptance-v3.5.4.json`
- 最新包验收状态：`PASS`
- `3.5.4` 状态：正式交付包；真实生成媒体仍未执行，`visual_status` 必须保持 `UNVERIFIED`。

四个安装目录仍保持在上一版 v3.5.3；本次只交付独立 3.5.4 包，不自动覆盖安装目录：

1. `C:\Users\dcf\.codex\skills\acheng-director`
2. `C:\Users\dcf\.gemini\config\skills\acheng-director`
3. `C:\Users\dcf\Desktop\minimax\skill\ai影视导演助手\acheng-director`
4. `D:\codex工作区\deliverables\acheng-director`

## 已完成改动

### 1. STYLE MOTHER 风格锚定

新增 `references/62-style-anchor.md`，定义：

- `STYLE_MOTHER` 作为无剧情身份的风格测试帧；
- 可选 `STYLE_CHARACTER_PROBE`、`STYLE_ENVIRONMENT_PROBE`、`STYLE_EFFECT_PROBE`；
- `style_lock` 根合同，包括锚点 ID、版本、状态、媒介、保留范围、排除范围和适用资产类型；
- 身份参考、场景参考、ShotSpec、风格母版的权威优先级；
- 批准文件和 SHA-256 校验；
- 风格母版不得覆盖身份、场景拓扑、动作、姿态、状态、相机和精确光位。

代码入口：

- `scripts/post_hooks.py`：`check_style_lock()`；
- `scripts/prompt_delivery.py`：将风格母版作用范围和排除范围注入 GPT Image 独立提示词；
- `scripts/asset_plan.py`：风格锁启用时保留非角色资产类型；
- `scripts/compile_assets.py`：编译资产时传递 `style_lock`；
- `modules/assets/SKILL.md`、根 `SKILL.md`：已加入调度规则。

风格锁是 opt-in。未声明 `style_lock` 的项目保持原有资产流程，不自动增加风格依赖。

### 2. H3 打戏方向与速度规范

新增 `scripts/combat_timing.py`，并接入 `scripts/audit_storyboard_quality.py`。当镜头 `features.combat` 为 true 时，必须提供 `combat.timing`：

- `axis_lock`：180 度轴线和左右关系；
- `spatial_direction`：出发点、目标点、屏幕方向和结果方向；
- `speed_curve`：快慢节奏总体原则；
- `camera_sync`：摄影机与动作锚点的同步；
- `phases`：完整覆盖 approach、commit、contact、recovery、reset 或等价阶段；
- `slow_motion`：是否启用、触发事实、理由、比例、时间窗和退出条件。

编译器会把 timing 展开到最终 H3 正文，避免出现冲刺朝向错误、无目标位移、无因慢动作或接触后瞬间重置。

相关合同：

- `references/40-action-choreography.md`；
- `references/70-minimax-h3-compiler.md`；
- `modules/model/SKILL.md`；
- 根 `SKILL.md`。

### 3. 交付完整性门禁执行入口（3.5.4）

补齐 `scripts/delivery_integrity.py`，把 `references/94-delivery-integrity.md` 的单次只读门禁落成可运行合同：检查阶段范围、full_production 过度声明、模型正文省略 shorthand、资产依赖缺口和机器审计证据，输出 `scope/delivered/blocked/evidence/unresolved/next_action` 回执。默认保留未生成媒体和缺图事实；`--require-ready` 才把未解决项升级为阻塞。新增 `scripts/test_delivery_integrity.py` 四个回归用例，并同步三个安装目录。

### 4. 本轮继续优化：结构化打戏 timing 与 H3 展开

为回应 H3 过简、冲刺方向不自然和无因慢动作问题，`scripts/combat_timing.py` 已从字符串存在性检查提升为可执行合同：

- `direction_facts` 必须写 origin、target、screen_direction、body_orientation、weapon_direction、support_point、result_direction；
- `speed_profile` 必须分别写 support、acceleration、contact_read、recovery；
- 每个阶段必须覆盖完整镜头帧区间，并按 approach → commit → contact → recovery → reset 排序；
- 每阶段必须写 positions、orientation、action、combat_logic、camera、dof、composition、dynamics、tail_frame；`combat_logic` 明确 attacker → target → target_point → intent → defender_state → response → result → next_authority；
- 慢动作窗口必须与 contact 阶段重叠且 contact 播放类型为 `slow_motion`；关闭慢动作时不得带窗口或慢速播放阶段。

`audit_storyboard_quality.py` 的 H3 编译现在逐阶段展开这些字段，独立 `.h3.txt` 会明确支点、加速、接触、受力、回收、相机矢量和尾帧，而不是只输出一组概括句。`templates/shot-spec.yaml`、机甲／巨构样例、规范文档和 `test_v3_contracts.py` 已同步；新增回归覆盖缺阶段、慢动作错窗、方向事实缺失和 STYLE_MOTHER 非最后上传槽位。

本轮验证：`scripts/test_*.py` 共 32 项通过；机甲与巨构样例审计通过；`validate_director_contract.py --report reports/package-acceptance-v3.5.4-combat-style.json` PASS；`quick_validate.py` PASS。实际生成媒体仍未生成，`visual_status` 保持 `UNVERIFIED`。

## 已验证结果

以下命令已通过：

```powershell
python scripts/test_v3_contracts.py
python scripts/test_contracts.py
python scripts/test_prompt_delivery.py
python scripts/test_liveliness_contract.py
python -B -m unittest discover -s scripts -p 'test_delivery_integrity.py' -v
python scripts/validate_director_contract.py --report reports/package-acceptance-v3.5.4.json
python -X utf8 C:/Users/dcf/.codex/skills/.system/skill-creator/scripts/quick_validate.py D:/codex工作区/deliverables/acheng-director
```

最终包验收报告显示：

- 132 条运镜目录通过；
- 原始 100 条情绪和扩展 100 条情绪通过；
- 8 套生产示例通过；
- 5 种 H3 模式全部覆盖；
- 23 条独立视频提示词；
- 19 条图像提示词设计；
- 角色四视图资产合同通过；
- `visual_verification` 仍为 `UNVERIFIED`，因为没有声称已生成真实影片、图片或音频。

## 新会话启动顺序

1. 读取本文件。
2. 读取根 `SKILL.md`、`modules/assets/SKILL.md`、`modules/model/SKILL.md`、`references/62-style-anchor.md`、`references/40-action-choreography.md`、`references/70-minimax-h3-compiler.md`。
3. 运行 `python scripts/validate_director_contract.py --report reports/package-acceptance-v3.5.4.json`，确认3.5.4合同通过。
4. 只根据用户的新需求修改；不要回退到 v3.5.1，也不要把已搁置的 v3.6 重新启用。
5. 3.5.4正式包已独立发布；后续修改必须递增版本或重新走发布验收，不覆盖已交付ZIP。

## 不要重复做的事

- 不要重新设计四视图角色资产默认值，当前默认已经是正面全身、背面全身、侧面全身、正脸头肩近景。
- 不要把 STYLE MOTHER 自动强加给没有 `style_lock` 的项目。
- 不要把 H3 timing 变成新的 H3 顶层字段；H3 最终仍保持基础三字段或 Ref2VA 六字段。
- 不要用摘要或折叠替代完整 H3 正文。
- 不要把 `A身材`、`I性格`、`M01`、`同上`、`沿用前段`等内部 shorthand 放入模型提示词。
- 不要修改工作区中与 `deliverables/acheng-director` 无关的脏文件。

## 已知边界

- 风格母版的机器合同、版本和文件哈希可自动检查；最终画风是否统一仍需要生成图组并排人工验收。
- H3 的方向和速度逻辑已经进入提示词合同；真实生成后的动作自然度、冲击力、速度感和物理可信度仍需逐帧人工验收。
- 本包默认不调用付费图像或视频模型，不代表媒体已经生成。

## 交接结论

工具异常影响的是上一会话的执行反馈，不是本项目的生产实现能力。当前 v3.5.4 是最新可交付包，v3.5.3 仅作历史基线；v3.6 已移入“偏离搁置”归档，不得重新启用。
