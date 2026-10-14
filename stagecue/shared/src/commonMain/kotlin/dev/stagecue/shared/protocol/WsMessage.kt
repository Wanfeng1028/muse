package dev.stagecue.shared.protocol

import dev.stagecue.shared.model.CueState
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
    val clientTimeMs: Long
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
