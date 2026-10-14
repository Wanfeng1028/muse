package dev.stagecue.server

import dev.stagecue.server.db.SettingsStore
import dev.stagecue.shared.protocol.*
import dev.stagecue.shared.sync.EventDeduper
import dev.stagecue.shared.oplog.OpLogStore
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

class SyncHub(
    private val clock: () -> Long = { System.currentTimeMillis() },
    private val deduper: EventDeduper = EventDeduper(),
    private val opLog: OpLogStore? = null,
    private val settings: SettingsStore? = null,
) {
    private val clients = ConcurrentHashMap<String, ClientRole>()

    /** 当前是否为排练模式（持久化在 settings 表，重启不丢失；无 settings 时恒为 false） */
    val rehearsalMode: Boolean
        get() = settings?.getBoolean("rehearsal", false) ?: false

    /**
     * 切换排练模式并持久化；调用方负责把返回的 RehearsalChanged 广播给所有客户端。
     * 排练模式下触发的 cue 会在 CueFired.rehearsal 打标，执行端应只提示、不驱动真实设备。
     */
    fun setRehearsal(enabled: Boolean): RehearsalChanged {
        settings?.set("rehearsal", enabled.toString())
        opLog?.append("REHEARSAL_MODE", "-", "enabled=$enabled")
        return RehearsalChanged(
            msgId = UUID.randomUUID().toString(),
            sentAtMs = clock(),
            enabled = enabled,
        )
    }

    fun handleConnect(clientId: String, role: ClientRole): Welcome {
        require(clientId.isNotBlank()) { "clientId must not be blank" }
        clients[clientId] = role
        val now = clock()
        return Welcome(
            msgId = UUID.randomUUID().toString(),
            sentAtMs = now,
            clientId = clientId,
            serverTimeMs = now,
        )
    }

    fun handleClockPing(msg: ClockPing): ClockPong {
        val now = clock()
        return ClockPong(
            msgId = UUID.randomUUID().toString(),
            sentAtMs = now,
            seq = msg.seq,
            clientTimeMs = msg.clientTimeMs,
            serverTimeMs = now,
        )
    }

    fun handleTriggerCue(msg: TriggerCue): WsMessage {
        val eventId = msg.msgId
        val now = clock()
        if (!deduper.isNew(eventId)) {
            return Error(
                msgId = UUID.randomUUID().toString(),
                sentAtMs = now,
                code = "DUPLICATE_EVENT",
                message = "eventId=$eventId already processed",
            )
        }
        val rehearsal = rehearsalMode
        opLog?.append("CUE_FIRED", msg.cueId, "eventId=$eventId rehearsal=$rehearsal")
        return CueFired(
            msgId = UUID.randomUUID().toString(),
            sentAtMs = now,
            cueId = msg.cueId,
            firedAtServerMs = now,
            eventId = eventId,
            rehearsal = rehearsal,
        )
    }

    fun handleArmCue(msg: ArmCue): CueArmed {
        val now = clock()
        return CueArmed(
            msgId = UUID.randomUUID().toString(),
            sentAtMs = now,
            cueId = msg.cueId,
        )
    }

    fun handleUnknown(msg: WsMessage): Error {
        val now = clock()
        return Error(
            msgId = UUID.randomUUID().toString(),
            sentAtMs = now,
            code = "UNKNOWN_MESSAGE",
            message = "Unsupported message type: ${msg::class.simpleName}",
        )
    }
}
