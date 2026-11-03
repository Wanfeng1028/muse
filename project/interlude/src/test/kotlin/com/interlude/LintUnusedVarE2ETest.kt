package com.interlude

import java.io.ByteArrayOutputStream
import java.io.PrintStream
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class LintUnusedVarE2ETest {

    private val script = """
    scene start:
      text: "开始"
      set unused_flag = 1
      set hp = 100
      text: "血量 {hp}"
      end
    """.trimIndent()

    @Test
    fun textFormatShowsUnusedVarWarning() {
        val dir = createTempDirectory("interlude-e2e")
        val file = dir.resolve("story.interlude")
        Files.writeString(file, script)

        val out = ByteArrayOutputStream()
        val original = System.out
        try {
            System.setOut(PrintStream(out))
            runLint(arrayOf("lint", file.toAbsolutePath().toString(), "--format", "text"))
        } finally {
            System.setOut(original)
        }

        val text = out.toString()
        assertTrue(text.contains("[WARNING] UNUSED_VAR"))
    }

    @Test
    fun jsonFormatShowsUnusedVarCode() {
        val dir = createTempDirectory("interlude-e2e")
        val file = dir.resolve("story.interlude")
        Files.writeString(file, script)

        val out = ByteArrayOutputStream()
        val original = System.out
        try {
            System.setOut(PrintStream(out))
            val code = runLint(arrayOf("lint", file.toAbsolutePath().toString(), "--format", "json"))
            assertEquals(0, code)
        } finally {
            System.setOut(original)
        }

        val text = out.toString()
        assertTrue(text.contains("\"code\":\"UNUSED_VAR\""))
    }
}
