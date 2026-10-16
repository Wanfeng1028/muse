package com.interlude.replay

/**
 * 对局事件时间戳：ISO-8601 字符串，如 "2026-10-16T20:01:00+08:00"。
 * 本模块不做时间解析，只透传展示。
 */
data class Alternative(val label: String, val target: String)

/**
 * 对局事件密封接口。所有事件都带一个 [at] 时间戳字符串（透传展示，不解析）。
 */
sealed interface SessionEvent {
    val at: String
}

/**
 * 对局开始事件，由顶层 "session" 对象合成，恒为解析结果列表的第一个元素。
 *
 * @param sessionId 对局 ID，来自 session.id
 * @param scriptFile 剧本文件名，来自 session.script
 * @param playerCount 玩家数，来自 session.players，缺省 1
 * @param at 对局开始时间，来自 session.startedAt
 */
data class SessionStart(
    val sessionId: String,
    val scriptFile: String,
    val playerCount: Int,
    override val at: String,
) : SessionEvent

/**
 * 进入场景事件。
 *
 * @param sceneId 进入的场景 ID
 * @param at 事件时间戳
 */
data class SceneEnter(val sceneId: String, override val at: String) : SessionEvent

/**
 * 做出抉择事件。
 *
 * @param sceneId 抉择发生的场景 ID
 * @param label 玩家选择的选项文本
 * @param target 玩家选择的目标场景 ID
 * @param alternatives 当时没选的路（label + target 列表），为空表示不是抉择点
 * @param at 事件时间戳
 */
data class ChoiceMade(
    val sceneId: String,
    val label: String,
    val target: String,
    val alternatives: List<Alternative>,
    override val at: String,
) : SessionEvent

/**
 * 投票事件。
 *
 * @param voter 投票者
 * @param target 被投目标
 * @param round 轮次
 * @param at 事件时间戳
 */
data class VoteCast(val voter: String, val target: String, val round: Int, override val at: String) : SessionEvent

/**
 * 出局事件。
 *
 * @param player 出局玩家
 * @param reason 出局原因
 * @param round 轮次
 * @param at 事件时间戳
 */
data class Elimination(val player: String, val reason: String, val round: Int, override val at: String) : SessionEvent

/**
 * 人工标注的关键时刻事件。
 *
 * @param note 标注文本
 * @param sceneId 关联场景 ID，可为 null 或缺失
 * @param at 事件时间戳
 */
data class KeyMoment(val note: String, val sceneId: String?, override val at: String) : SessionEvent

/**
 * 对局结束事件。
 *
 * @param outcome 结局描述
 * @param winner 胜者，可为 null 或缺失
 * @param at 事件时间戳
 */
data class SessionEnd(val outcome: String, val winner: String?, override val at: String) : SessionEvent
