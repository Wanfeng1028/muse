package dev.stagecue.shared.protocol

import dev.stagecue.shared.model.CueState
import dev.stagecue.shared.oplog.OpLogEntry
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
sealed interface WsMessage {
    val msgId: String
    val sentAtMs: Long
}

@Serializable
@SerialName("hello")
data class Hello(
    override val msgId: String,
    override val sentAtMs: Long,
    val clientId: String,
    val role: ClientRole,
    val clientTimeMs: Long,
    /**
     * 重连时客户端已同步的最大 oplog seq；服务端回放大于该 seq 的条目。
     * null 表示全新客户端，服务端不回放。老客户端不填此字段，解码时取默认值。
     */
    val lastSeenSeq: Long? = null
) : WsMessage

@Serializable
@SerialName("clock_ping")
data class ClockPing(
    override val msgId: String,
    override val sentAtMs: Long,
    val seq: Long,
    val clientTimeMs: Long
) : WsMessage

@Serializable
@SerialName("trigger_cue")
data class TriggerCue(
    override val msgId: String,
    override val sentAtMs: Long,
    val cueId: String,
    val fireAtServerMs: Long? = null
) : WsMessage

@Serializable
@SerialName("arm_cue")
data class ArmCue(
    override val msgId: String,
    override val sentAtMs: Long,
    val cueId: String
) : WsMessage

@Serializable
@SerialName("welcome")
data class Welcome(
    override val msgId: String,
    override val sentAtMs: Long,
    val clientId: String,
    val serverTimeMs: Long
) : WsMessage

@Serializable
@SerialName("clock_pong")
data class ClockPong(
    override val msgId: String,
    override val sentAtMs: Long,
    val seq: Long,
    val clientTimeMs: Long,
    val serverTimeMs: Long
) : WsMessage

@Serializable
@SerialName("cue_fired")
data class CueFired(
    override val msgId: String,
    override val sentAtMs: Long,
    val cueId: String,
    val firedAtServerMs: Long,
    val eventId: String,
    /** 排练模式下触发为 true，执行端应只提示、不驱动真实设备。默认 false 兼容老消息。 */
    val rehearsal: Boolean = false
) : WsMessage

@Serializable
@SerialName("cue_armed")
data class CueArmed(
    override val msgId: String,
    override val sentAtMs: Long,
    val cueId: String
) : WsMessage

@Serializable
@SerialName("set_rehearsal")
data class SetRehearsal(
    override val msgId: String,
    override val sentAtMs: Long,
    val enabled: Boolean
) : WsMessage

@Serializable
@SerialName("rehearsal_changed")
data class RehearsalChanged(
    override val msgId: String,
    override val sentAtMs: Long,
    val enabled: Boolean
) : WsMessage

@Serializable
@SerialName("state_snapshot")
data class StateSnapshot(
    override val msgId: String,
    override val sentAtMs: Long,
    val showId: String,
    val states: Map<String, CueState>,
    val serverTimeMs: Long
) : WsMessage

@Serializable
@SerialName("error")
data class Error(
    override val msgId: String,
    override val sentAtMs: Long,
    val code: String,
    val message: String
) : WsMessage


/**
 * 重连回放：服务端把客户端未同步的 oplog 条目一次性推给它。
 * 客户端只做日志补齐展示，绝不能把回放条目当新事件重新执行（尤其不能重放成 CueFired 去驱动设备）。
 */
@Serializable
@SerialName("oplog_replay")
data class OpLogReplay(
    override val msgId: String,
    override val sentAtMs: Long,
    val entries: List<OpLogEntry>
) : WsMessage
