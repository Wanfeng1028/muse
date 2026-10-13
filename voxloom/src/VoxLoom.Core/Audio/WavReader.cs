using System.Buffers.Binary;
using System.Text;

namespace VoxLoom.Core.Audio;

/// <summary>
/// WAV（RIFF/WAVE）文件读取器。
/// <para>
/// 支持的编码格式：
/// <list type="bullet">
///   <item><description>PCM 16-bit / 24-bit / 32-bit（整型）</description></item>
///   <item><description>IEEE float 32-bit</description></item>
/// </list>
/// 支持的声道数：1（单声道）、2（立体声）。
/// </para>
/// </summary>
public static class WavReader
{
    private const int WaveFormatPcm = 0x0001;
    private const int WaveFormatIeeeFloat = 0x0003;
    private const int WaveFormatExtensible = 0xFFFE;

    /// <summary>
    /// 从指定路径读取 WAV 文件并返回 <see cref="AudioClip"/>。
    /// </summary>
    /// <param name="path">WAV 文件路径。</param>
    /// <exception cref="ArgumentNullException"><paramref name="path"/> 为 null。</exception>
    /// <exception cref="WavFormatException">文件不是合法的 WAV，或使用了不支持的编码/声道配置。</exception>
    public static AudioClip Read(string path)
    {
        ArgumentNullException.ThrowIfNull(path);

        byte[] bytes;
        try
        {
            bytes = File.ReadAllBytes(path);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or FileNotFoundException)
        {
            throw new WavFormatException($"无法读取 WAV 文件“{path}”：{ex.Message}", ex);
        }

        return Read(bytes);
    }

    /// <summary>
    /// 从字节数据读取 WAV 并返回 <see cref="AudioClip"/>。
    /// </summary>
    /// <param name="data">完整的 WAV 文件字节内容。</param>
    /// <exception cref="ArgumentNullException"><paramref name="data"/> 为 null。</exception>
    /// <exception cref="WavFormatException">数据不是合法的 WAV，或使用了不支持的编码/声道配置。</exception>
    public static AudioClip Read(byte[] data)
    {
        ArgumentNullException.ThrowIfNull(data);

        if (data.Length < 12)
        {
            throw new WavFormatException("文件过小，不足以包含 RIFF/WAVE 头。");
        }

        // RIFF 头
        string riff = Encoding.ASCII.GetString(data, 0, 4);
        if (riff != "RIFF")
        {
            throw new WavFormatException("缺少 RIFF 标识，可能不是 WAV 文件。");
        }

        uint riffSize = BinaryPrimitives.ReadUInt32LittleEndian(data.AsSpan(4, 4));
        string wave = Encoding.ASCII.GetString(data, 8, 4);
        if (wave != "WAVE")
        {
            throw new WavFormatException("缺少 WAVE 标识，可能不是 WAV 文件。");
        }

        // 遍历 chunk
        int pos = 12;
        int fmtFormat = 0;
        int fmtChannels = 0;
        int fmtSampleRate = 0;
        int fmtBitsPerSample = 0;
        byte[]? dataChunk = null;
        int dataChunkOffset = 0;
        int dataChunkLength = 0;

        while (pos + 8 <= data.Length)
        {
            string chunkId = Encoding.ASCII.GetString(data, pos, 4);
            uint chunkSize = BinaryPrimitives.ReadUInt32LittleEndian(data.AsSpan(pos + 4, 4));
            int bodyOffset = pos + 8;

            // chunk 数据超出文件范围则截断处理
            if (chunkSize > (uint)(data.Length - bodyOffset))
            {
                if (chunkId == "data")
                {
                    // data chunk 声明长度超过实际文件，按实际可用长度处理
                    chunkSize = (uint)(data.Length - bodyOffset);
                }
                else
                {
                    throw new WavFormatException($"chunk “{chunkId}” 声明长度超出文件范围，文件可能已损坏。");
                }
            }

            switch (chunkId)
            {
                case "fmt ":
                    if (chunkSize < 16)
                    {
                        throw new WavFormatException("fmt chunk 长度不足，无法解析音频格式。");
                    }
                    fmtFormat = BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(bodyOffset, 2));
                    fmtChannels = BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(bodyOffset + 2, 2));
                    fmtSampleRate = (int)BinaryPrimitives.ReadUInt32LittleEndian(data.AsSpan(bodyOffset + 4, 4));
                    fmtBitsPerSample = BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(bodyOffset + 14, 2));

                    // WAVE_FORMAT_EXTENSIBLE 需要查看 SubFormat 的前 2 字节
                    if (fmtFormat == WaveFormatExtensible)
                    {
                        if (chunkSize < 40)
                        {
                            throw new WavFormatException("WAVE_FORMAT_EXTENSIBLE 的 fmt chunk 长度不足。");
                        }
                        // cbSize(2) + validBits(2) + channelMask(4) + SubFormat GUID(16)
                        // SubFormat 前 2 字节即为实际格式
                        int subFormatOffset = bodyOffset + 24;
                        fmtFormat = BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(subFormatOffset, 2));
                    }
                    break;

                case "data":
                    dataChunkOffset = bodyOffset;
                    dataChunkLength = (int)chunkSize;
                    dataChunk = data;
                    break;
            }

            // chunk 按 2 字节对齐
            long advance = 8 + (long)chunkSize + (chunkSize % 2);
            pos = (int)(pos + advance);
        }

        if (fmtFormat == 0)
        {
            throw new WavFormatException("未找到 fmt chunk，无法确定音频格式。");
        }

        if (dataChunk is null)
        {
            throw new WavFormatException("未找到 data chunk，文件中没有音频数据。");
        }

        if (fmtChannels != 1 && fmtChannels != 2)
        {
            throw new WavFormatException($"不支持的声道数：{fmtChannels}（仅支持 1 或 2）。");
        }

        if (fmtSampleRate <= 0)
        {
            throw new WavFormatException($"非法的采样率：{fmtSampleRate}。");
        }

        float[] samples = fmtFormat switch
        {
            WaveFormatPcm => DecodePcm(
                dataChunk.AsSpan(dataChunkOffset, dataChunkLength),
                fmtBitsPerSample, fmtChannels),
            WaveFormatIeeeFloat => DecodeFloat(
                dataChunk.AsSpan(dataChunkOffset, dataChunkLength),
                fmtBitsPerSample, fmtChannels),
            _ => throw new WavFormatException(
                $"不支持的编码格式：0x{fmtFormat:X4}（仅支持 PCM 与 IEEE float）。")
        };

        return new AudioClip(fmtSampleRate, fmtChannels, samples);
    }

    private static float[] DecodePcm(ReadOnlySpan<byte> span, int bitsPerSample, int channels)
    {
        switch (bitsPerSample)
        {
            case 16:
                {
                    int frameBytes = 2 * channels;
                    if (span.Length % frameBytes != 0)
                    {
                        throw new WavFormatException("data chunk 长度不是帧大小的整数倍，文件可能已损坏。");
                    }
                    int count = span.Length / 2;
                    var result = new float[count];
                    for (int i = 0; i < count; i++)
                    {
                        short s = BinaryPrimitives.ReadInt16LittleEndian(span.Slice(i * 2, 2));
                        result[i] = s / 32768f;
                    }
                    return result;
                }

            case 24:
                {
                    int frameBytes = 3 * channels;
                    if (span.Length % frameBytes != 0)
                    {
                        throw new WavFormatException("data chunk 长度不是帧大小的整数倍，文件可能已损坏。");
                    }
                    int count = span.Length / 3;
                    var result = new float[count];
                    for (int i = 0; i < count; i++)
                    {
                        int o = i * 3;
                        // 小端 24-bit 有符号整型
                        int v = span[o] | (span[o + 1] << 8) | (span[o + 2] << 16);
                        // 符号扩展
                        if ((v & 0x800000) != 0)
                        {
                            v |= unchecked((int)0xFF000000);
                        }
                        result[i] = v / 8388608f;
                    }
                    return result;
                }

            case 32:
                {
                    int frameBytes = 4 * channels;
                    if (span.Length % frameBytes != 0)
                    {
                        throw new WavFormatException("data chunk 长度不是帧大小的整数倍，文件可能已损坏。");
                    }
                    int count = span.Length / 4;
                    var result = new float[count];
                    for (int i = 0; i < count; i++)
                    {
                        int v = BinaryPrimitives.ReadInt32LittleEndian(span.Slice(i * 4, 4));
                        result[i] = (float)(v / 2147483648.0);
                    }
                    return result;
                }

            default:
                throw new WavFormatException($"不支持的 PCM 位深：{bitsPerSample} bit（仅支持 16/24/32）。");
        }
    }

    private static float[] DecodeFloat(ReadOnlySpan<byte> span, int bitsPerSample, int channels)
    {
        if (bitsPerSample != 32)
        {
            throw new WavFormatException($"不支持的 IEEE float 位深：{bitsPerSample} bit（仅支持 32）。");
        }

        int frameBytes = 4 * channels;
        if (span.Length % frameBytes != 0)
        {
            throw new WavFormatException("data chunk 长度不是帧大小的整数倍，文件可能已损坏。");
        }

        int count = span.Length / 4;
        var result = new float[count];
        for (int i = 0; i < count; i++)
        {
            int raw = BinaryPrimitives.ReadInt32LittleEndian(span.Slice(i * 4, 4));
            result[i] = BitConverter.Int32BitsToSingle(raw);
        }
        return result;
    }
}
