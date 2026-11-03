package dev.stagecue.server.ws

import dev.stagecue.server.metrics.StageMetrics
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong

/**
 * WS 广播中心：每客户端独立有界队列 + 独立发送协程。
 *
 * 背压策略（v0.3 决策）：队列满时丢弃最旧（DROP_OLDEST），不断开慢消费者。
 * 理由：演出中慢端短暂卡顿可接受，断开会导致黑屏/失联更危险；cue 事件"最新覆盖旧"，
 * 优先送达最新；丢弃数经 stagecue_ws_broadcast_dropped_total 可观测。
 *
 * 序列号为每客户端独立（per-slot），缺口法只统计真正进入该客户端队列后被挤掉的消息；
 * 迟注册与被排除的广播不产生幽灵丢弃计数。
 */
class BroadcastHub(
    private val metrics: StageMetrics,
    private val queueCapacity: Int = 64,
) {
    /** 发送一帧文本的抽象，便于单测用假实现。生产环境包装 WebSocketServerSession.send。 */
    fun interface FrameSink {
        suspend fun send(text: String)
    }

    private data class Sequenced(val seq: Long, val text: String)

    private class Slot(
        val sink: FrameSink,
        val channel: Channel<Sequenced>,
    ) {
        var job: Job? = null
        var lastDeliveredSeq: Long = 0L
        val seq = AtomicLong(0L)
    }

    private val slots = ConcurrentHashMap<String, Slot>()

    /**
     * 注册客户端并启动其专属发送协程（作为 scope 的子协程，scope 结束自动取消）。
     * 同一 clientId 重复注册会先注销旧的（幂等）。
     */
    fun register(clientId: String, sink: FrameSink, scope: CoroutineScope): Job {
        unregister(clientId)
        val slot = Slot(sink, Channel(queueCapacity, BufferOverflow.DROP_OLDEST))
        slots[clientId] = slot
        val job = scope.launch {
            try {
                for (item in slot.channel) {
                    val gap = item.seq - slot.lastDeliveredSeq - 1
                    if (gap > 0) metrics.broadcastDropped(gap)
                    slot.lastDeliveredSeq = item.seq
                    try {
                        slot.sink.send(item.text)
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        unregister(clientId)
                        break
                    }
                }
            } finally {
                // channel 关闭或 scope 取消时确保清理
                if (slots[clientId] === slot) slots.remove(clientId)
            }
        }
        slot.job = job
        return job
    }

    /** 注销客户端：取消发送协程并关闭队列。幂等，不存在则无操作。 */
    fun unregister(clientId: String) {
        val slot = slots.remove(clientId) ?: return
        slot.job?.cancel()
        slot.channel.close()
    }

    /** 广播文本给除 exceptClientId 外的所有客户端；永不挂起。 */
    fun broadcastExcept(exceptClientId: String?, text: String) {
        for ((id, slot) in slots) {
            if (id == exceptClientId) continue
            val s = slot.seq.incrementAndGet()
            slot.channel.trySend(Sequenced(s, text))
        }
    }

    fun sessionCount(): Int = slots.size
}
