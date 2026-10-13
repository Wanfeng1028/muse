package dev.stagecue.server

import dev.stagecue.shared.protocol.*
import dev.stagecue.shared.sync.EventDeduper
import dev.stagecue.shared.oplog.OpLogStore
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

class SyncHub(
    private val clock: () -> Long = { System.currentTimeMillis() },
    private val deduper: EventDeduper = EventDeduper(),
    private val opLog: OpLogStore? = null,
) {
    private val clients = ConcurrentHashMap<String, ClientRole>()

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
        opLog?.append("CUE_FIRED", msg.cueId, "eventId=$eventId")
        return CueFired(
            msgId = UUID.randomUUID().toString(),
            sentAtMs = now,
            cueId = msg.cueId,
            firedAtServerMs = now,
            eventId = eventId,
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
