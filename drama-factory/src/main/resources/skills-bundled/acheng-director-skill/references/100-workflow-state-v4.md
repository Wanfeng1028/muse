# 100｜Workflow State v4 薄编排状态合同

workflow_state.json 是一次运行的控制平面，不是第二份生产真值。它只记录 run_id、request_id、execution_mode、current_phase、current_cursor、production_revision、节点状态、重试次数、blocked、unresolved、证据和已提交产物索引。

它不得复制角色正文、剧情事实、ShotSpec、资产提示词、H3 正文、STYLE_MOTHER 合同或 combat timing 事实。恢复时重新读取生产文件和产物索引，不从状态文件重建生产数据。

状态写入必须是 UTF-8、禁止 NaN 的原子替换。production_revision 由当前 production.json 的规范化内容计算；当生产真值变化时，旧计划的提交必须被拒绝。current_cursor 用于长输出续写，可包含 node_id、segment_id、offset 和宿主自定义 token/frame 游标，但不包含生产正文。

`execution_mode` 只能是 `interactive_segment` 或 `autonomous_file_batch`。数字 `1`（默认/推荐）映射到 `autonomous_file_batch`：每个 Segment 写成独立 artifact，聊天展示逐段简洁上传操作卡、文件清单和验收状态，不重复长正文；数字 `2` 映射到 `interactive_segment`：每轮最多提交一个完整 Segment。恢复时沿用已保存的模式，不重新询问，也不得在两种模式之间静默切换。

状态机：PLANNED → RUNNING → PAUSED/COMPLETED/FAILED。只有 pause() 或不可替代阻塞才能进入 PAUSED；恢复从最后一个 COMMITTED 产物开始，不回退已提交文件，不覆盖 3.5.4 包。
