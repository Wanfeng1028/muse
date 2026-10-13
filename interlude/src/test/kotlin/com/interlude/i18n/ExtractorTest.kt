
package com.interlude.i18n

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ExtractorTest {

    private fun story() = Parser(
        """
        scene start:
          text: "hello {name}"
          choice "go now" -> finish
          choice "stay" -> start
        scene finish:
          text: "bye"
          end
        """.trimIndent()
    ).parse()

    @Test
    fun `extract produces correct keys and count`() {
        val entries = Extractor.extract(story())
        assertEquals(4, entries.size)
        assertEquals("start.text.0", entries[0].key)
        assertEquals("text", entries[0].kind)
        assertEquals("start", entries[0].sceneId)
        assertEquals("hello {name}", entries[0].source)
        assertEquals("start.choice.0", entries[1].key)
        assertEquals("choice", entries[1].kind)
        assertEquals("go now", entries[1].source)
        assertEquals("start.choice.1", entries[2].key)
        assertEquals("stay", entries[2].source)
        assertEquals("finish.text.0", entries[3].key)
        assertEquals("bye", entries[3].source)
    }

    @Test
    fun `apply substitutes translations and preserves placeholders`() {
        val translations = mapOf(
            "start.text.0" to "你好 {name}",
            "start.choice.0" to "出发",
            "finish.text.0" to "再见"
        )
        val result = Extractor.apply(story(), translations)
        val start = result.scenes.first { it.id == "start" }
        val textStmt = start.statements.filterIsInstance<com.interlude.dsl.Text>().first()
        assertEquals("你好 {name}", textStmt.value)
        val choiceStmt = start.statements.filterIsInstance<com.interlude.dsl.Choice>().first()
        assertEquals("出发", choiceStmt.label)
    }

    @Test
    fun `apply reinserts missing placeholders`() {
        val translations = mapOf("start.text.0" to "你好")
        val result = Extractor.apply(story(), translations)
        val start = result.scenes.first { it.id == "start" }
        val textStmt = start.statements.filterIsInstance<com.interlude.dsl.Text>().first()
        assertTrue(textStmt.value.contains("{name}"))
    }

    @Test
    fun `apply keeps source when key missing`() {
        val result = Extractor.apply(story(), emptyMap())
        val start = result.scenes.first { it.id == "start" }
        val textStmt = start.statements.filterIsInstance<com.interlude.dsl.Text>().first()
        assertEquals("hello {name}", textStmt.value)
        val choiceStmt = start.statements.filterIsInstance<com.interlude.dsl.Choice>().first()
        assertEquals("go now", choiceStmt.label)
    }
}
