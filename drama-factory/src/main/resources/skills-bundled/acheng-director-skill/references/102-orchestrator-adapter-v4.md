# 102｜Orchestrator Adapter v4 宿主适配合同

宿主可以提供以下可选接口，编排层不要求宿主采用特定代理、后台任务或模型：

plan(request, production)
execute(node, context)
validate(node, artifact)
commit(node, artifact)
schedule_next(state)
pause(reason)
resume(state)

plan 只返回能力触发图；execute 可以调用现有七个专业模块或外部执行能力，但不得改变模块字段所有权；validate 返回结构/合同证据；commit 必须遵守 101 号合同；schedule_next 只读取状态和计划；pause 仅用于缺少用户决策、不可替代素材、权限或外部能力；resume 从最后一个已提交产物和游标继续。

适配器没有实现时，4.0 仍可输出计划、状态和阻塞回执；不得把计划伪装成已执行。编排器不调用付费图像、视频或音频模型，不创建第二个 H3 编译器，也不直接写 production.json 的生产字段。
