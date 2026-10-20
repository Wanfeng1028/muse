package com.interlude.replay

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ReplayMarkdownWarningsSectionTest {

    @Test
    fun warningsSectionRendered() {
        val report = ReplayReport(
            sessionId = "s1",
            scriptFile = "s.interlude",
            startedAt = "2026-10-16T20:00:00+08:00",
            endedAt = null,
            timeline = listOf(
                SessionStart("s1", "s.interlude", 2, "2026-10-16T20:00:00+08:00")
            ),
            decisionPoints = emptyList(),
            voteRounds = emptyList(),
            playerStats = emptyList(),
            keyMoments = emptyList(),
            outcome = null,
            winner = null,
            warnings = listOf(
                "事件 events[2] 引用的场景 'xxx' 在剧本中不存在",
                "第二条警告"
            ),
        )

        val md = ReplayMarkdown.render(report)

        assertTrue(
            md.contains("## 数据问题"),
            "存在警告时输出应包含数据问题节标题"
        )
        assertTrue(
            md.contains("- 事件 events[2] 引用的场景 'xxx' 在剧本中不存在\n"),
            "第一条警告应以 - 开头独占一行"
        )
        assertTrue(
            md.contains("- 第二条警告\n"),
            "第二条警告应以 - 开头独占一行"
        )
    }

    @Test
    fun emptyWarningsNoSection() {
        val report = ReplayReport(
            sessionId = "s1",
            scriptFile = "s.interlude",
            startedAt = "2026-10-16T20:00:00+08:00",
            endedAt = null,
            timeline = listOf(
                SessionStart("s1", "s.interlude", 2, "2026-10-16T20:00:00+08:00")
            ),
            decisionPoints = emptyList(),
            voteRounds = emptyList(),
            playerStats = emptyList(),
            keyMoments = emptyList(),
            outcome = null,
            winner = null,
            warnings = emptyList(),
        )

        val md = ReplayMarkdown.render(report)

        assertFalse(
            md.contains("## 数据问题"),
            "无警告时不应输出数据问题节"
        )
    }

    @Test
    fun analyzerProducesSceneWarning() {
        val story = Parser(
            """
            scene a:
              text: "起点"
            """.trimIndent()
        ).parse()

        val log = """
        {"session": {"id":"t1","script":"s.interlude","players":2,"startedAt":"2026-10-16T20:00:00+08:00"},"events": [{"type":"scene","scene":"ghost","at":"2026-10-16T20:00:05+08:00"}]}
        """.trimIndent()

        val events = SessionLog.parse(log)
        val report = ReplayAnalyzer.buildReport(story, events)

        assertEquals(
            1,
            report.warnings.size,
            "仅有一个 ghost 场景引用缺失，应恰好产生一条警告"
        )
        assertTrue(
            report.warnings[0].contains("ghost"),
            "警告文本应包含缺失的场景名 ghost"
        )

        val md = ReplayMarkdown.render(report)
        assertTrue(
            md.contains("## 数据问题"),
            "存在场景缺失警告时渲染结果应包含数据问题节"
        )
        assertTrue(
            md.contains("ghost"),
            "渲染结果应包含缺失的场景名 ghost"
        )
    }
}