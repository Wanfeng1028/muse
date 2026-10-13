package dev.stagecue.desktop.sync

import dev.stagecue.shared.model.Cue
import dev.stagecue.shared.model.CueState
import dev.stagecue.shared.model.Show
import dev.stagecue.shared.protocol.ArmCue
import dev.stagecue.shared.protocol.ClientRole
import dev.stagecue.shared.protocol.ClockPing
import dev.stagecue.shared.protocol.ClockPong
import dev.stagecue.shared.protocol.CueArmed
import dev.stagecue.shared.protocol.CueFired
import dev.stagecue.shared.protocol.Error
import dev.stagecue.shared.protocol.Hello
import dev.stagecue.shared.protocol.StateSnapshot
import dev.stagecue.shared.protocol.TriggerCue
import dev.stagecue.shared.protocol.Welcome
import dev.stagecue.shared.protocol.WsJson
import dev.stagecue.shared.protocol.WsMessage
import dev.stagecue.shared.sync.ClockEstimator
import io.ktor.client.HttpClient
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.client.plugins.websocket.webSocket
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.websocket.Frame
import io.ktor.websocket.readText
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.util.UUID

/** 连接状态 */
enum class ConnState { DISCONNECTED, CONNECTING, CONNECTED }

/**
 * 导演台与同步服务之间的 WebSocket 客户端。
 *
 * 负责：
 *  - 建立到 /ws 的 WebSocket 连接，发送 Hello 握手
 *  - 通过 ClockPing/ClockPong 做 NTP 式时钟同步
 *  - 连接成功后通过 HTTP GET /api/show 拉取完整 Show（含 cue 列表）
 *  - 接收服务端广播的 CueFired/CueArmed 事件并更新本地状态
 */
class DirectorClient {
    var onCueFired: ((Cue) -> Unit)? = null

    private val _cues = MutableStateFlow<List<Cue>>(emptyList())
    val cues: StateFlow<List<Cue>> = _cues

    private val _states = MutableStateFlow<Map<String, CueState>>(emptyMap())
    val states: StateFlow<Map<String, CueState>> = _states

    private val _connState = MutableStateFlow(ConnState.DISCONNECTED)
    val connState: StateFlow<ConnState> = _connState

    private val _log = MutableStateFlow<List<String>>(emptyList())
    val log: StateFlow<List<String>> = _log

    private val _serverTimeMs = MutableStateFlow<Long?>(null)
    val serverTimeMs: StateFlow<Long?> = _serverTimeMs

    private val client = HttpClient { install(WebSockets) }
    private val scope = CoroutineScope(Dispatchers.IO + Job())
    private val clockEstimator = ClockEstimator()
    private var pingSeq = 0L
    private var pingJob: Job? = null
    private var session: io.ktor.client.plugins.websocket.DefaultClientWebSocketSession? = null

    fun log(msg: String) {
        _log.value = (_log.value + msg).takeLast(200)
    }

    fun connect(host: String, port: Int) {
        if (_connState.value == ConnState.CONNECTING || _connState.value == ConnState.CONNECTED) return
        _connState.value = ConnState.CONNECTING
        val clientId = "director-${UUID.randomUUID().toString().take(8)}"
        scope.launch {
            try {
                client.webSocket("ws://$host:$port/ws") {
                    session = this
                    _connState.value = ConnState.CONNECTED
                    log("已连接同步服务 $host:$port")
                    val now = System.currentTimeMillis()
                    send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(),
                        Hello(UUID.randomUUID().toString(), now, clientId, ClientRole.DIRECTOR, now))))
                    loadShow(host, port)
                    startPing()
                    for (frame in incoming) {
                        if (frame is Frame.Text) handle(frame.readText())
                    }
                }
            } catch (t: Throwable) {
                if (scope.isActive) log("连接断开：${t.message}")
            } finally {
                session = null
                _connState.value = ConnState.DISCONNECTED
                pingJob?.cancel()
            }
        }
    }

    fun disconnect() {
        scope.launch {
            try { client.close() } catch (t: Throwable) { /* ignore */ }
            _connState.value = ConnState.DISCONNECTED
        }
    }

    fun triggerCue(cueId: String) {
        val s = session
        if (s == null) {
            log("未连接，无法触发 cue")
            return
        }
        scope.launch {
            val now = System.currentTimeMillis()
            try {
                s.send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(),
                    TriggerCue(UUID.randomUUID().toString(), now, cueId))))
                log("已发送触发 cue $cueId")
            } catch (t: Throwable) {
                log("触发失败：${t.message}")
            }
        }
    }

    fun armCue(cueId: String) {
        val s = session
        if (s == null) {
            log("未连接，无法预备 cue")
            return
        }
        scope.launch {
            val now = System.currentTimeMillis()
            try {
                s.send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(),
                    ArmCue(UUID.randomUUID().toString(), now, cueId))))
                log("已发送预备 cue $cueId")
            } catch (t: Throwable) {
                log("预备失败：${t.message}")
            }
        }
    }

    private suspend fun loadShow(host: String, port: Int) {
        try {
            val body = client.get("http://$host:$port/api/show").bodyAsText()
            val show = WsJson.json.decodeFromString(Show.serializer(), body)
            _cues.value = show.cues
            _states.value = show.cues.associate { it.id to it.state }
            log("已载入 ${show.cues.size} 条 cue")
        } catch (t: Throwable) {
            log("载入 cue 列表失败：${t.message}")
        }
    }

    private fun startPing() {
        pingJob?.cancel()
        pingJob = scope.launch {
            while (isActive) {
                delay(5_000)
                val s = session ?: break
                try {
                    val t1 = System.currentTimeMillis()
                    s.send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(),
                        ClockPing(UUID.randomUUID().toString(), t1, ++pingSeq, t1))))
                } catch (t: Throwable) {
                    break
                }
            }
        }
    }

    private fun handle(text: String) {
        val msg = try {
            WsJson.json.decodeFromString(WsMessage.serializer(), text)
        } catch (t: Throwable) {
            log("无法解析消息：${t.message}")
            return
        }
        when (msg) {
            is Welcome -> {
                _serverTimeMs.value = msg.serverTimeMs
                log("握手成功 clientId=${msg.clientId}")
            }
            is ClockPong -> {
                val t3 = System.currentTimeMillis()
                clockEstimator.addSample(msg.clientTimeMs, msg.sentAtMs, msg.serverTimeMs, t3)
                _serverTimeMs.value = clockEstimator.serverNowMs(t3)
            }
            is CueFired -> {
                _states.value = _states.value + (msg.cueId to CueState.FIRING)
                val cue = _cues.value.firstOrNull { it.id == msg.cueId }
                if (cue != null) {
                    log("cue 触发 ${cue.name}")
                    onCueFired?.invoke(cue)
                } else {
                    log("未知 cueId=${msg.cueId}")
                }
            }
            is CueArmed -> {
                _states.value = _states.value + (msg.cueId to CueState.ARMED)
                log("cue 预备 ${msg.cueId}")
            }
            is StateSnapshot -> {
                _states.value = msg.states
            }
            is Error -> {
                log("服务端错误 ${msg.code}：${msg.message}")
            }
            else -> { /* Hello/ClockPing/TriggerCue/ArmCue 不会发给导演台 */ }
        }
    }
}
