package dev.stagecue.server

import dev.stagecue.shared.oplog.FileOpLogStore

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

/**
 * FileOpLogStore 重启语义测试。
 *
 * 关注点：
 * 1. 关闭后重新打开同一目录，seq 是否延续「历史最大 seq + 1」。
 * 2. 多次重启是否单调递增、不回绕。
 * 3. clear 之后重启是否从 1 重新开始。
 * 4. 重启后能否 replay 全部历史 entries。
 * 5. 空目录首次打开的起点。
 * 6. 文件被外部损坏/截断时构造是否容错（源码语义：解析失败仅告警跳过，不抛错）。
 */
class FileOpLogStoreRestartDeepTest {

    /** 追加三条后重启，新实例的 seq 应当从 4 开始。 */
    @Test
    fun `重启后 seq 延续为最大 seq 加一`(@TempDir dir: File) {
        val first = FileOpLogStore(dir)
        val e1 = first.append("CUE_START", "cue-1", "detail-1")
        val e2 = first.append("CUE_STOP", "cue-1", "detail-2")
        val e3 = first.append("CUE_START", "cue-2", "detail-3")
        assertEquals(1L, e1.seq)
        assertEquals(2L, e2.seq)
        assertEquals(3L, e3.seq)

        val second = FileOpLogStore(dir)
        assertEquals(3, second.readAll().size)

        val e4 = second.append("CUE_STOP", "cue-2", "detail-4")
        assertEquals(4L, e4.seq)
    }

    /** 连续重启 3 次，seq 必须持续递增且不回绕。 */
    @Test
    fun `多次重启 seq 持续递增不回绕`(@TempDir dir: File) {
        val store0 = FileOpLogStore(dir)
        assertEquals(1L, store0.append("T", "c", "d0").seq)

        val store1 = FileOpLogStore(dir)
        assertEquals(2L, store1.append("T", "c", "d1").seq)

        val store2 = FileOpLogStore(dir)
        assertEquals(3L, store2.append("T", "c", "d2").seq)

        val store3 = FileOpLogStore(dir)
        assertEquals(4L, store3.append("T", "c", "d3").seq)
        assertEquals(4, store3.readAll().size)
    }

    /** clear 之后重启，seq 应从 1 重新开始。 */
    @Test
    fun `clear 后重启 seq 从 1 开始`(@TempDir dir: File) {
        val first = FileOpLogStore(dir)
        first.append("T", "c", "d1")
        first.append("T", "c", "d2")
        first.clear()

        val second = FileOpLogStore(dir)
        assertTrue(second.readAll().isEmpty())
        val e = second.append("T", "c", "d3")
        assertEquals(1L, e.seq)
    }

    /** 重启后历史 entries 可读，replay 全量且 seq/type/cueId/detail 一致。 */
    @Test
    fun `重启后历史 entries 可完整 replay`(@TempDir dir: File) {
        val first = FileOpLogStore(dir)
        first.append("CUE_START", "cue-A", "alpha")
        first.append("CUE_STOP", "cue-A", "beta")
        first.append("CUE_START", "cue-B", "gamma")

        val second = FileOpLogStore(dir)
        val all = second.readAll()
        assertEquals(3, all.size)
        assertEquals(listOf(1L, 2L, 3L), all.map { it.seq })
        assertEquals(listOf("CUE_START", "CUE_STOP", "CUE_START"), all.map { it.type })
        assertEquals(listOf("cue-A", "cue-A", "cue-B"), all.map { it.cueId })
        assertEquals(listOf("alpha", "beta", "gamma"), all.map { it.detail })
        // eventId 应被持久化并可读回，非空。
        assertTrue(all.all { it.eventId.isNotEmpty() })
    }

    /** 空目录首次打开：无历史，seq 从 1 开始。 */
    @Test
    fun `空目录首次打开 seq 从 1 开始`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        assertTrue(store.readAll().isEmpty())
        val e = store.append("T", null, "first")
        assertEquals(1L, e.seq)
    }

    /**
     * 外部把文件尾部截断成半行时，构造应当容错：
     * 源码语义为「单行解析失败仅告警并跳过」，因此不抛错，
     * 已成功解析的完整行保留，nextSeq 基于可解析 entries 的最大 seq + 1。
     */
    @Test
    fun `文件尾部截断后打开按容错语义处理`(@TempDir dir: File) {
        val first = FileOpLogStore(dir)
        first.append("T", "c", "d1")
        first.append("T", "c", "d2")

        val logFile = File(dir, "oplog.jsonl")
        assertTrue(logFile.exists())
        // 追加一行明显不完整的 JSON，模拟崩溃产生的截断尾行。
        logFile.appendText("{\"seq\":3,\"eventId\":\"broken")

        val second = FileOpLogStore(dir)
        // 只有前两条完整行被加载，损坏行被跳过。
        val all = second.readAll()
        assertEquals(2, all.size)
        assertEquals(listOf(1L, 2L), all.map { it.seq })
        assertNotNull(all[0].eventId)

        // 续写应接在可解析的最大 seq 之后。
        val e = second.append("T", "c", "d3")
        assertEquals(3L, e.seq)
    }
}