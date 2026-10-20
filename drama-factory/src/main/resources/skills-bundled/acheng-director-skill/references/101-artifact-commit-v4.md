# 101｜Artifact Commit v4 产物提交合同

编排器不生成导演内容。模块或宿主先在临时路径写出产物，orchestrator_commit.py 再执行一次受控提交：读取文件、计算 SHA-256、检查输入版本、原子写入目标路径、更新产物索引和状态游标。

每条索引至少包含 artifact_id、node_id、path、sha256、status、accepted、input_revision、output_revision。output_revision 是本次产物内容哈希；它不是 production.json 的副本。

同一 artifact_id + input_revision + sha256 的重复提交是幂等回执，不产生第二份文件。相同身份但内容不同必须拒绝。输入版本不是当前 production_revision 时必须拒绝，防止过期模块覆盖新真值。目标已存在且哈希不同也必须拒绝。

当宿主报告 partial 或达到单次输出上限时，提交器保存 current_cursor 和 continuation_required=true，节点保持可续写；不得把截断正文标为 accepted=true。完整产物提交后才推进到下一个节点。

H3 产物还有一道持久化质量门：声明 Ref2VA 六字段的 `.h3.txt` 或 `.h3` 文件，`detailed_description` 少于该 Segment 的 `h3_min_words` 时不能以 `complete`、`COMMITTED` 或 `accepted=true` 提交；必须以 `partial` 保存游标并续写同一 Segment。该门禁防止宿主把短摘要误报为完整 H3。

在 `interactive_segment` 模式中，完整产物提交后也要停在当前交互回合，等待用户发送 `继续`、`1` 或 `下一段`；不能因为还有后续节点就把多个 Segment 拼进同一轮。`autonomous_file_batch` 模式可以在宿主确实提供工作区写入和连续工具循环时逐段提交独立文件，聊天直接展示逐段简洁上传操作卡、manifest、状态和阻塞项，长正文留文件；工具循环、执行时长或权限不足时必须保存已提交产物并暂停，不能声称后台无限运行。

4.3.6 的新 H3 complete 提交必须通过[114 联合门](114-reference-binding-delivery-v4.3.6.md)：正文、上传卡、绑定快照、素材、格式合同和回执保存为同一 bundle。旧 COMMITTED 记录可读取，但不能冒充新版联合验收。partial 保存游标，不走伪通过路径。
