package dev.stagecue.shared.model

import kotlinx.serialization.Serializable

/**
 * 返听屏只读状态快照。
 *
 * @param current 当前正在触发的 cue，从未触发或已丢失时为 null。
 * @param next 下一待触发的 cue（按 order 升序），无后续时为 null。
 * @param remainingMs 当前 cue 剩余倒计时毫秒；current 为 null 或 durationMs <= 0 时为 null。
 * @param rehearsal 是否处于排练模式。
 * @param serverTimeMs 服务端生成该快照的时间戳。
 */
@Serializable
data class MonitorState(
    val current: Cue?,
    val next: Cue?,
    val remainingMs: Long?,
    val rehearsal: Boolean,
    val serverTimeMs: Long,
)
