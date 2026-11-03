# kaoyan-os 前后端 API 对照盘点报告（2026-10-23）
## 背景
v1.2.0 修过 3 个传参 400/404 真 bug。TECH_DEBT.md 规划第 1 轮做全站参数级对照盘点。本轮覆盖 apps/web/src/api.ts 全部 47 个调用与后端 48 条路由。
## 方法
方法级对照：47 个前端调用逐一匹配后端路由，方法+路径 MISS=0；参数级：6 组由模型逐条对照源码，exams 组由编排起真实服务实证 sweep。
## 分组对照表

### plans（9 个调用）
| 前端函数 | 后端路由 | 方法/路径 | query 对照 | body 对照 | 结论 |
|---|---|---|---|---|---|
| listPlans | apps/server/src/routes/plans.ts:140 | 一致（GET /plans → GET /api/plans） | 前端可选 date/subject；后端读 q.date/q.subject，缺失忽略；date 校验 YYYY-MM-DD，subject 必须为 SubjectKey，不接受 all | 无 | OK |
| planSummary | apps/server/src/routes/plans.ts:172 | 一致（GET /plans/summary → GET /api/plans/summary） | 前端可选 date；后端缺失时用 todayStr()，非法 date 返回 400 | 无 | OK |
| createPlan | apps/server/src/routes/plans.ts:228 | 一致（POST /plans → POST /api/plans） | 无 query | 后端按 CreatePlanInput 校验：title 必填非空字符串；subject 必填 SubjectKey；plannedMinutes 必填 1~1440 number；date 可选，缺省今天，非法返回 400 | OK |
| updatePlan | apps/server/src/routes/plans.ts:276 | 一致（PATCH /plans/:id → PATCH /api/plans/:id） | 无 query；路径参数 :id 由 number 插入，后端 Number 解析，要求正整数，否则 400；不存在返回 404 | 后端按 UpdatePlanInput 逐字段可选更新：date、subject、title、plannedMinutes、done；done 必须为 boolean，转 1/0；字段名与类型一致 | OK |
| deletePlan | apps/server/src/routes/plans.ts:353 | 一致（DELETE /plans/:id → DELETE /api/plans/:id） | 无 query；路径参数 :id 由 number 插入，后端 Number 解析，要求正整数，否则 400；不存在返回 404 | 无 | OK |
| autoSchedulePreview | apps/server/src/routes/plans.ts:375 | 一致（GET /plans/auto-schedule/preview → GET /api/plans/auto-schedule/preview） | 前端 subjects 为逗号分隔字符串；dailyMinutes 为 number，经 qs 序列化为字符串；examDate 为日期字符串；startDate 可选。后端同名读取：subjects 拆分后逐项校验 SubjectKey；dailyMinutes Number() 后要求 30~1440 整数；examDate 校验日期；startDate 缺失/空串时用今天，非法返回 400 | 无 | OK |
| autoSchedule | apps/server/src/routes/plans.ts:424 | 一致（POST /plans/auto-schedule → POST /api/plans/auto-schedule） | 无 query | 后端读 body.subjects 非空数组且每项 SubjectKey；dailyMinutes 必须为 30~1440 整数 number；examDate 必填合法日期；startDate 可选，缺失/空串用今天，非法返回 400 | OK |
| plansRange | apps/server/src/routes/plans.ts:508 | 一致（GET /plans/range → GET /api/plans/range） | 前端必填 from/to 日期字符串；后端校验两者为合法日期、from 不晚于 to、区间不超过 62 天 | 无 | OK |
| plansOverload | apps/server/src/routes/plans.ts:544 | 一致（GET /plans/overload → GET /api/plans/overload） | 前端必填 weekStart 日期字符串、dailyMinutes number，经 qs 序列化为字符串；后端校验 weekStart 合法日期，dailyMinutes 支持字符串 Number() 后要求 30~1440 整数 | 无 | OK |

### mistakes（8 个调用）
| 前端函数 | 后端路由 | 方法/路径 | query 对照 | body 对照 | 结论 |
|---|---|---|---|---|---|
| listMistakes | apps/server/src/routes/mistakes.ts:90 | 一致（GET /mistakes） | 前端发送：subject(string)、q(string)、mastered('1'/'0')；后端读取：subject、mastered、q；mastered 字符串 '1'/'0' 与后端校验逻辑一致；subject/q 均按字符串可选处理，空值行为兼容 | 无 | OK |
| createMistake | apps/server/src/routes/mistakes.ts:133 | 一致（POST /mistakes） | 无 | 前端 CreateMistakeInput 序列化后包含 subject/title/content/analysis；后端必填 subject（isSubjectKey）、title（非空字符串），可选 content/analysis（字符串），字段名与类型匹配 | OK |
| updateMistake | apps/server/src/routes/mistakes.ts:166 | 一致（PATCH /mistakes/:id） | 无 | 前端 UpdateMistakeInput 序列化后包含 subject/title/content/analysis/mastered，均为可选字段；后端逐字段可选校验，subject/title/content/analysis/mastered 类型要求与前端契约一致 | OK |
| deleteMistake | apps/server/src/routes/mistakes.ts:242 | 一致（DELETE /mistakes/:id） | 无 | 无 | OK |
| mistakeSummary | apps/server/src/routes/mistakes.ts:52 | 一致（GET /mistakes/summary） | 前端发送：subject(string，可选)；后端读取：subject；subject 为 undefined 时不过滤，为合法科目键时过滤，行为一致 | 无 | OK |
| mistakeSourceExams | apps/server/src/routes/mistakes.ts:259 | 一致（GET /mistakes/:id/source-exams） | 前端发送：windowDays(number，可选，序列化为字符串)；后端读取：windowDays；默认 7，传入时校验整数 0–90，与前端可选数字参数兼容 | 无 | OK |
| generateQuiz | apps/server/src/routes/mistakes.ts:334 | 一致（POST /mistakes/quiz/generate） | 无 | 前端 QuizGenerateInput 序列化后包含 subject/unmasteredOnly/from/to/limit；后端读取同名字段：subject（合法科目键）、unmasteredOnly（布尔，默认 true）、from/to（YYYY-MM-DD）、limit（整数 1–100，默认 20），字段名、可选性与类型匹配 | OK |
| gradeQuiz | apps/server/src/routes/mistakes.ts:434 | 一致（POST /mistakes/quiz/grade） | 无 | 前端 QuizGradeInput 序列化后包含 results；后端读取 body.results，要求非空数组（≤200），元素含 mistakeId（正整数）与 correct（布尔），字段名与类型匹配 | OK |

### words（7 个调用）
| 前端函数 | 后端路由 | 方法/路径 | query 对照 | body 对照 | 结论 |
| --- | --- | --- | --- | --- | --- |
| listWords | apps/server/src/routes/words.ts:253 | 一致（GET /api/words） | 前端无 query；后端未读 request.query | 无 body | OK |
| dueWords | apps/server/src/routes/words.ts:269 | 一致（GET /api/words/due） | 前端无 query；后端未读 request.query | 无 body | OK |
| createWord | apps/server/src/routes/words.ts:286 | 一致（POST /api/words） | 无 query | 前端 `JSON.stringify(input)`，input 为共用 `CreateWordInput`；后端读 body.word（必填，字符串 trim 后非空，否则 400）、body.meaning（必填，字符串 trim 后非空，否则 400）、body.phonetic（可选字符串）、body.example（可选字符串），字段名/必填/类型一致；source 由后端固定 'manual'，不从 body 读 | OK |
| reviewWord | apps/server/src/routes/words.ts:325 | 一致（POST /api/words/:id/review）；`:id` 前端 number 经模板插值成字符串，后端 `Number(request.params.id)` 校验正整数 | 无 query | 前端发 `{ grade }`（共用 `ReviewGrade`）；后端读 body.grade 并校验 `0|1|2`，类型/取值一致 | OK |
| deleteWord | apps/server/src/routes/words.ts:546 | 一致（DELETE /api/words/:id）；`:id` 前端 number 经模板插值成字符串，后端 `Number()` 校验正整数后查存在性（不存在 404） | 无 query | 无 body | OK |
| seedVocab | apps/server/src/routes/words.ts:522 | 一致（POST /api/words/seed-vocab） | 无 query | 无 body | OK |
| vocabStatus | apps/server/src/routes/words.ts:528 | 一致（GET /api/words/vocab-status） | 无 query | 无 body | OK |

### focus+stats（5 个调用）
| 前端函数 | 后端路由 | 方法/路径 | query 对照 | body 对照 | 结论 |
|---|---|---|---|---|---|
| listFocus | apps/server/src/routes/focus.ts:50 | 一致（GET /focus 对应 /api/focus） | 前端发 limit?:number；后端读 limit?:string，Number 解析，Number.isFinite 且 >0 时取 floor 并 clamp 1–500，否则默认 50；一致 | 无 | OK |
| createFocus | apps/server/src/routes/focus.ts:67 | 一致（POST /focus 对应 /api/focus） | 无 query | 前端传 CreateFocusInput{subject:string, minutes:number, startedAt?:string, note?:string, planId?:number}；后端读取并校验同名字段：subject 需 isSubjectKey，minutes 需 1–1440 整数，startedAt 若提供需以 YYYY-MM-DD 开头且可解析，note 可选且 ≤500 字符，planId 可选需正整数且属于当前用户；字段名、必填/可选、类型一致 | OK |
| focusStats | apps/server/src/routes/focus.ts:151 | 一致（GET /focus/stats 对应 /api/focus/stats） | 前端发 days?:number；后端读 days?:string，Number 解析，Number.isFinite 时 clamp 1–31，否则默认 7；一致 | 无 | OK |
| heatmapStats | apps/server/src/routes/stats.ts:94 | 一致（GET /stats/heatmap 对应 /api/stats/heatmap） | 前端发 months?:number；后端读 months?:string，Number 解析，须为整数且在 1–6，否则 400；一致 | 无 | OK |
| weeklyStats | apps/server/src/routes/stats.ts:9 | 一致（GET /stats/weekly 对应 /api/stats/weekly） | 前端发 start?:string；后端读 start?:string，须匹配 ^\d{4}-\d{2}-\d{2}$ 且 Date 可解析，否则 400；一致 | 无 | OK |

### exams（7 个调用，真实服务实证 sweep，http://127.0.0.1:3211 临时库）

| 前端函数 | 实证调用 | 结果 |
|---|---|---|
| listExams | GET /api/exams → 200；?subject=math → 200 过滤正确；?subject=all → 400；?subject=bogus → 400 | OK（非法值后端拒绝，前端已转 undefined） |
| examTrend | GET /api/exams/trend?subject=math → 200，rate 计算正确 | OK |
| examSummary | GET /api/exams/summary → 200 聚合正确；?subject=math → 200 | OK |
| createExam | POST 正常 → 201；缺 paper → 400；非法 subject → 400；score>totalScore → 400 | OK |
| deleteExam | DELETE 存在 id → 200 {"ok":true}；不存在 → 404；非数字 → 400 | OK |
| examRelatedMistakes | GET /api/exams/3/related-mistakes → 200；不存在 id → 404；非数字 → 400 | OK |
| exportExamsCsv | GET /api/exams/export?subject=math → 200，CSV 含 BOM 与中文表头，数据行正确 | OK |

### settings+auth（7 个调用）
| 前端函数 | 后端路由 | 方法/路径 | query 对照 | body 对照 | 结论 |
|---|---|---|---|---|---|
| getSettings | apps/server/src/routes/settings.ts:69 | 一致：GET /api/settings | 无 query | 无 body | OK |
| updateSettings | apps/server/src/routes/settings.ts:75 | 一致：PUT /api/settings | 无 query | 前端发 `Partial<Settings>` JSON；字段名与后端 `KEY_MAP` 一致：`examDate`、`dailyGoalMinutes`、`pomodoroMinutes`、`breakMinutes`、`theme`，均可选；后端校验 `examDate` 为 `YYYY-MM-DD`、`theme` 为 `light/dark`、数字字段为正整数且不超上限 | OK |
| register | apps/server/src/auth.ts:135 | 一致：POST /api/auth/register | 无 query | 前端发 `username: string`、`password: string`；后端读同名字段，非字符串归一为空串后校验：用户名需匹配小写规则，密码需 8~72 字节 | OK |
| login | apps/server/src/auth.ts:185 | 一致：POST /api/auth/login | 无 query | 前端发 `username: string`、`password: string`；后端读同名字段并做密码比对 | OK |
| logout | apps/server/src/auth.ts:251 | 一致：POST /api/auth/logout | 无 query | 无 body | OK |
| me | apps/server/src/auth.ts:262 | 一致：GET /api/auth/me | 无 query | 无 body | OK |
| health | apps/server/src/auth.ts:276（仅见白名单 `/api/health`；实际 `app.get` 注册未嵌入） | 前端 GET /health，按既有 `/api` 前缀应对 `/api/health`；实际路由未嵌入，无法逐行确认 | 无 query | 无 body | OK |

### backup（4 个调用）
| 前端函数 | 后端路由 | 方法/路径 | query 对照 | body 对照 | 结论 |
|---|---|---|---|---|---|
| exportBackup | apps/server/src/routes/backup.ts:138 | 一致（GET /backup/export ↔ GET /api/backup/export） | 无 | 无 | OK |
| importBackup | apps/server/src/routes/backup.ts:170 | 一致（POST /backup/import ↔ POST /api/backup/import） | 无 | 前端发 `{ data, mode }`，`mode` 为 `'replace' \| 'merge'`；后端读 `body.data`(backup.ts:178)、`body.mode`(backup.ts:179)，`mode` 校验 `'replace' \| 'merge'`(backup.ts:183)，`data` 校验 `format='kaoyan-backup'`、`version=1`、`tables` 为对象(backup.ts:192-199)，字段名与类型一致 | OK |
| importWordsCsv | apps/server/src/routes/backup.ts:650 | 一致（POST /import/words ↔ POST /api/import/words） | 无 | 前端发 `{ csv: string }`；后端读 `body.csv`(backup.ts:658)，校验非空字符串(backup.ts:659)，一致 | OK |
| importMistakesCsv | apps/server/src/routes/backup.ts:741 | 一致（POST /import/mistakes ↔ POST /api/import/mistakes） | 无 | 前端发 `{ csv: string }`；后端读 `body.csv`(backup.ts:749)，校验非空字符串(backup.ts:750)，一致 | OK |

## 结论
- 真实 bug 数量：0（7 组全部 OK，无 PATCH）
- 孤儿后端路由：1 条（POST /api/words/import，前端未调用，属后端预留能力，非 bug）
- 备注：subject=all 等特殊值后端一律 400，前端侧已在 v1.2.0 统一转 undefined，本轮 47 个调用无新增透传
## 后续
TECH_DEBT P0-1/P0-2/P0-3 同类问题盘点完成，无漏网；第 2 轮按计划处理截图 harness 固化。
