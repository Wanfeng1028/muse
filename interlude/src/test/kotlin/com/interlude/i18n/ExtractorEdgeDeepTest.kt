package com.interlude.i18n

import com.interlude.dsl.Choice
import com.interlude.dsl.End
import com.interlude.dsl.Jump
import com.interlude.dsl.Scene
import com.interlude.dsl.SetVar
import com.interlude.dsl.Story
import com.interlude.dsl.Text
import com.interlude.dsl.VarRef
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class ExtractorEdgeDeepTest {

    // 事实来源：extractScene 中 textIndex 每个 scene 从 0 独立计数，key="${scene.id}.text.$textIndex"
    @Test
    fun extractMultiSceneResetsTextIndex() {
        val story = Story(
            listOf(
                Scene("s1", 1, listOf(Text(2, "a"), Text(3, "b"))),
                Scene("s2", 4, listOf(Text(5, "c"), Text(6, "d")))
            )
        )
        val entries = Extractor.extract(story)
        assertEquals(4, entries.size)
        assertEquals("s1.text.0", entries[0].key)
        assertEquals("s1", entries[0].sceneId)
        assertEquals("s1.text.1", entries[1].key)
        assertEquals("s2.text.0", entries[2].key)
        assertEquals("s2", entries[2].sceneId)
        assertEquals("s2.text.1", entries[3].key)
    }

    // 事实来源：textIndex 与 choiceIndex 分开自增，交错时各自独立计数
    @Test
    fun extractTextAndChoiceIndexIndependent() {
        val story = Story(
            listOf(
                Scene(
                    "s1", 1,
                    listOf(
                        Text(2, "t0"),
                        Choice(3, "c0", "s2", null),
                        Text(4, "t1"),
                        Choice(5, "c1", "s2", null)
                    )
                )
            )
        )
        val entries = Extractor.extract(story)
        assertEquals(4, entries.size)
        assertEquals("s1.text.0", entries[0].key)
        assertEquals("s1.choice.0", entries[1].key)
        assertEquals("s1.text.1", entries[2].key)
        assertEquals("s1.choice.1", entries[3].key)
    }

    // 事实来源：when 分支的 else -> {} 使 SetVar/Jump/End 不产生条目
    @Test
    fun extractSkipsNonTextNonChoiceStatements() {
        val story = Story(
            listOf(
                Scene(
                    "s1", 1,
                    listOf(
                        SetVar(2, "x", VarRef("y")),
                        Jump(3, "s2", null),
                        End(4)
                    )
                )
            )
        )
        val entries = Extractor.extract(story)
        assertEquals(0, entries.size)
    }

    // 事实来源：applyScene 的 Choice 分支命中时 st.copy(label = preservePlaceholders(...))
    @Test
    fun applyReplacesChoiceLabel() {
        val story = Story(
            listOf(Scene("s1", 1, listOf(Choice(3, "去", "s2", null))))
        )
        val result = Extractor.apply(story, mapOf("s1.choice.0" to "Go"))
        val choice = result.scenes[0].statements[0] as Choice
        assertEquals("Go", choice.label)
    }

    // 事实来源：preservePlaceholders 检测缺失占位符，以 "{name}" 拼在译文末尾
    @Test
    fun applyPreservesPlaceholderWhenMissing() {
        val story = Story(
            listOf(Scene("s1", 1, listOf(Text(2, "你好 {name}"))))
        )
        val result = Extractor.apply(story, mapOf("s1.text.0" to "Hello"))
        val text = result.scenes[0].statements[0] as Text
        assertEquals("Hello{name}", text.value)
    }

    // 事实来源：preservePlaceholders 中 translated 为空时只返回 suffix
    @Test
    fun applyEmptyTranslationWithPlaceholderReturnsSuffix() {
        val story = Story(
            listOf(Scene("s1", 1, listOf(Text(2, "{name} 来了"))))
        )
        val result = Extractor.apply(story, mapOf("s1.text.0" to ""))
        val text = result.scenes[0].statements[0] as Text
        assertEquals("{name}", text.value)
    }

    // 事实来源：preservePlaceholders 中 missing 为空时直接返回 translated
    @Test
    fun applyTranslationWithAllPlaceholdersUnchanged() {
        val story = Story(
            listOf(Scene("s1", 1, listOf(Text(2, "Hi {name}"))))
        )
        val result = Extractor.apply(story, mapOf("s1.text.0" to "你好 {name}"))
        val text = result.scenes[0].statements[0] as Text
        assertEquals("你好 {name}", text.value)
    }

    // 事实来源：applyScene 按 key 查找，未命中返回原语句，story 不变
    @Test
    fun applyUnknownKeyLeavesStoryUnchanged() {
        val story = Story(
            listOf(Scene("s1", 1, listOf(Text(2, "你好"))))
        )
        val result = Extractor.apply(story, mapOf("s9.text.9" to "Nope"))
        val text = result.scenes[0].statements[0] as Text
        assertEquals("你好", text.value)
    }

    // 事实来源：Text(value = ..., line = st.line) 保留原行号
    @Test
    fun applyPreservesLineNumber() {
        val story = Story(
            listOf(Scene("s1", 1, listOf(Text(5, "你好"))))
        )
        val result = Extractor.apply(story, mapOf("s1.text.0" to "Hello"))
        val text = result.scenes[0].statements[0] as Text
        assertEquals(5, text.line)
    }

    // 事实来源：TextEntry 构造参数 kind 与 source，Text 条目 kind=="text"，Choice 条目 kind=="choice"
    @Test
    fun extractEntryKindAndSource() {
        val story = Story(
            listOf(
                Scene(
                    "s1", 1,
                    listOf(
                        Text(2, "你好"),
                        Choice(3, "去", "s2", null)
                    )
                )
            )
        )
        val entries = Extractor.extract(story)
        assertEquals(2, entries.size)
        assertEquals("text", entries[0].kind)
        assertEquals("你好", entries[0].source)
        assertEquals("choice", entries[1].kind)
        assertEquals("去", entries[1].source)
    }
}