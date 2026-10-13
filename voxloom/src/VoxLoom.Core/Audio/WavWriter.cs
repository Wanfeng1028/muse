using System.Buffers.Binary;
using System.Text;

namespace VoxLoom.Core.Audio;

/// <summary>
/// WAV 写入器：将 <see cref="AudioClip"/> 以 16-bit PCM 格式写出。
/// </summary>
public static class WavWriter
{
    private const int BitsPerSample = 16;
    private const int WaveFormatPcm = 0x0001;

    /// <summary>
    /// 将音频片段写入指定路径的 WAV 文件（16-bit PCM，小端）。
    /// </summary>
    /// <param name="path">目标文件路径。</param>
    /// <param name="clip">要写出的音频片段。</param>
    /// <exception cref="ArgumentNullException"><paramref name="path"/> 或 <paramref name="clip"/> 为 null。</exception>
    /// <exception cref="WavFormatException">音频参数不被 16-bit PCM WAV 支持。</exception>
    public static void Write(string path, AudioClip clip)
    {
        ArgumentNullException.ThrowIfNull(path);
        ArgumentNullException.ThrowIfNull(clip);

        if (clip.SampleRate <= 0)
        {
            throw new WavFormatException($"无法写出：采样率必须大于 0，当前为 {clip.SampleRate}。");
        }

        if (clip.Channels <= 0 || clip.Channels > 2)
        {
            throw new WavFormatException($"无法写出：仅支持 1 或 2 声道，当前为 {clip.Channels}。");
        }

        long sampleCount = clip.Samples.Length;
        if (sampleCount > int.MaxValue / 2)
        {
            throw new WavFormatException("音频数据过大，超出 32-bit WAV 的容量限制。");
        }

        int channels = clip.Channels;
        int blockAlign = channels * (BitsPerSample / 8);
        int byteRate = clip.SampleRate * blockAlign;
        int dataSize = (int)sampleCount * (BitsPerSample / 8);
        int riffSize = 4 + (8 + 16) + (8 + dataSize);

        // 一次分配整个文件缓冲，避免多次 IO 抖动
        var buffer = new byte[8 + riffSize];

        // ---- RIFF header ----
        WriteAscii(buffer, 0, "RIFF");
        BinaryPrimitives.WriteUInt32LittleEndian(buffer.AsSpan(4, 4), (uint)riffSize);
        WriteAscii(buffer, 8, "WAVE");

        // ---- fmt chunk ----
        int p = 12;
        WriteAscii(buffer, p, "fmt ");
        BinaryPrimitives.WriteUInt32LittleEndian(buffer.AsSpan(p + 4, 4), 16);
        BinaryPrimitives.WriteUInt16LittleEndian(buffer.AsSpan(p + 8, 2), WaveFormatPcm);
        BinaryPrimitives.WriteUInt16LittleEndian(buffer.AsSpan(p + 10, 2), (ushort)channels);
        BinaryPrimitives.WriteUInt32LittleEndian(buffer.AsSpan(p + 12, 4), (uint)clip.SampleRate);
        BinaryPrimitives.WriteUInt32LittleEndian(buffer.AsSpan(p + 16, 4), (uint)byteRate);
        BinaryPrimitives.WriteUInt16LittleEndian(buffer.AsSpan(p + 20, 2), (ushort)blockAlign);
        BinaryPrimitives.WriteUInt16LittleEndian(buffer.AsSpan(p + 22, 2), BitsPerSample);

        // ---- data chunk ----
        p = 12 + 8 + 16;
        WriteAscii(buffer, p, "data");
        BinaryPrimitives.WriteUInt32LittleEndian(buffer.AsSpan(p + 4, 4), (uint)dataSize);

        int dataOffset = p + 8;
        var samples = clip.Samples;
        for (int i = 0; i < samples.Length; i++)
        {
            short s = FloatToInt16(samples[i]);
            BinaryPrimitives.WriteInt16LittleEndian(buffer.AsSpan(dataOffset + i * 2, 2), s);
        }

        File.WriteAllBytes(path, buffer);
    }

    private static void WriteAscii(byte[] buffer, int offset, string value)
    {
        for (int i = 0; i < value.Length; i++)
        {
            buffer[offset + i] = (byte)value[i];
        }
    }

    /// <summary>
    /// 将 [-1, 1] 的浮点样本转换为 16-bit 有符号整型。
    /// 超出范围时进行饱和裁剪，NaN 视为 0。
    /// </summary>
    private static short FloatToInt16(float value)
    {
        if (float.IsNaN(value))
        {
            return 0;
        }

        if (value >= 1f)
        {
            return short.MaxValue;
        }

        if (value <= -1f)
        {
            return short.MinValue;
        }

        // 采用乘以 32767 并四舍五入，避免正负不对称的细微偏置
        double scaled = Math.Round(value * 32767.0, MidpointRounding.AwayFromZero);
        if (scaled > short.MaxValue)
        {
            return short.MaxValue;
        }
        if (scaled < short.MinValue)
        {
            return short.MinValue;
        }
        return (short)scaled;
    }
}
