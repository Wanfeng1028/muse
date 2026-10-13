
package com.interlude.i18n

import com.interlude.dsl.Choice
import com.interlude.dsl.Scene
import com.interlude.dsl.Statement
import com.interlude.dsl.Story
import com.interlude.dsl.Text
import com.interlude.dsl.extractPlaceholders

data class TextEntry(
    val key: String,
    val sceneId: String,
    val kind: String,
    val source: String
)

object Extractor {

    fun extract(story: Story): List<TextEntry> {
        val entries = mutableListOf<TextEntry>()
        for (scene in story.scenes) {
            entries.addAll(extractScene(scene))
        }
        return entries
    }

    private fun extractScene(scene: Scene): List<TextEntry> {
        val entries = mutableListOf<TextEntry>()
        var textIndex = 0
        var choiceIndex = 0
        for (st in scene.statements) {
            when (st) {
                is Text -> {
                    entries.add(
                        TextEntry(
                            key = "${scene.id}.text.$textIndex",
                            sceneId = scene.id,
                            kind = "text",
                            source = st.value
                        )
                    )
                    textIndex++
                }
                is Choice -> {
                    entries.add(
                        TextEntry(
                            key = "${scene.id}.choice.$choiceIndex",
                            sceneId = scene.id,
                            kind = "choice",
                            source = st.label
                        )
                    )
                    choiceIndex++
                }
                else -> {}
            }
        }
        return entries
    }

    fun apply(story: Story, translations: Map<String, String>): Story {
        val newScenes = story.scenes.map { scene -> applyScene(scene, translations) }
        return story.copy(scenes = newScenes)
    }

    private fun applyScene(scene: Scene, translations: Map<String, String>): Scene {
        var textIndex = 0
        var choiceIndex = 0
        val newStatements: List<Statement> = scene.statements.map { st ->
            when (st) {
                is Text -> {
                    val key = "${scene.id}.text.$textIndex"
                    textIndex++
                    val translated = translations[key]
                    if (translated != null) {
                        Text(value = preservePlaceholders(st.value, translated), line = st.line)
                    } else {
                        st
                    }
                }
                is Choice -> {
                    val key = "${scene.id}.choice.$choiceIndex"
                    choiceIndex++
                    val translated = translations[key]
                    if (translated != null) {
                        st.copy(label = preservePlaceholders(st.label, translated))
                    } else {
                        st
                    }
                }
                else -> st
            }
        }
        return scene.copy(statements = newStatements)
    }

    /**
     * 译文应保留原文中的 {var} 占位符。若译文中缺失某些占位符，则在末尾补齐，
     * 以确保占位符集合与原文字符串一致。
     */
    private fun preservePlaceholders(source: String, translated: String): String {
        val required = extractPlaceholders(source)
        if (required.isEmpty()) return translated
        val present = extractPlaceholders(translated).toSet()
        val missing = required.filter { it !in present }
        if (missing.isEmpty()) return translated
        val suffix = missing.joinToString(separator = "") { "{$it}" }
        return if (translated.isEmpty()) suffix else "$translated$suffix"
    }
}
