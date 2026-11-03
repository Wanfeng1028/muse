package dev.stagecue.server

import dev.stagecue.server.db.SettingsStore
import dev.stagecue.shared.protocol.*
import dev.stagecue.shared.sync.EventDeduper
import dev.stagecue.shared.oplog.OpLogEntry
import dev.stagecue.shared.oplog.OpLogStore
import dev.stagecue.shared.model.MonitorState
import dev.stagecue.shared.model.Show
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

class SyncHub(
    private val clock: () -> Long = { System.currentTimeMillis() },
    private val deduper: EventDeduper = EventDeduper(),
    private val opLog: OpLogStore? = null,
    private val settings: SettingsStore? = null,
) {
    private val clients = ConcurrentHashMap<String, ClientRole>()

    /** 最近一次成功触发（CueFired）的 cue id；去重命中的 Error 路径不记录。 */
    private var lastFiredCueId: String? = null

    /** 最近一次成功触发的时间戳（毫秒）。 */
    private var lastFiredAtMs: Long = 0L

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
        lastFiredCueId = msg.cueId
        lastFiredAtMs = clock()
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

    /**
     * 重连回放：返回 seq 大于 [lastSeenSeq] 的 oplog 条目（按 seq 升序）。
     * lastSeenSeq 为 null 表示全新客户端，不回放（避免首次连接被全量历史淹没）。
     * opLog 未配置时返回空列表。
     */
    fun missedOps(lastSeenSeq: Long?): List<OpLogEntry> {
        if (lastSeenSeq == null) return emptyList()
        return opLog?.readAll().orEmpty().filter { it.seq > lastSeenSeq }.sortedBy { it.seq }
    }

    /** 返回当前连接的客户端角色；未注册时为 null。 */
    fun roleOf(clientId: String): ClientRole? = clients[clientId]

    /**
     * 写操作鉴权。MONITOR 角色发送 TriggerCue/ArmCue/SetRehearsal 时返回 FORBIDDEN Error；
     * 其余（含 role 为 null 的遗留行为）一律返回 null 表示放行。
     */
    fun authorizeWrite(role: ClientRole?, msg: WsMessage): Error? {
        if (role != ClientRole.MONITOR) return null
        val action = when (msg) {
            is TriggerCue -> "trigger_cue"
            is ArmCue -> "arm_cue"
            is SetRehearsal -> "set_rehearsal"
            else -> return null
        }
        return Error(
            msgId = UUID.randomUUID().toString(),
            sentAtMs = clock(),
            code = "FORBIDDEN",
            message = "role MONITOR is read-only; $action requires DIRECTOR",
        )
    }

    /**
     * 构造返听屏只读快照。
     *
     * current = 最近触发 cue（按 id 查找，找不到或从未触发为 null）；
     * next = order 大于 current.order 的最小者（current 为 null 时取 order 最小者，已是最后一个为 null）；
     * remainingMs = current 非空且 durationMs > 0 时按 lastFiredAtMs 计算剩余，否则 null。
     */
    fun monitorSnapshot(show: Show, nowMs: Long = clock()): MonitorState {
        val sorted = show.cues.sortedBy { it.order }
        val current = lastFiredCueId?.let { id -> sorted.firstOrNull { it.id == id } }
        val next = if (current == null) {
            sorted.firstOrNull()
        } else {
            sorted.firstOrNull { it.order > current.order }
        }
        val remainingMs = if (current != null && current.durationMs > 0) {
            maxOf(0L, current.durationMs - (nowMs - lastFiredAtMs))
        } else {
            null
        }
        return MonitorState(
            current = current,
            next = next,
            remainingMs = remainingMs,
            rehearsal = rehearsalMode,
            serverTimeMs = nowMs,
        )
    }
}
