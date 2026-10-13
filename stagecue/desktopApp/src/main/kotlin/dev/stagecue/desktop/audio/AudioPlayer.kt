package dev.stagecue.desktop.audio

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.File
import javax.sound.sampled.AudioSystem
import javax.sound.sampled.Clip
import javax.sound.sampled.FloatControl

/**
 * 本地音频播放：仅支持 WAV（v1 明确限制）。
 * 淡入通过 FloatControl MASTER_GAIN 协程渐变实现。
 * 文件缺失/格式不支持时记日志、不崩溃。
 */
object AudioPlayer {
    private var clip: Clip? = null
    private var fadeJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.Default)
    var logger: ((String) -> Unit)? = null

    @Synchronized
    fun play(path: String, fadeInMs: Long) {
        stopInternal()
        try {
            val file = File(path)
            if (!file.exists()) {
                logger?.invoke("音频文件不存在：$path")
                return
            }
            val stream = AudioSystem.getAudioInputStream(file)
            val c = AudioSystem.getClip()
            c.open(stream)
            clip = c

            val gain = try {
                c.getControl(FloatControl.Type.MASTER_GAIN) as? FloatControl
            } catch (_: Throwable) {
                null
            }

            if (gain != null && fadeInMs > 0) {
                // 从静音开始
                gain.value = gain.minimum
                c.start()
                val steps = 20
                val stepDelay = (fadeInMs / steps).coerceAtLeast(10L)
                fadeJob = scope.launch {
                    try {
                        val range = gain.maximum - gain.minimum
                        for (i in 1..steps) {
                            if (!isActive) break
                            val v = gain.minimum + range * (i.toFloat() / steps)
                            try {
                                gain.value = v
                            } catch (_: Throwable) {
                            }
                            delay(stepDelay)
                        }
                        try {
                            gain.value = 0f
                        } catch (_: Throwable) {
                        }
                    } catch (_: Throwable) {
                    }
                }
            } else {
                c.start()
            }
        } catch (e: Throwable) {
            logger?.invoke("音频播放失败：${e.message ?: e.javaClass.simpleName}（仅支持 WAV）")
            stopInternal()
        }
    }

    @Synchronized
    fun stop() {
        stopInternal()
    }

    private fun stopInternal() {
        try {
            fadeJob?.cancel()
            fadeJob = null
            clip?.stop()
            clip?.close()
        } catch (_: Throwable) {
        } finally {
            clip = null
        }
    }
}
