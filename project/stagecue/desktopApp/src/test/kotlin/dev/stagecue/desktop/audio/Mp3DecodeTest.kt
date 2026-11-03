package dev.stagecue.desktop.audio

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.io.File
import javax.sound.sampled.AudioFormat
import javax.sound.sampled.UnsupportedAudioFileException

class Mp3DecodeTest {

    @Test
    fun `mp3 decodes to pcm`() {
        val url = javaClass.getResource("/audio/tone.mp3") ?: error("缺测试资源 audio/tone.mp3")
        val path = File(url.toURI()).absolutePath
        AudioPlayer.decodeToPcm(path).use { pcm ->
            assertEquals(AudioFormat.Encoding.PCM_SIGNED, pcm.format.encoding)
            val bytes = pcm.readAllBytes()
            assertTrue(bytes.size > 8000, "0.5s 44100Hz 16-bit mono 应远大于 8KB，实际 ${bytes.size}")
        }
    }

    @Test
    fun `wav still decodes to pcm`() {
        val wav = File.createTempFile("tone-", ".wav")
        wav.deleteOnExit()
        writeToneWav(wav, seconds = 0.1, freqHz = 440.0, sampleRate = 44100)
        AudioPlayer.decodeToPcm(wav.absolutePath).use { pcm ->
            assertEquals(AudioFormat.Encoding.PCM_SIGNED, pcm.format.encoding)
            val bytes = pcm.readAllBytes()
            assertTrue(bytes.isNotEmpty(), "WAV 解码数据不应为空")
        }
    }

    @Test
    fun `missing file throws`() {
        assertThrows<Exception> {
            AudioPlayer.decodeToPcm("/不存在/xxx.mp3")
        }
    }

    @Test
    fun `garbage file throws UnsupportedAudioFileException`() {
        val bad = File.createTempFile("garbage-", ".wav")
        bad.deleteOnExit()
        bad.writeText("not audio")
        assertThrows<UnsupportedAudioFileException> {
            AudioPlayer.decodeToPcm(bad.absolutePath)
        }
    }

    /** 手写 16-bit PCM 单声道 WAV（44 字节 RIFF 头 + 数据），小端序。 */
    private fun writeToneWav(file: File, seconds: Double, freqHz: Double, sampleRate: Int) {
        val channels = 1
        val bitsPerSample = 16
        val byteRate = sampleRate * channels * bitsPerSample / 8
        val blockAlign = channels * bitsPerSample / 8
        val totalSamples = (sampleRate * seconds).toInt()
        val dataSize = totalSamples * blockAlign

        val pcm = ByteArrayOutputStream(dataSize)
        val dos = DataOutputStream(pcm)
        for (i in 0 until totalSamples) {
            val v = (Short.MAX_VALUE * 0.5 * Math.sin(2.0 * Math.PI * freqHz * i / sampleRate)).toInt()
            dos.writeByte(v and 0xFF)
            dos.writeByte((v shr 8) and 0xFF)
        }
        dos.flush()
        val data = pcm.toByteArray()

        DataOutputStream(file.outputStream()).use { out ->
            out.writeBytes("RIFF")
            out.writeInt(Integer.reverseBytes(36 + dataSize))
            out.writeBytes("WAVE")
            out.writeBytes("fmt ")
            out.writeInt(Integer.reverseBytes(16))
            out.writeShort(java.lang.Short.reverseBytes(1.toShort()).toInt())        // PCM
            out.writeShort(java.lang.Short.reverseBytes(channels.toShort()).toInt())
            out.writeInt(Integer.reverseBytes(sampleRate))
            out.writeInt(Integer.reverseBytes(byteRate))
            out.writeShort(java.lang.Short.reverseBytes(blockAlign.toShort()).toInt())
            out.writeShort(java.lang.Short.reverseBytes(bitsPerSample.toShort()).toInt())
            out.writeBytes("data")
            out.writeInt(Integer.reverseBytes(dataSize))
            out.write(data)
        }
    }
}
