package dev.stagecue.server

import dev.stagecue.shared.protocol.ArmCue
import dev.stagecue.shared.protocol.ClockPing
import dev.stagecue.shared.protocol.ClientRole
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class SyncHubConnectDeepTest {

    @Test
    fun `blank clientId throws IllegalArgumentException`() {
        // require(clientId.isNotBlank()) 对全空白字符串失败，因此 "   " 必须抛 IAE。
        val hub = SyncHub(clock = { 0L })
        assertThrows(IllegalArgumentException::class.java) {
            hub.handleConnect("   ", ClientRole.DIRECTOR)
        }
    }

    @Test
    fun `empty clientId throws IllegalArgumentException`() {
        // isNotBlank() 对空串返回 false，require 触发 IAE；验证空串与空白串行为一致。
        val hub = SyncHub(clock = { 0L })
        assertThrows(IllegalArgumentException::class.java) {
            hub.handleConnect("", ClientRole.DIRECTOR)
        }
    }

    @Test
    fun `roleOf returns null for unknown client`() {
        // clients 是 ConcurrentHashMap，未注册的 key 读取返回 null。
        val hub = SyncHub(clock = { 0L })
        assertNull(hub.roleOf("ghost"))
    }

    @Test
    fun `roleOf reflects last connect role`() {
        // clients[clientId] = role 是覆盖写：同一 clientId 二次 connect 应覆盖旧角色。
        val hub = SyncHub(clock = { 0L })
        hub.handleConnect("c1", ClientRole.MONITOR)
        assertEquals(ClientRole.MONITOR, hub.roleOf("c1"))
        hub.handleConnect("c1", ClientRole.DIRECTOR)
        assertEquals(ClientRole.DIRECTOR, hub.roleOf("c1"))
    }

    @Test
    fun `welcome carries clock time twice`() {
        // 注入 now=7777L，Welcome 的 sentAtMs 与 serverTimeMs 都取自同一 now 快照。
        var now: Long = 7777L
        val hub = SyncHub(clock = { now })
        val welcome = hub.handleConnect("c1", ClientRole.DIRECTOR)
        assertEquals("c1", welcome.clientId)
        assertEquals(7777L, welcome.sentAtMs)
        assertEquals(7777L, welcome.serverTimeMs)
        assertNotNull(welcome.msgId)
        assertTrue(welcome.msgId.isNotEmpty())
    }

    @Test
    fun `clock ping pong echoes and stamps clock`() {
        // seq 与 clientTimeMs 原样回显；sentAtMs/serverTimeMs 取自注入时钟 now=5555L。
        var now: Long = 5555L
        val hub = SyncHub(clock = { now })
        val pong = hub.handleClockPing(ClockPing(msgId = "m", sentAtMs = 1L, seq = 9L, clientTimeMs = 4444L))
        assertEquals(9L, pong.seq)
        assertEquals(4444L, pong.clientTimeMs)
        assertEquals(5555L, pong.sentAtMs)
        assertEquals(5555L, pong.serverTimeMs)
        assertTrue(pong.msgId.isNotEmpty())
    }

    @Test
    fun `handleUnknown names ArmCue`() {
        // 未知消息路径用 msg::class.simpleName 构造 message，ArmCue 的 simpleName 即 "ArmCue"。
        var now: Long = 123L
        val hub = SyncHub(clock = { now })
        val error = hub.handleUnknown(ArmCue(msgId = "m", sentAtMs = 1L, cueId = "c1"))
        assertEquals("UNKNOWN_MESSAGE", error.code)
        assertTrue(error.message.contains("ArmCue"))
        assertEquals(123L, error.sentAtMs)
    }

    @Test
    fun `setRehearsal without settings stamps clock and keeps mode false`() {
        // settings 为 null 时 rehearsalMode 恒 false；setRehearsal 仍按 now=8888L 打时间戳并回显 enabled=true。
        var now: Long = 8888L
        val hub = SyncHub(clock = { now })
        val changed = hub.setRehearsal(true)
        assertEquals(8888L, changed.sentAtMs)
        assertTrue(changed.enabled)
        assertFalse(hub.rehearsalMode)
        assertTrue(changed.msgId.isNotEmpty())
    }
}
