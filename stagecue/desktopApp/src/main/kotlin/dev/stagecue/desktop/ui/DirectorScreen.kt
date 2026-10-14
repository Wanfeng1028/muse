package dev.stagecue.desktop.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Divider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.stagecue.desktop.audio.AudioPlayer
import dev.stagecue.desktop.sync.ConnState
import dev.stagecue.desktop.sync.DirectorClient
import dev.stagecue.desktop.theme.MonoStyle
import dev.stagecue.desktop.theme.StageColors
import dev.stagecue.shared.model.Cue
import dev.stagecue.shared.model.CueType
import dev.stagecue.shared.protocol.WsJson
import kotlinx.coroutines.delay
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.doubleOrNull

@Composable
fun DirectorScreen() {
    val scope = rememberCoroutineScope()
    val client = remember { DirectorClient() }
    val connState by client.connState.collectAsState()
    val cues by client.cues.collectAsState()
    val states by client.states.collectAsState()
    val logLines by client.log.collectAsState()
    val serverTimeMs by client.serverTimeMs.collectAsState()

    var selectedCueId by remember { mutableStateOf<String?>(null) }
    val rehearsal by client.rehearsalMode.collectAsState()

    // 首次进入连接
    LaunchedEffect(Unit) {
        client.connect("127.0.0.1", 8080)
    }

    // 音频播放挂钩
    DisposableEffect(client) {
        AudioPlayer.logger = { msg -> client.log(msg) }
        client.onCueFired = { cue ->
            if (cue.type == CueType.AUDIO) {
                val payloadText = cue.payload
                if (!payloadText.isNullOrBlank()) {
                    try {
                        val obj = WsJson.json.parseToJsonElement(payloadText).jsonObject
                        val path = obj["path"]?.jsonPrimitive?.content
                        val volume = obj["volume"]?.jsonPrimitive?.doubleOrNull ?: 0.8
                        if (path.isNullOrBlank()) {
                            client.log("音频 cue 缺少 path")
                        } else {
                            AudioPlayer.play(path, fadeInMs = 300L)
                        }
                    } catch (e: Throwable) {
                        client.log("音频 payload 解析失败")
                    }
                }
            }
        }
        onDispose {
            client.disconnect()
            AudioPlayer.stop()
        }
    }

    // 服务器时钟显示
    var displayClock by remember { mutableStateOf("--:--:--") }
    LaunchedEffect(serverTimeMs, connState) {
        while (true) {
            val base = serverTimeMs
            if (base != null && connState == ConnState.CONNECTED) {
                // 用本地流逝补齐
                val anchor = System.currentTimeMillis()
                while (true) {
                    val elapsed = System.currentTimeMillis() - anchor
                    displayClock = formatHms(base + elapsed)
                    delay(250)
                }
            } else {
                displayClock = "--:--:--"
                delay(500)
            }
        }
    }

    val currentCueId = cues.firstOrNull { states[it.id] == dev.stagecue.shared.model.CueState.FIRING }?.id
        ?: cues.firstOrNull { states[it.id] == dev.stagecue.shared.model.CueState.ARMED }?.id

    val firedCount = cues.count { states[it.id] == dev.stagecue.shared.model.CueState.FIRING }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(StageColors.Charcoal)
    ) {
        TopStatusBar(
            showName = "舞台剧 · 未命名",
            connState = connState,
            clockText = displayClock,
            rehearsal = rehearsal,
        )
        Divider(color = StageColors.DimGold, thickness = 1.dp)
        Row(modifier = Modifier.weight(1f).fillMaxWidth()) {
            // 左侧 cue 列表
            CueListPanel(
                modifier = Modifier.weight(1f).fillMaxSize(),
                cues = cues,
                states = states,
                currentCueId = currentCueId,
                selectedCueId = selectedCueId,
                onSelect = { selectedCueId = it },
                onArm = { client.armCue(it) }
            )
            Divider(
                color = StageColors.DimGold,
                thickness = 1.dp,
                modifier = Modifier.width(1.dp).fillMaxSize()
            )
            EventLogPanel(
                modifier = Modifier.width(320.dp).fillMaxSize(),
                lines = logLines
            )
        }
        Divider(color = StageColors.DimGold, thickness = 1.dp)
        TransportBar(
            rehearsal = rehearsal,
            onToggleRehearsal = { client.setRehearsal(!rehearsal) },
            onArm = {
                val id = selectedCueId ?: currentCueId
                if (id != null) client.armCue(id) else client.log("未选中 cue，无法预备")
            },
            onTrigger = {
                val id = selectedCueId ?: currentCueId
                if (id != null) client.triggerCue(id) else client.log("未选中 cue，无法触发")
            },
            firedCount = firedCount
        )
    }
}

@Composable
private fun TopStatusBar(
    showName: String,
    connState: ConnState,
    clockText: String,
    rehearsal: Boolean
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(56.dp)
            .background(StageColors.Panel)
            .padding(horizontal = 16.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = showName,
            color = StageColors.Spotlight,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold
        )
        Spacer(Modifier.width(24.dp))
        ConnectionIndicator(connState)
        if (rehearsal) {
            Spacer(Modifier.width(12.dp))
            Box(
                modifier = Modifier
                    .background(StageColors.Curtain)
                    .padding(horizontal = 10.dp, vertical = 4.dp)
            ) {
                Text(
                    text = "排练",
                    color = StageColors.Chalk,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        }
        Spacer(Modifier.weight(1f))
        Text(
            text = clockText,
            color = StageColors.Spotlight,
            fontFamily = FontFamily.Monospace,
            fontSize = 28.sp,
            fontWeight = FontWeight.Medium
        )
    }
}

@Composable
private fun ConnectionIndicator(connState: ConnState) {
    val connected = connState == ConnState.CONNECTED
    val color = if (connected) StageColors.Connected else StageColors.Disconnected
    val label = if (connected) "已连接" else "未连接"
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .width(10.dp)
                .height(10.dp)
                .background(color)
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = label,
            color = if (connected) StageColors.Chalk else StageColors.Disconnected,
            fontSize = 14.sp
        )
    }
}

private fun formatHms(ms: Long): String {
    val totalSec = (ms / 1000) % 86400
    val h = totalSec / 3600
    val m = (totalSec % 3600) / 60
    val s = totalSec % 60
    return "%02d:%02d:%02d".format(h, m, s)
}
