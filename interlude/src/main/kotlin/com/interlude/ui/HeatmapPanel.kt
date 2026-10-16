package com.interlude.ui

// 色值与 App.kt 保持一致
import androidx.compose.foundation.background
import androidx.compose.foundation.border

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.interlude.replay.HeatmapAnalyzer
import com.interlude.replay.HeatmapReport
import com.interlude.replay.HeatmapLoader
import com.interlude.replay.HeatmapLoadStatus
import com.interlude.replay.HotPath
import com.interlude.replay.SessionLog

import java.io.File

private val Ink = Color(0xFF1B1712)
private val InkSoft = Color(0xFF26201A)
private val Paper = Color(0xFFE8DCC0)
private val PaperDim = Color(0xFFB9AE93)
private val Vermilion = Color(0xFFC8402A)
private val Amber = Color(0xFFD9A441)
private val Hairline = Color(0xFF3A322A)

private val Serif = FontFamily.Serif
private val Mono = FontFamily.Monospace

@Composable
fun HeatmapPanel() {
    var dirText by remember { mutableStateOf("src/main/resources/replays") }
    var report by remember { mutableStateOf<HeatmapReport?>(null) }
    var failedFiles by remember { mutableStateOf<List<String>>(emptyList()) }
    var dirMissing by remember { mutableStateOf(false) }
    var noJson by remember { mutableStateOf(false) }

    fun runAnalyze() {
        val loaded = HeatmapLoader.load(File(dirText))
        dirMissing = loaded.status == HeatmapLoadStatus.DIR_MISSING
        noJson = loaded.status == HeatmapLoadStatus.NO_JSON
        failedFiles = loaded.failedFiles
        report = loaded.report
    }


    Column(
        Modifier.fillMaxSize().background(Ink).padding(12.dp)
    ) {
        Text(
            "热力分析",
            color = PaperDim,
            fontFamily = Mono,
            fontSize = 11.sp
        )
        Spacer(Modifier.height(8.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.weight(1f)
                    .background(InkSoft)
                    .border(1.dp, Hairline)
                    .padding(horizontal = 8.dp, vertical = 6.dp)
            ) {
                BasicTextField(
                    value = dirText,
                    onValueChange = { dirText = it },
                    textStyle = TextStyle(
                        color = Paper,
                        fontFamily = Mono,
                        fontSize = 12.sp
                    ),
                    cursorBrush = SolidColor(Vermilion),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
            }
            Spacer(Modifier.width(8.dp))
            Button(
                onClick = { runAnalyze() },
                colors = ButtonDefaults.buttonColors(
                    containerColor = Vermilion,
                    contentColor = Paper
                ),
                shape = androidx.compose.foundation.shape.RoundedCornerShape(4.dp)
            ) {
                Text("分析", fontFamily = Mono, fontSize = 13.sp)
            }
        }
        Spacer(Modifier.height(10.dp))

        if (dirMissing) {
            Text(
                "目录下没有可分析的对局日志",
                color = PaperDim,
                fontFamily = Mono,
                fontSize = 12.sp
            )
            return@Column
        }
        if (noJson) {
            Text(
                "目录下没有可分析的对局日志",
                color = PaperDim,
                fontFamily = Mono,
                fontSize = 12.sp
            )
            return@Column
        }

        val r = report
        if (r == null) {
            if (failedFiles.isNotEmpty()) {
                Text(
                    "全部日志解析失败",
                    color = Vermilion,
                    fontFamily = Mono,
                    fontSize = 12.sp
                )
                Spacer(Modifier.height(6.dp))
                for (name in failedFiles.take(3)) {
                    Text(
                        "· $name",
                        color = Vermilion,
                        fontFamily = Mono,
                        fontSize = 12.sp
                    )
                }
            } else {
                Text(
                    "尚未分析，输入目录后点击「分析」",
                    color = PaperDim,
                    fontFamily = Mono,
                    fontSize = 12.sp
                )
            }
            return@Column
        }

        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState())
        ) {
            // a. 总览行
            Text(
                "对局 ${r.sessionCount} · 选项 ${r.totalChoices} · 节点 ${r.nodes.size} · 解析失败 ${failedFiles.size} 个",
                color = PaperDim,
                fontFamily = Mono,
                fontSize = 12.sp
            )
            if (failedFiles.isNotEmpty()) {
                Spacer(Modifier.height(4.dp))
                for (name in failedFiles.take(3)) {
                    Text(
                        "· $name",
                        color = Vermilion,
                        fontFamily = Mono,
                        fontSize = 12.sp
                    )
                }
            }

            Spacer(Modifier.height(14.dp))
            Text(
                "Top 热门路径",
                color = Paper,
                fontFamily = Serif,
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium
            )
            Spacer(Modifier.height(6.dp))
            if (r.topPaths.isEmpty()) {
                Text(
                    "暂无路径数据",
                    color = PaperDim,
                    fontFamily = Mono,
                    fontSize = 12.sp
                )
            } else {
                for ((idx, hp) in r.topPaths.withIndex()) {
                    Text(
                        "路径 #${idx + 1} ×${hp.count}  ${formatPath(hp)}",
                        color = Paper,
                        fontFamily = Mono,
                        fontSize = 12.sp
                    )
                    Spacer(Modifier.height(4.dp))
                }
            }

            Spacer(Modifier.height(14.dp))
            Text(
                "节点热力",
                color = Paper,
                fontFamily = Serif,
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium
            )
            Spacer(Modifier.height(6.dp))
            if (r.nodes.isEmpty()) {
                Text(
                    "暂无节点数据",
                    color = PaperDim,
                    fontFamily = Mono,
                    fontSize = 12.sp
                )
            } else {
                val maxVisits = r.nodes.maxOf { it.visits }.coerceAtLeast(1)
                Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                    Text("nodeId", color = PaperDim, fontFamily = Mono, fontSize = 11.sp, modifier = Modifier.weight(1.6f))
                    Text("scene", color = PaperDim, fontFamily = Mono, fontSize = 11.sp, modifier = Modifier.weight(1.0f))
                    Text("label", color = PaperDim, fontFamily = Mono, fontSize = 11.sp, modifier = Modifier.weight(1.4f))
                    Text("visits", color = PaperDim, fontFamily = Mono, fontSize = 11.sp, modifier = Modifier.weight(0.6f))
                    Text("drops", color = PaperDim, fontFamily = Mono, fontSize = 11.sp, modifier = Modifier.weight(0.6f))
                    Text("drop%", color = PaperDim, fontFamily = Mono, fontSize = 11.sp, modifier = Modifier.weight(0.7f))
                    Spacer(Modifier.width(12.dp))
                }
                for (n in r.nodes) {
                    val ratio = n.visits.toFloat() / maxVisits.toFloat()
                    val rowColor = when {
                        ratio >= 0.999f -> Vermilion
                        ratio >= 0.5f -> Amber
                        else -> Paper
                    }
                    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                        Text(
                            n.nodeId,
                            color = rowColor,
                            fontFamily = Mono,
                            fontSize = 12.sp,
                            modifier = Modifier.weight(1.6f)
                        )
                        Text(
                            n.sceneId,
                            color = rowColor,
                            fontFamily = Mono,
                            fontSize = 12.sp,
                            modifier = Modifier.weight(1.0f)
                        )
                        Text(
                            if (n.label.isEmpty()) "(空)" else n.label,
                            color = rowColor,
                            fontFamily = Serif,
                            fontSize = 12.sp,
                            modifier = Modifier.weight(1.4f)
                        )
                        Text(
                            n.visits.toString(),
                            color = rowColor,
                            fontFamily = Mono,
                            fontSize = 12.sp,
                            modifier = Modifier.weight(0.6f)
                        )
                        Text(
                            n.drops.toString(),
                            color = rowColor,
                            fontFamily = Mono,
                            fontSize = 12.sp,
                            modifier = Modifier.weight(0.6f)
                        )
                        Text(
                            "${(n.dropRate * 100).toInt()}%",
                            color = rowColor,
                            fontFamily = Mono,
                            fontSize = 12.sp,
                            modifier = Modifier.weight(0.7f)
                        )
                        Spacer(Modifier.width(12.dp))
                        if (n.dropRate >= 0.5) {
                            Text(
                                "!",
                                color = Vermilion,
                                fontFamily = Mono,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }
                }
            }

            Spacer(Modifier.height(14.dp))
            Text(
                "流失点",
                color = Paper,
                fontFamily = Serif,
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium
            )
            Spacer(Modifier.height(6.dp))
            if (r.churnPoints.isEmpty()) {
                Text(
                    "未发现显著流失点",
                    color = PaperDim,
                    fontFamily = Mono,
                    fontSize = 12.sp
                )
            } else {
                for (cp in r.churnPoints) {
                    Text(
                        "${cp.sceneId}::${if (cp.label.isEmpty()) "(空)" else cp.label} 流失率 ${(cp.dropRate * 100).toInt()}%（${cp.drops}/${cp.visits}）",
                        color = Vermilion,
                        fontFamily = Mono,
                        fontSize = 12.sp
                    )
                    Spacer(Modifier.height(4.dp))
                }
            }
        }
    }
}

private fun formatPath(hp: HotPath): String {
    val joined = hp.path.joinToString(" → ") { id ->
        if (id.length > 24) id.substring(0, 24) + "…" else id
    }
    return joined
}





