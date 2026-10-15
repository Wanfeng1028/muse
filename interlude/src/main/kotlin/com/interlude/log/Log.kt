package com.interlude.log

import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter

enum class Level { TRACE, DEBUG, INFO, WARN, ERROR }

object Log {
    var level: Level = Level.INFO
    var jsonMode: Boolean = false

    private val TS_FMT: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSSXXX")

    fun setLevel(name: String) {
        val v = when (name.lowercase()) {
            "trace" -> Level.TRACE
            "debug" -> Level.DEBUG
            "info" -> Level.INFO
            "warn" -> Level.WARN
            "error" -> Level.ERROR
            else -> throw IllegalArgumentException(
                "Invalid log level: '$name'. Valid values: trace, debug, info, warn, error"
            )
        }
        level = v
    }

    fun trace(op: String, message: String, fields: Map<String, Any?> = emptyMap()) =
        log(Level.TRACE, op, message, fields)

    fun debug(op: String, message: String, fields: Map<String, Any?> = emptyMap()) =
        log(Level.DEBUG, op, message, fields)

    fun info(op: String, message: String, fields: Map<String, Any?> = emptyMap()) =
        log(Level.INFO, op, message, fields)

    fun warn(op: String, message: String, fields: Map<String, Any?> = emptyMap()) =
        log(Level.WARN, op, message, fields)

    fun error(op: String, message: String, fields: Map<String, Any?> = emptyMap()) =
        log(Level.ERROR, op, message, fields)

    private fun log(lv: Level, op: String, message: String, fields: Map<String, Any?>) {
        if (lv.ordinal < level.ordinal) return
        val ts = OffsetDateTime.now().format(TS_FMT)
        val line = if (jsonMode) formatJson(ts, lv, op, message, fields)
        else formatHuman(ts, lv, op, message, fields)
        System.err.println(line)
    }

    private fun formatHuman(
        ts: String,
        lv: Level,
        op: String,
        message: String,
        fields: Map<String, Any?>
    ): String {
        val sb = StringBuilder()
        sb.append(ts).append(' ')
        sb.append('[').append(lv.name.padEnd(5)).append(']').append(' ')
        sb.append("op=").append(op)
        for ((k, v) in fields.toSortedMap()) {
            sb.append(' ').append(k).append('=').append(v?.toString() ?: "null")
        }
        sb.append(' ').append(message)
        return sb.toString()
    }

    private fun formatJson(
        ts: String,
        lv: Level,
        op: String,
        message: String,
        fields: Map<String, Any?>
    ): String {
        val sb = StringBuilder()
        sb.append('{')
        sb.append("\"timestamp\":").append(quote(ts)).append(',')
        sb.append("\"level\":").append(quote(lv.name)).append(',')
        sb.append("\"op\":").append(quote(op)).append(',')
        sb.append("\"message\":").append(quote(message))
        for ((k, v) in fields.toSortedMap()) {
            sb.append(',').append(quote(k)).append(':').append(jsonValue(v))
        }
        sb.append('}')
        return sb.toString()
    }

    private fun jsonValue(v: Any?): String = when (v) {
        null -> "null"
        is Boolean -> v.toString()
        is Byte, is Short, is Int, is Long, is Float, is Double -> v.toString()
        else -> quote(v.toString())
    }

    private fun quote(s: String): String {
        val sb = StringBuilder(s.length + 2)
        sb.append('"')
        for (c in s) {
            when (c) {
                '"' -> sb.append("\\\"")
                '\\' -> sb.append("\\\\")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                '\t' -> sb.append("\\t")
                '\b' -> sb.append("\\b")
                '\u000C' -> sb.append("\\f")
                else -> if (c < ' ') {
                    sb.append("\\u").append(String.format("%04x", c.code))
                } else {
                    sb.append(c)
                }
            }
        }
        sb.append('"')
        return sb.toString()
    }
}