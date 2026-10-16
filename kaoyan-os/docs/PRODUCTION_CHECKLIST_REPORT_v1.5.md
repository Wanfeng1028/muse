# v1.5 发版对照报告

版本：v1.5
日期：2026-10-16
范围：考研核心 500 词词库扩充（数据、后端、前端、测试、构建、真实冒烟）

## 1. 可靠性

[通过] 自动化测试 73/73 全绿，本轮新增 apps/server/tests/vocab-seed.test.ts 共 18 例，覆盖四个数据文件的条数、跨文件去重、字段完整、无 redacted、seed-vocab 幂等、memory_tip 透出、vocab-status 计数、validateVocabEntry 校验等场景。
[通过] seed-vocab 先逐条校验再写入，任一条非法即 400 返回 { error, errors: [{ file, index, message }] }，不做部分写入；word 已存在则跳过，二次调用 imported=0、skippedExisting=500，幂等总数不变。
[通过] DB 迁移做了 words 表 memory_tip 列的建表 SQL，并对老库用 PRAGMA table_info 检查后 ALTER TABLE 迁移。
[通过] 健康检查沿用已有 /api/health，本轮没有改动。
[未通过] 失败注入测试本轮没有做（例如写库中途报错、磁盘写满、校验通过后写入失败等场景），已记排期到下一轮补。

## 2. 可观测性

[通过] 沿用 Fastify 默认日志，本轮没有新增日志、指标或链路相关代码。

## 3. 数据

[通过] 备份恢复沿用 v1.1.0 的机制，本轮没有改动。
[不适用] 敏感数据不适用，本地词库内容为公开考研词汇，不含敏感信息。
[通过] 配置与密钥分离沿用已有做法，本轮没有新增密钥或配置项。

## 4. 部署运维

[通过] Dockerfile 已有，本轮 vite build 成功产出的 dist 产物可直接挂载运行。
[不适用] 滚动更新不适用，本项目是单机本地应用，不涉及多实例滚动发布。
[通过] 运维手册沿用已有内容，本轮没有新增运维步骤。

## 5. 安全

[通过] seed-vocab 对每条词逐条校验，非法数据直接 400 并返回 file/index/message 明细，不会把脏数据写进库。
[不适用] 鉴权限流不适用，本项目为本地单用户使用，没有对外暴露的多用户入口。

## 6. 可维护

[通过] API 契约在报告里写清：POST /api/words/seed-vocab 播种 500 词（幂等，source='core500'，返回 imported/skippedExisting/skippedInvalid/errors）；GET /api/words/vocab-status 返回 { total, mastered, pending }，只统计 core500，mastered = srs_state.repetitions > 0；packages/shared 的 Word 接口新增可选字段 memory_tip。
[未通过] CHANGELOG 待编排者统一更新，本轮先标待更新。
[通过] 技术债记一笔：旧 seed/words-500.json 已无人引用，建议下一轮删除或归档。

## 7. 周期机制

[未通过] 故障演练本轮没有做，已记排期到下一轮补。
[通过] 真实数据验证用了完整 500 词，本地起 Fastify 挂载 web/dist 冒烟，seed-vocab 返回 { imported: 500, skippedExisting: 0, skippedInvalid: 0, errors: [] }，vocab-status 计数正确，对 8 个词调 review grade=2 后 mastered=8。

## 8. 前端与视觉验收

[通过] 新增 /vocab「词库浏览」页，导航项排在"单词 SRS"之后，包含词库状态卡（总数/已掌握/待掌握 + 进度条 + "导入 500 词库"按钮）和浏览卡（搜索框、掌握情况筛选、20 条/页分页，表格列为单词/音标/释义/记忆法/状态/操作，"标记已掌握"调已有 reviewWord grade=2 接口）。
[通过] 浅色与深色主题跟随 <html data-theme>，无新增全局样式。
[通过] 浅色、深色各 1 张真实截图，均为 500 词真实数据、8 个已掌握；编排者亲眼检查布局撑满视口、无异常空白、无错字、无重复条目。
[通过] 视觉验收发现"状态/操作"列"已掌握"折行的小 bug，已修复并重新截图确认。
[通过] 交互冒烟正常：搜索 abnormal 得到 1 条、筛选未掌握为 20 条/页共 25 页、翻页正常、标记已掌握后 vocab-status 从 8 变 9，全程无页面报错。
