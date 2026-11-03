package com.interlude.log

import org.junit.jupiter.api.*
import java.io.ByteArrayOutputStream
import java.io.PrintStream

class LogDeepTest {

    private fun capture(block: () -> Unit): String {
        val old = System.err
        val buf = ByteArrayOutputStream()
        System.setErr(PrintStream(buf))
        try {
            block()
            return buf.toString()
        } finally {
            System.setErr(old)
            Log.level = Level.INFO
            Log.jsonMode = false
        }
    }

    @Test
    fun `setLevel accepts all five case-insensitively`() {
        val old = System.err
        try {
            Log.setLevel("TRACE")
            Assertions.assertEquals(Level.TRACE, Log.level)
            Log.setLevel("Debug")
            Assertions.assertEquals(Level.DEBUG, Log.level)
            Log.setLevel("INFO")
            Assertions.assertEquals(Level.INFO, Log.level)
            Log.setLevel("Warn")
            Assertions.assertEquals(Level.WARN, Log.level)
            Log.setLevel("eRRoR")
            Assertions.assertEquals(Level.ERROR, Log.level)
        } finally {
            System.setErr(old)
            Log.level = Level.INFO
            Log.jsonMode = false
        }
    }

    @Test
    fun `setLevel invalid throws with message`() {
        val old = System.err
        try {
            val ex = Assertions.assertThrows(IllegalArgumentException::class.java) {
                Log.setLevel("verbose")
            }
            Assertions.assertTrue(ex.message!!.contains("Invalid log level"))
        } finally {
            System.setErr(old)
            Log.level = Level.INFO
            Log.jsonMode = false
        }
    }

    @Test
    fun `info below warn level is dropped`() {
        Log.level = Level.WARN
        val out = capture {
            Log.info("op", "msg")
        }
        Assertions.assertEquals("", out)
    }

    @Test
    fun `warn at warn level is emitted`() {
        Log.level = Level.WARN
        val out = capture {
            Log.warn("op", "msg")
        }
        Assertions.assertTrue(out.contains("[WARN ]"))
        Assertions.assertTrue(out.contains("op=op"))
        Assertions.assertTrue(out.contains("msg"))
    }

    @Test
    fun `trace dropped at info level`() {
        Log.level = Level.INFO
        val out = capture {
            Log.trace("op", "msg")
        }
        Assertions.assertEquals("", out)
    }

    @Test
    fun `human format sorts fields`() {
        Log.level = Level.INFO
        val out = capture {
            Log.info("op", "hello", mapOf("z" to 1, "a" to 2))
        }
        val ai = out.indexOf("a=2")
        val zi = out.indexOf("z=1")
        Assertions.assertTrue(ai >= 0)
        Assertions.assertTrue(zi >= 0)
        Assertions.assertTrue(ai < zi)
    }

    @Test
    fun `human format null field prints null`() {
        Log.level = Level.INFO
        val out = capture {
            Log.info("op", "msg", mapOf("k" to null))
        }
        Assertions.assertTrue(out.contains("k=null"))
    }

    @Test
    fun `json mode structure`() {
        Log.level = Level.INFO
        Log.jsonMode = true
        val out = capture {
            Log.info("op", "hi", mapOf("n" to 42, "b" to true, "s" to "x"))
        }
        Assertions.assertTrue(out.contains("\"level\":\"INFO\""))
        Assertions.assertTrue(out.contains("\"op\":\"op\""))
        Assertions.assertTrue(out.contains("\"message\":\"hi\""))
        Assertions.assertTrue(out.contains("\"n\":42"))
        Assertions.assertTrue(out.contains("\"b\":true"))
        Assertions.assertTrue(out.contains("\"s\":\"x\""))
    }

    @Test
    fun `json escapes quotes and newline`() {
        Log.level = Level.INFO
        Log.jsonMode = true
        val out = capture {
            Log.info("op", "a\"b\nc")
        }
        Assertions.assertTrue(out.contains("\"message\":\"a\\\"b\\nc\""))
    }
}
