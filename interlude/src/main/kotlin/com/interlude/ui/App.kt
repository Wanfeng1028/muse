
package com.interlude.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.Canvas
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import com.interlude.dsl.Parser
import com.interlude.dsl.ParseError
import com.interlude.dsl.Story
import com.interlude.dsl.Statement
import com.interlude.dsl.Text
import com.interlude.lint.Validator
import com.interlude.lint.Issue
import com.interlude.lint.Severity
import java.io.File

private val Ink = Color(0xFF1B1712)
private val InkSoft = Color(0xFF26201A)
private val Paper = Color(0xFFE8DCC0)
private val PaperDim = Color(0xFFB9AE93)
private val Vermilion = Color(0xFFC8402A)
private val Amber = Color(0xFFD9A441)
private val Hairline = Color(0xFF3A322A)
private val EdgeGray = Color(0xFF6B6154)

private val Serif = FontFamily.Serif
private val Mono = FontFamily.Monospace

private val scheme = darkColorScheme(
    background = Ink,
    surface = InkSoft,
    onBackground = Paper,
    onSurface = Paper,
    primary = Vermilion,
    onPrimary = Paper,
)

@Composable
fun App() {
    var source by remember { mutableStateOf(loadSample()) }
    var story by remember { mutableStateOf<Story?>(null) }
    var parseError by remember { mutableStateOf<ParseError?>(null) }
    var issues by remember { mutableStateOf<List<Issue>>(emptyList()) }
    var selectedScene by remember { mutableStateOf<String?>(null) }
    var statusLine by remember { mutableStateOf<String?>(null) }

    fun runLint() {
        try {
            val s = Parser(source).parse()
            story = s
            parseError = null
            issues = Validator.validate(s)
            statusLine = if (issues.isEmpty()) "未发现问题" else "发现 ${issues.size} 个问题"
        } catch (e: ParseError) {
            story = null
            parseError = e
            issues = emptyList()
            statusLine = null
        }
    }

    LaunchedEffect(Unit) { runLint() }

    MaterialTheme(colorScheme = scheme) {
        Surface(color = Ink, modifier = Modifier.fillMaxSize()) {
            Column(Modifier.fillMaxSize()) {
                TopBar(
                    onSample = { source = loadSample(); runLint() },
                    onValidate = { runLint() }
                )
                Row(Modifier.fillMaxSize()) {
                    Box(Modifier.fillMaxHeight().weight(0.38f)) {
                        EditorPane(
                            value = source,
                            onChange = { source = it },
                            parseError = parseError
                        )
                    }
                    Box(
                        Modifier.fillMaxHeight().weight(0.62f)
                            .border(1.dp, Hairline)
                    ) {
                        Column(Modifier.fillMaxSize()) {
                            Box(Modifier.weight(0.62f).fillMaxWidth()) {
                                GraphPane(
                                    story = story,
                                    issues = issues,
                                    selected = selectedScene,
                                    onSelect = { selectedScene = it; statusLine = "选中场景 $it" }
                                )
                            }
                            Box(
                                Modifier.weight(0.38f).fillMaxWidth()
                                    .border(1.dp, Hairline)
                                    .background(InkSoft)
                            ) {
                                IssuesPane(issues = issues, onPick = { issue ->
                                    statusLine = "${issue.sceneId ?: "-"}:${issue.line}  ${issue.message}"
                                })
                            }
                        }
                    }
                }
                if (statusLine != null) {
                    Box(
                        Modifier.fillMaxWidth().background(InkSoft)
                            .border(1.dp, Hairline).padding(8.dp)
                    ) {
                        Text(
                            statusLine!!,
                            color = PaperDim,
                            fontFamily = Mono,
                            fontSize = 12.sp
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun TopBar(onSample: () -> Unit, onValidate: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().background(InkSoft)
            .border(1.dp, Hairline)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            "幕间 Interlude · 分支叙事 linter",
            color = Paper,
            fontFamily = Serif,
            fontSize = 18.sp,
            fontWeight = FontWeight.Medium
        )
        Spacer(Modifier.weight(1f))
        Button(
            onClick = onSample,
            colors = ButtonDefaults.buttonColors(
                containerColor = Ink,
                contentColor = Paper
            ),
            shape = RoundedCornerShape(4.dp)
        ) { Text("载入示例", fontFamily = Mono, fontSize = 13.sp) }
        Spacer(Modifier.width(8.dp))
        Button(
            onClick = onValidate,
            colors = ButtonDefaults.buttonColors(
                containerColor = Vermilion,
                contentColor = Paper
            ),
            shape = RoundedCornerShape(4.dp)
        ) { Text("校验", fontFamily = Mono, fontSize = 13.sp) }
    }
}

@Composable
private fun EditorPane(value: String, onChange: (String) -> Unit, parseError: ParseError?) {
    Column(Modifier.fillMaxSize().background(Ink).padding(12.dp)) {
        Text(
            "剧本 DSL",
            color = PaperDim,
            fontFamily = Mono,
            fontSize = 11.sp
        )
        Spacer(Modifier.height(6.dp))
        Box(
            Modifier.fillMaxWidth().weight(1f)
                .background(InkSoft)
                .border(1.dp, Hairline)
                .padding(10.dp)
        ) {
            BasicTextField(
                value = value,
                onValueChange = onChange,
                textStyle = TextStyle(
                    color = Paper,
                    fontFamily = Mono,
                    fontSize = 13.sp
                ),
                cursorBrush = SolidColor(Vermilion),
                modifier = Modifier.fillMaxSize()
            )
        }
        if (parseError != null) {
            Spacer(Modifier.height(6.dp))
            Text(
                "第 ${parseError.line} 行：${parseError.message}",
                color = Vermilion,
                fontFamily = Mono,
                fontSize = 12.sp
            )
        }
    }
}

@Composable
private fun GraphPane(
    story: Story?,
    issues: List<Issue>,
    selected: String?,
    onSelect: (String) -> Unit
) {
    Box(Modifier.fillMaxSize().background(Ink)) {
        Text(
            "分支图",
            color = PaperDim,
            fontFamily = Mono,
            fontSize = 11.sp,
            modifier = Modifier.padding(12.dp)
        )
        if (story == null) {
            Text(
                "解析失败，无法绘制分支图",
                color = Vermilion,
                fontFamily = Mono,
                fontSize = 12.sp,
                modifier = Modifier.padding(12.dp).offset(y = 20.dp)
            )
            return
        }
        val (positions, edges) = remember(story) { GraphLayout.layout(story) }
        val issueByScene = remember(issues) {
            issues.filter { it.sceneId != null }
                .groupBy { it.sceneId!! }
                .mapValues { (_, list) ->
                    when {
                        list.any { it.severity == Severity.ERROR } -> Severity.ERROR
                        list.any { it.severity == Severity.WARNING } -> Severity.WARNING
                        else -> null
                    }
                }
        }
        val sceneById = remember(story) { story.scenes.associateBy { it.id } }

        val hScroll = rememberScrollState()
        val vScroll = rememberScrollState()

        Box(
            Modifier.fillMaxSize().padding(top = 32.dp)
                .horizontalScroll(hScroll).verticalScroll(vScroll)
        ) {
            Canvas(Modifier.size(2400.dp, 1600.dp)) {
                val cardW = 200f
                val cardH = 90f
                // edges first
                for (e in edges) {
                    val from = positions[e.from] ?: continue
                    val to = positions[e.to]
                    val start = Offset(from.x + cardW, from.y + cardH / 2f)
                    if (to == null) {
                        // undefined target: 画一小段虚线红
                        val end = Offset(start.x + 80f, start.y)
                        drawLine(
                            color = Vermilion,
                            start = start,
                            end = end,
                            strokeWidth = 2f
                        )
                        continue
                    }
                    val end = Offset(to.x, to.y + cardH / 2f)
                    drawLine(
                        color = EdgeGray,
                        start = start,
                        end = end,
                        strokeWidth = 2f
                    )
                    // arrowhead
                    val dx = end.x - start.x
                    val dy = end.y - start.y
                    val len = kotlin.math.sqrt(dx * dx + dy * dy).coerceAtLeast(1f)
                    val ux = dx / len
                    val uy = dy / len
                    val ah = 8f
                    val left = Offset(end.x - ux * ah - uy * ah * 0.6f, end.y - uy * ah + ux * ah * 0.6f)
                    val right = Offset(end.x - ux * ah + uy * ah * 0.6f, end.y - uy * ah - ux * ah * 0.6f)
                    drawLine(EdgeGray, end, left, 2f)
                    drawLine(EdgeGray, end, right, 2f)
                }
                // cards
                for (scene in sceneById.values) {
                    val pos = positions[scene.id] ?: continue
                    val sev = issueByScene[scene.id]
                    val border = when (sev) {
                        Severity.ERROR -> Vermilion
                        Severity.WARNING -> Amber
                        else -> if (scene.id == selected) Vermilion else Hairline
                    }
                    val strokeW = when (sev) {
                        Severity.ERROR -> 3f
                        Severity.WARNING -> 3f
                        else -> if (scene.id == selected) 2f else 1f
                    }
                    drawRoundRect(
                        color = Paper,
                        topLeft = Offset(pos.x, pos.y),
                        size = androidx.compose.ui.geometry.Size(cardW, cardH),
                        cornerRadius = androidx.compose.ui.geometry.CornerRadius(8f, 8f)
                    )
                    drawRoundRect(
                        color = border,
                        topLeft = Offset(pos.x, pos.y),
                        size = androidx.compose.ui.geometry.Size(cardW, cardH),
                        cornerRadius = androidx.compose.ui.geometry.CornerRadius(8f, 8f),
                        style = Stroke(width = strokeW)
                    )
                }
            }
            // 覆盖文本层（用 Compose 文本，独立于 Canvas）
            Box(Modifier.size(2400.dp, 1600.dp)) {
                for (scene in sceneById.values) {
                    val pos = positions[scene.id] ?: continue
                    Column(
                        Modifier
                            .offset(x = (pos.x / 1f).dp, y = (pos.y / 1f).dp)
                            .size(200.dp, 90.dp)
                            .clickable { onSelect(scene.id) }
                            .padding(8.dp)
                    ) {
                        Text(
                            scene.id,
                            color = Ink,
                            fontFamily = Mono,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(Modifier.height(4.dp))
                        val firstText = scene.statements
                            .filterIsInstance<Text>()
                            .firstOrNull()?.value ?: ""
                        Text(
                            firstText,
                            color = Ink,
                            fontFamily = Serif,
                            fontSize = 12.sp,
                            maxLines = 3
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun IssuesPane(issues: List<Issue>, onPick: (Issue) -> Unit) {
    Column(Modifier.fillMaxSize().padding(12.dp)) {
        Text(
            "问题清单",
            color = PaperDim,
            fontFamily = Mono,
            fontSize = 11.sp
        )
        Spacer(Modifier.height(8.dp))
        if (issues.isEmpty()) {
            Text(
                "未发现问题",
                color = PaperDim,
                fontFamily = Mono,
                fontSize = 12.sp
            )
            return
        }
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            for (issue in issues) {
                val isErr = issue.severity == Severity.ERROR
                Row(
                    Modifier.fillMaxWidth()
                        .padding(vertical = 4.dp)
                        .clickable { onPick(issue) },
                    verticalAlignment = Alignment.Top
                ) {
                    Box(
                        Modifier
                            .border(1.dp, if (isErr) Vermilion else Amber)
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    ) {
                        Text(
                            if (isErr) "ERROR" else "WARN",
                            color = if (isErr) Vermilion else Amber,
                            fontFamily = Mono,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Spacer(Modifier.width(8.dp))
                    Column(Modifier.weight(1f)) {
                        Text(
                            issue.message,
                            color = Paper,
                            fontFamily = Serif,
                            fontSize = 13.sp
                        )
                        Text(
                            "${issue.sceneId ?: "-"}:${issue.line}",
                            color = PaperDim,
                            fontFamily = Mono,
                            fontSize = 11.sp
                        )
                    }
                }
            }
        }
    }
}

private fun loadSample(): String {
    val candidates = listOf(
        File("src/main/resources/scripts/sample.interlude"),
        File("resources/scripts/sample.interlude")
    )
    for (f in candidates) {
        if (f.exists()) return f.readText()
    }
    return ""
}

fun runApp() {
    application {
        Window(
            onCloseRequest = { exitApplication() },
            title = "幕间 Interlude"
        ) {
            App()
        }
    }
}
