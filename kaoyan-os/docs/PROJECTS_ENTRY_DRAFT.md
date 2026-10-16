# PROJECTS.md 同步草稿：kaoyan-os

## 后续计划

- 周报视图：已交付（v1.4.0，2026-10-16）。

## 里程碑记录

- v1.4.0（2026-10-16）
  - 后端：packages/shared 的 WeeklyStats 新增 2 个字段——focusMinutesByDay（7 个数，周一..周日每日专注分钟）、currentStreak（连续打卡天数，口径与热力图一致：今日有专注则从今日往前数，否则从昨日往前数）；GET /api/stats/weekly 既有参数与字段语义不变（start=YYYY-MM-DD 缺省本周一，非法值 400）。
  - 前端：apps/web/src/pages/Weekly.tsx（/weekly 路由、导航「周报」不变）升级，新增 5 个视觉模块——顶部概览卡（本周专注、计划完成率、连续打卡、新增错题、模考场次）、7 天专注分钟条形、计划完成率 SVG 圆环 + 四科专注条、「和上周比一比」（专注分钟/完成率/错题/模考与上周的增减，大白话）、单词卡；深色模式跟随 data-theme；视觉延续 v1.3.0 热力图体系（蓝五档：浅 #c9e2fb→#2f74e0 / 深 #1e4068→#5b9bf3），未引入新配色与新字体。
  - 测试与构建：apps/server/tests/weekly.test.ts 新增 5 例（focusMinutesByDay 长度 7 且总和等于 focusMinutes、周三补记录对应下标 +25、今天补专注后 streak≥1、-30 天孤立记录不影响 streak、start=20261012 返回 400）；服务端 vitest 55/55 全绿；前端 tsc --noEmit 零错；vite build 成功。
  - 截图 2 张：docs/screenshots/light-weekly.png（浅色）、docs/screenshots/dark-weekly.png（深色），真实演示数据、已亲眼验收（布局撑满视口、无错字）。
  - 参数备注：里程碑原计划参数为 week=YYYY-Www，实际保留了已有的 start=YYYY-MM-DD（前端已在使用且有测试覆盖，避免破坏性变更）。
