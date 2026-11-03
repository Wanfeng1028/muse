package dev.stagecue.server

import dev.stagecue.shared.oplog.FileOpLogStore
import dev.stagecue.shared.oplog.InMemoryOpLogStore
import dev.stagecue.shared.oplog.OpLogStore

import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

/**
 * SyncHub.missedOps(sinceSeq) 语义测试。
 *
 * 覆盖：空日志、全量回放、部分回放、边界（等于最大 seq）、越界（大于最大 seq）、
 * 字段完整性、顺序（seq 升序），以及 FileOpLogStore 与 InMemoryOpLogStore 的行为一致性。
 *
 * 说明：SyncHub 只使用源码中已验证的用法 —— SyncHub(opLog = store).missedOps(n)。
 * 不编造任何其他 API。
 */
class SyncHubMissedOpsDeepTest {

    /**
     * 语义：空日志时，missedOps(0) 不应返回任何条目（没有可回放的内容）。
     */
    @Test
    fun `空日志 missedOps 返回空列表`(@TempDir dir: File) = runBlocking {
        val store = FileOpLogStore(dir)
        val hub = SyncHub(opLog = store)

        val missed = hub.missedOps(0)

        assertTrue(missed.isEmpty(), "空日志时 missedOps(0) 应为空，实际=$missed")
    }

    /**
     * 语义：写入 3 条后，sinceSeq=0 表示"从头回放"，应返回全部 3 条且 seq 为 [1,2,3]。
     */
    @Test
    fun `三条后 missedOps 零起点返回全部`(@TempDir dir: File) = runBlocking {
        val store = FileOpLogStore(dir)
        store.append("CUE_ADD", "cue-1", "d1")
        store.append("CUE_ADD", "cue-2", "d2")
        store.append("CUE_ADD", "cue-3", "d3")
        val hub = SyncHub(opLog = store)

        val missed = hub.missedOps(0)

        assertEquals(listOf(1L, 2L, 3L), missed.map { it.seq }, "sinceSeq=0 应回放 seq 1..3")
    }

    /**
     * 语义：sinceSeq=2 表示客户端已收到 1、2，只需回放 seq 严格大于 2 的条目，即 [3]。
     */
    @Test
    fun `missedOps 只返回严格大于 sinceSeq 的条目`(@TempDir dir: File) = runBlocking {
        val store = FileOpLogStore(dir)
        store.append("CUE_ADD", "cue-1", "d1")
        store.append("CUE_ADD", "cue-2", "d2")
        store.append("CUE_ADD", "cue-3", "d3")
        val hub = SyncHub(opLog = store)

        val missed = hub.missedOps(2)

        assertEquals(listOf(3L), missed.map { it.seq }, "sinceSeq=2 应只回放 seq=3")
    }

    /**
     * 语义：边界 —— sinceSeq 恰好等于最大 seq 时，没有"严格大于"的条目，返回空。
     */
    @Test
    fun `missedOps 等于最大 seq 时返回空`(@TempDir dir: File) = runBlocking {
        val store = FileOpLogStore(dir)
        store.append("CUE_ADD", "cue-1", "d1")
        store.append("CUE_ADD", "cue-2", "d2")
        store.append("CUE_ADD", "cue-3", "d3")
        val hub = SyncHub(opLog = store)

        val missed = hub.missedOps(3)

        assertTrue(missed.isEmpty(), "sinceSeq=最大 seq 时应为空，实际=$missed")
    }

    /**
     * 语义：越界 —— sinceSeq 远大于最大 seq 时，同样返回空（不能抛出，也不能倒回旧条目）。
     */
    @Test
    fun `missedOps 超出最大 seq 时返回空`(@TempDir dir: File) = runBlocking {
        val store = FileOpLogStore(dir)
        store.append("CUE_ADD", "cue-1", "d1")
        store.append("CUE_ADD", "cue-2", "d2")
        store.append("CUE_ADD", "cue-3", "d3")
        val hub = SyncHub(opLog = store)

        val missed = hub.missedOps(999)

        assertTrue(missed.isEmpty(), "sinceSeq=999 超出范围时应为空，实际=$missed")
    }

    /**
     * 语义：回放顺序必须是 seq 升序，且每条 entry 的 type / cueId / detail 字段完整保真。
     * 用各不相同的字段值做对照，避免"字段串行"式的假通过。
     */
    @Test
    fun `missedOps 返回 seq 升序且字段完整`(@TempDir dir: File) = runBlocking {
        val store = FileOpLogStore(dir)
        store.append("CUE_ADD", "cue-a", "added a")
        store.append("CUE_UPDATE", "cue-b", "updated b")
        store.append("CUE_REMOVE", null, "removed c")
        store.append("CUE_ADD", "cue-d", "added d")
        store.append("CUE_UPDATE", "cue-e", "updated e")
        val hub = SyncHub(opLog = store)

        val missed = hub.missedOps(0)

        assertEquals(listOf(1L, 2L, 3L, 4L, 5L), missed.map { it.seq }, "应按 seq 升序回放全部 5 条")
        assertEquals(
            listOf("CUE_ADD", "CUE_UPDATE", "CUE_REMOVE", "CUE_ADD", "CUE_UPDATE"),
            missed.map { it.type },
            "type 字段应逐条保真"
        )
        assertEquals(
            listOf("cue-a", "cue-b", null, "cue-d", "cue-e"),
            missed.map { it.cueId },
            "cueId 字段应逐条保真（含 null）"
        )
        assertEquals(
            listOf("added a", "updated b", "removed c", "added d", "updated e"),
            missed.map { it.detail },
            "detail 字段应逐条保真"
        )
    }

    /**
     * 语义：对照测试 —— InMemoryOpLogStore 与 FileOpLogStore 在 missedOps 上语义一致。
     * 相同写入序列下，两者的 seq 列表与字段必须相同，保证实现可互换。
     */
    @Test
    fun `InMemoryOpLogStore 与 FileOpLogStore 的 missedOps 语义一致`(@TempDir dir: File) = runBlocking {
        val fileStore = FileOpLogStore(dir)
        val memoryStore = InMemoryOpLogStore()

        for (store in listOf<OpLogStore>(fileStore, memoryStore)) {
            store.append("CUE_ADD", "cue-a", "added a")
            store.append("CUE_UPDATE", "cue-b", "updated b")
            store.append("CUE_REMOVE", null, "removed c")
        }

        val fileHub = SyncHub(opLog = fileStore)
        val memoryHub = SyncHub(opLog = memoryStore)

        val fromFile = fileHub.missedOps(1)
        val fromMemory = memoryHub.missedOps(1)

        assertEquals(listOf(2L, 3L), fromFile.map { it.seq }, "File 实现 sinceSeq=1 应回放 2、3")
        assertEquals(listOf(2L, 3L), fromMemory.map { it.seq }, "Memory 实现 sinceSeq=1 应回放 2、3")
        assertEquals(fromFile.map { it.seq }, fromMemory.map { it.seq }, "两实现 seq 序列应一致")
        assertEquals(fromFile.map { it.type }, fromMemory.map { it.type }, "两实现 type 序列应一致")
        assertEquals(fromFile.map { it.cueId }, fromMemory.map { it.cueId }, "两实现 cueId 序列应一致")
        assertEquals(fromFile.map { it.detail }, fromMemory.map { it.detail }, "两实现 detail 序列应一致")
    }
}