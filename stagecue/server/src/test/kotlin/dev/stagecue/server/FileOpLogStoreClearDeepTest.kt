package dev.stagecue.server

import dev.stagecue.shared.oplog.FileOpLogStore

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

/**
 * FileOpLogStore.clear() 语义测试。
 *
 * 覆盖：
 *  - 成功清空：内存 entries 清空、nextSeq 回 1、日志文件被删除
 *  - 清空后重放为空
 *  - 空 store / 连续 clear 幂等
 *  - 删除失败 fail-fast：抛 IllegalStateException，且内存状态（entries、nextSeq）保持不变
 *  - 删除后新实例打开同一目录：seq 从 1 开始，无残留
 */
class FileOpLogStoreClearDeepTest {

    /**
     * 在测：append 3 条后 clear，内存 entries 为空、日志文件被删除、再 append 的 seq 从 1 开始。
     */
    @Test
    fun `append 三条后 clear 清空内存删除文件并重置 seq`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        store.append("a", null, "d1")
        store.append("b", "cue-1", "d2")
        store.append("c", null, "d3")
        assertEquals(3, store.readAll().size)

        store.clear()

        assertTrue(store.readAll().isEmpty(), "clear 后内存 entries 应为空")
        val file = File(dir, "oplog.jsonl")
        assertFalse(file.exists(), "clear 后日志文件应被删除")

        val entry = store.append("after-clear", null, "d")
        assertEquals(1L, entry.seq, "clear 后首次 append 的 seq 应为 1")
    }

    /**
     * 在测：clear 后 readAll 重放为空，说明内存已彻底清空。
     */
    @Test
    fun `clear 后重放为空`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        store.append("x", null, "1")
        store.append("y", null, "2")

        store.clear()

        assertEquals(0, store.readAll().size, "clear 后重放不应有任何 entry")
    }

    /**
     * 在测：空 store 上 clear 不应抛异常，且后续 append 从 seq=1 开始。
     */
    @Test
    fun `空 store 上 clear 不抛异常`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        assertEquals(0, store.readAll().size)

        store.clear()

        val entry = store.append("first", null, "d")
        assertEquals(1L, entry.seq)
    }

    /**
     * 在测：连续 clear 两次幂等，不抛异常，且状态与单次 clear 一致。
     */
    @Test
    fun `连续 clear 两次幂等`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        store.append("k", null, "d")

        store.clear()
        store.clear()

        assertTrue(store.readAll().isEmpty())
        val entry = store.append("post", null, "d")
        assertEquals(1L, entry.seq)
    }

    /**
     * 在测：当日志文件无法删除时，clear 必须 fail-fast 抛 IllegalStateException。
     *
     * 环境假设：@TempDir 下的子目录在多数 CI（非 root）下可通过 setWritable(false) 令其不可写，
     * 从而让 File.delete() 失败。若运行在 root 下 chmod 无效，该断言可能失效——此处依赖标准
     * 非 root 测试环境；为保证确定性与可复现，测试会先探测目录是否真的不可写，若仍可写则跳过。
     */
    @Test
    fun `删除失败时 clear 抛 IllegalStateException`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        store.append("keep", null, "d")
        val file = File(dir, "oplog.jsonl")
        assertTrue(file.exists(), "前置条件：日志文件应存在")

        val originalWritable = dir.canWrite()
        dir.setWritable(false, false)
        try {
            if (dir.canWrite()) {
                // root 等特权环境下 chmod 无效，无法构造删除失败场景，跳过断言。
                return
            }
            assertThrows(IllegalStateException::class.java) {
                store.clear()
            }
        } finally {
            dir.setWritable(originalWritable, false)
        }
    }

    /**
     * 在测：删除失败抛异常后，内存 entries 与 nextSeq 均保持不变——异常后 append 仍能成功且 seq 连续。
     */
    @Test
    fun `删除失败后内存状态不变且 seq 连续`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        val e1 = store.append("a", null, "1")
        val e2 = store.append("b", null, "2")
        assertEquals(1L, e1.seq)
        assertEquals(2L, e2.seq)
        val sizeBefore = store.readAll().size

        val originalWritable = dir.canWrite()
        dir.setWritable(false, false)
        try {
            if (dir.canWrite()) {
                // root 环境下无法触发删除失败，跳过。
                return
            }
            assertThrows(IllegalStateException::class.java) {
                store.clear()
            }
        } finally {
            dir.setWritable(originalWritable, false)
        }

        assertEquals(sizeBefore, store.readAll().size, "异常后内存 entries 不应被清空")
        assertEquals(2, store.readAll().size)

        // 恢复可写后再次 append，seq 必须从 3 继续（nextSeq 未回退）。
        val e3 = store.append("c", null, "3")
        assertEquals(3L, e3.seq, "删除失败后 nextSeq 不应回退，seq 应连续")
    }

    /**
     * 在测：clear 删除文件后，用同一目录新建 store，seq 从 1 开始（无残留 entry）。
     */
    @Test
    fun `clear 后新实例打开同目录 seq 从 1 开始`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        store.append("a", null, "1")
        store.append("b", null, "2")
        store.clear()

        val reopened = FileOpLogStore(dir)
        assertEquals(0, reopened.readAll().size, "文件已删除，新实例不应加载到任何 entry")
        val entry = reopened.append("fresh", null, "d")
        assertEquals(1L, entry.seq, "新实例在空目录下 seq 应从 1 开始")
        assertNotNull(entry.eventId)
    }
}
