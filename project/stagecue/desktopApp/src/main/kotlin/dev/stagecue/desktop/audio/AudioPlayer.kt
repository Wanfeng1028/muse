package dev.stagecue.desktop.audio

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.File
import javax.sound.sampled.AudioFormat
import javax.sound.sampled.AudioInputStream
import javax.sound.sampled.AudioSystem
import javax.sound.sampled.Clip
import javax.sound.sampled.FloatControl
import javax.sound.sampled.UnsupportedAudioFileException

/**
 * 本地音频播放：支持 WAV / MP3。
 * MP3 经 mp3spi（SPI 自动发现）解码为 PCM_SIGNED 后播放。
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
            val stream = decodeToPcm(path)
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
            logger?.invoke("音频播放失败：${e.message ?: e.javaClass.simpleName}（支持 WAV / MP3）")
            stopInternal()
        }
    }

    /**
     * 把音频文件解码为 PCM_SIGNED 流（WAV 直接返回，MP3 经 mp3spi 转码）。
     * 供测试与排障用；调用方负责关闭返回的流。
     * @throws UnsupportedAudioFileException 格式不支持
     * @throws java.io.IOException 读取失败
     */
    @Throws(UnsupportedAudioFileException::class, java.io.IOException::class)
    fun decodeToPcm(path: String): AudioInputStream {
        val file = File(path)
        val base = AudioSystem.getAudioInputStream(file)
        if (base.format.encoding == AudioFormat.Encoding.PCM_SIGNED) {
            return base
        }
        val src = base.format
        val decoded = AudioFormat(
            AudioFormat.Encoding.PCM_SIGNED,
            src.sampleRate,
            16,
            src.channels,
            src.channels * 2,
            src.sampleRate,
            false
        )
        try {
            return AudioSystem.getAudioInputStream(decoded, base)
        } catch (e: Exception) {
            try { base.close() } catch (_: Exception) { /* ignore */ }
            throw e
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
