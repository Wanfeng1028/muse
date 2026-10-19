# v3.0 审核流（2026-10-19）

## 概述
这次给剧本和分镜加了审核环节，剧本走两级，分镜走一级。
审核记录单独存一张表，谁在什么时候做了什么、写了什么意见、对应哪个版本，都能查。
Run 执行前会检查剧本有没有过审，没过就暂停等着。
单用户部署不硬拦自审，但会标记出来，前端也会提示。
具体设计写在 docs/REVIEW_FLOW.md，里面包含 v3.0a 自审死锁修正的说明。

## 状态机
剧本两级：DRAFT 到 PENDING_L1，再到 PENDING_L2，最后 APPROVED 或 REJECTED。
分镜一级：DRAFT 到 PENDING，然后 APPROVED 或 REJECTED。
状态只能按这个顺序走，跳级或者往回走会被接口挡掉，返回 409。

## 执行门
Run 跑到 VIDEO 步骤之前，会先看剧本是不是 APPROVED。
不是的话这个 run 置为 PAUSED，停下来等审核结果。
过了审再继续跑。

## API
提交、一审、二审、驳回、查历史挂在 /api/projects/{projectId}/episodes/{episodeId}/review/ 下面，分别是 submit、l1、l2、reject、history。
审核队列在 /api/projects/{projectId}/review/queue。
非法流转返回 409，跨项目访问返回 403，kind 对不上返回 404。

## 数据
Flyway 脚本 V18__review_flow.sql 建了 review_item 和 review_history 两张表。
episode 被删除时，相关审核记录跟着级联删掉。

## 前端
审核队列页是 review.html，用的 Tabler 1.6.1。
自审的情况会用 ReviewDetailResponse.selfReviewed 标记出来，页面上给醒目提示。

## 测试
新增 ReviewServiceTest 29 例、ReviewApiTest 9 例、RunExecutorReviewGateTest 3 例。
另外修了 ScriptSplitterServiceDeepTest 里预先损坏的反射构造，12 例，是 Toonflow 移植时落下的。

## 状态
代码和测试已经合进仓库。
还差真实冒烟，流程是提交、一审、二审、过审、Run 放行，再加截图验收。
这些都过了再对照 docs/dod-v3.0.md 发版。