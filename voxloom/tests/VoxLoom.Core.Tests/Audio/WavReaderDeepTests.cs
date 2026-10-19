using System;
using System.Buffers.Binary;
using System.Text;
using VoxLoom.Core.Audio;
using Xunit;

namespace VoxLoom.Core.Tests.Audio;

public class WavReaderDeepTests
{
    // 事实来源：WavReader.Read(string) 第一行 ArgumentNullException.ThrowIfNull(path)。
    [Fact]
    public void Read_StringNull_ThrowsArgumentNullException()
    {
        Assert.Throws<ArgumentNullException>(() => WavReader.Read((string)null!));
    }

    // 事实来源：WavReader.Read(byte[]) 第一行 ArgumentNullException.ThrowIfNull(data)。
    [Fact]
    public void Read_BytesNull_ThrowsArgumentNullException()
    {
        Assert.Throws<ArgumentNullException>(() => WavReader.Read((byte[])null!));
    }

    // 事实来源：Read(byte[]) 中 data.Length < 12 时抛 WavFormatException("文件过小...")。
    [Fact]
    public void Read_FileTooSmall_ThrowsWavFormatException()
    {
        byte[] bytes = new byte[11];
        Assert.Throws<WavFormatException>(() => WavReader.Read(bytes));
    }

    // 事实来源：Read 中 riff != "RIFF" 时抛 WavFormatException("缺少 RIFF 标识...")。
    [Fact]
    public void Read_NotRiff_ThrowsWavFormatException()
    {
        byte[] bytes = BuildWav(1, 1, 8000, 16, new byte[] { 0x00, 0x40 });
        Encoding.ASCII.GetBytes("RIFX").CopyTo(bytes, 0);
        Assert.Throws<WavFormatException>(() => WavReader.Read(bytes));
    }

    // 事实来源：Read 中 wave != "WAVE" 时抛 WavFormatException("缺少 WAVE 标识...")。
    [Fact]
    public void Read_RiffButNotWave_ThrowsWavFormatException()
    {
        byte[] bytes = BuildWav(1, 1, 8000, 16, new byte[] { 0x00, 0x40 });
        Encoding.ASCII.GetBytes("AVI ").CopyTo(bytes, 8);
        Assert.Throws<WavFormatException>(() => WavReader.Read(bytes));
    }

    // 事实来源：Read 中 fmtFormat == 0 检查（遍历后未找到 fmt chunk）抛 WavFormatException。
    [Fact]
    public void Read_MissingFmtChunk_ThrowsWavFormatException()
    {
        byte[] bytes = BuildWavWithoutFmt(new byte[] { 0x00, 0x40 });
        Assert.Throws<WavFormatException>(() => WavReader.Read(bytes));
    }

    // 事实来源：Read 中 dataChunk is null 检查（未找到 data chunk）抛 WavFormatException。
    [Fact]
    public void Read_MissingDataChunk_ThrowsWavFormatException()
    {
        byte[] bytes = BuildWavWithoutData(1, 1, 8000, 16);
        Assert.Throws<WavFormatException>(() => WavReader.Read(bytes));
    }

    // 事实来源：Read 中 case "fmt " 的 chunkSize < 16 检查抛 WavFormatException。
    [Fact]
    public void Read_FmtChunkTooShort_ThrowsWavFormatException()
    {
        byte[] bytes = BuildWavWithShortFmt(new byte[] { 0x00, 0x40 });
        Assert.Throws<WavFormatException>(() => WavReader.Read(bytes));
    }

    // 事实来源：Read 中 fmtChannels != 1 && != 2 时抛 WavFormatException。
    [Fact]
    public void Read_UnsupportedChannels_ThrowsWavFormatException()
    {
        byte[] bytes = BuildWav(1, 3, 8000, 16, new byte[] { 0x00, 0x40, 0x00, 0xC0, 0x00, 0x20 });
        Assert.Throws<WavFormatException>(() => WavReader.Read(bytes));
    }

    // 事实来源：Read 中 fmtSampleRate <= 0 时抛 WavFormatException。
    [Fact]
    public void Read_InvalidSampleRate_ThrowsWavFormatException()
    {
        byte[] bytes = BuildWav(1, 1, 0, 16, new byte[] { 0x00, 0x40 });
        Assert.Throws<WavFormatException>(() => WavReader.Read(bytes));
    }

    // 事实来源：Read 中 fmtFormat switch default 分支抛 $"不支持的编码格式：0x{fmtFormat:X4}"。
    [Fact]
    public void Read_UnsupportedFormat_Alaw_ThrowsWavFormatExceptionWithCode()
    {
        byte[] bytes = BuildWav(6, 1, 8000, 8, new byte[] { 0x00 });
        WavFormatException ex = Assert.Throws<WavFormatException>(() => WavReader.Read(bytes));
        Assert.Contains("0x0006", ex.Message);
    }

    // 事实来源：DecodePcm 24-bit 分支符号扩展 (v & 0x800000) 后 v |= 0xFF000000，除以 8388608f。
    [Fact]
    public void Read_Pcm24Bit_NegativeFullScale_ReturnsMinusOne()
    {
        byte[] bytes = BuildWav(1, 1, 8000, 24, new byte[] { 0x00, 0x00, 0x80 });
        AudioClip clip = WavReader.Read(bytes);
        Assert.Equal(-1.0f, clip.Samples[0], 6);
    }

    // 事实来源：DecodePcm 24-bit 分支 v / 8388608f，正的最大值 0x7FFFFF。
    [Fact]
    public void Read_Pcm24Bit_PositiveMax_ReturnsCorrectValue()
    {
        byte[] bytes = BuildWav(1, 1, 8000, 24, new byte[] { 0xFF, 0xFF, 0x7F });
        AudioClip clip = WavReader.Read(bytes);
        Assert.Equal(8388607f / 8388608f, clip.Samples[0], 6);
    }

    // 事实来源：DecodePcm 32-bit 分支 v / 2147483648.0，int.MinValue 为 -1.0。
    [Fact]
    public void Read_Pcm32Bit_MinValue_ReturnsMinusOne()
    {
        byte[] pcm = BitConverter.GetBytes(int.MinValue);
        byte[] bytes = BuildWav(1, 1, 8000, 32, pcm);
        AudioClip clip = WavReader.Read(bytes);
        Assert.Equal(-1.0f, clip.Samples[0], 6);
    }

    // 事实来源：DecodeFloat 分支 BitConverter.Int32BitsToSingle(raw) 读取 0.5f。
    [Fact]
    public void Read_IeeeFloat_ReturnsHalf()
    {
        byte[] pcm = BitConverter.GetBytes(0.5f);
        byte[] bytes = BuildWav(3, 1, 8000, 32, pcm);
        AudioClip clip = WavReader.Read(bytes);
        Assert.Equal(0.5f, clip.Samples[0], 6);
    }

    // 事实来源：DecodePcm 16-bit 分支按序解码 s / 32768f，Read 返回 AudioClip(fmtSampleRate, fmtChannels, samples)。
    [Fact]
    public void Read_Stereo16Bit_Interleaved_ReturnsExpectedSamples()
    {
        byte[] pcm = new byte[]
        {
            0x00, 0x40,
            0x00, 0xC0,
            0x00, 0x20,
            0x00, 0xE0
        };
        byte[] bytes = BuildWav(1, 2, 8000, 16, pcm);
        AudioClip clip = WavReader.Read(bytes);
        Assert.Equal(2, clip.Channels);
        Assert.Equal(4, clip.Samples.Length);
        Assert.Equal(0x4000 / 32768f, clip.Samples[0], 6);
        Assert.Equal(-0x4000 / 32768f, clip.Samples[1], 6);
        Assert.Equal(0x2000 / 32768f, clip.Samples[2], 6);
        Assert.Equal(-0x2000 / 32768f, clip.Samples[3], 6);
    }

    // 事实来源：Read 中 data chunk 声明长度超出文件时按实际可用长度截断，不抛异常。
    [Fact]
    public void Read_DataChunkDeclaredLongerThanFile_TruncatesToActualLength()
    {
        byte[] pcm = new byte[] { 0x00, 0x40, 0x00, 0xC0 };
        byte[] bytes = BuildWavWithDeclaredDataSize(1, 1, 8000, 16, pcm, 100);
        AudioClip clip = WavReader.Read(bytes);
        Assert.Equal(2, clip.Samples.Length);
        Assert.Equal(0x4000 / 32768f, clip.Samples[0], 6);
        Assert.Equal(-0x4000 / 32768f, clip.Samples[1], 6);
    }

    // 事实来源：Read 中 advance = 8 + chunkSize + (chunkSize % 2) 对奇数长度未知 chunk 做 2 字节对齐。
    [Fact]
    public void Read_OddLengthJunkChunk_SkipsWithPadding()
    {
        byte[] bytes = BuildWavWithJunk(new byte[] { 0x00, 0x40 }, 3);
        AudioClip clip = WavReader.Read(bytes);
        Assert.Equal(1, clip.Samples.Length);
        Assert.Equal(0x4000 / 32768f, clip.Samples[0], 6);
    }

    // 事实来源：DecodePcm 16-bit 分支 span.Length % frameBytes != 0 时抛 WavFormatException。
    [Fact]
    public void Read_DataLengthNotFrameMultiple_ThrowsWavFormatException()
    {
        byte[] bytes = BuildWav(1, 1, 8000, 16, new byte[] { 0x00, 0x40, 0x00 });
        Assert.Throws<WavFormatException>(() => WavReader.Read(bytes));
    }

    // 事实来源：Read 中 fmtFormat == WaveFormatExtensible 时读 subFormatOffset = bodyOffset + 24 的前 2 字节。
    [Fact]
    public void Read_ExtensiblePcm_ReturnsExpectedSample()
    {
        byte[] bytes = BuildExtensibleWav(new byte[] { 0x00, 0x40 });
        AudioClip clip = WavReader.Read(bytes);
        Assert.Equal(0x4000 / 32768f, clip.Samples[0], 6);
    }

    private static byte[] BuildWav(ushort format, ushort channels, uint rate, ushort bits, byte[] pcm)
    {
        return BuildWavWithDeclaredDataSize(format, channels, rate, bits, pcm, (uint)pcm.Length);
    }

    private static byte[] BuildWavWithDeclaredDataSize(ushort format, ushort channels, uint rate, ushort bits, byte[] pcm, uint declaredDataSize)
    {
        int totalSize = 44 + pcm.Length;
        byte[] bytes = new byte[totalSize];
        Encoding.ASCII.GetBytes("RIFF").CopyTo(bytes, 0);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(4, 4), (uint)(totalSize - 8));
        Encoding.ASCII.GetBytes("WAVE").CopyTo(bytes, 8);
        Encoding.ASCII.GetBytes("fmt ").CopyTo(bytes, 12);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(16, 4), 16);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(20, 2), format);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(22, 2), channels);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(24, 4), rate);
        uint byteRate = rate * (uint)channels * ((uint)bits / 8);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(28, 4), byteRate);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(32, 2), (ushort)(channels * (bits / 8)));
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(34, 2), bits);
        Encoding.ASCII.GetBytes("data").CopyTo(bytes, 36);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(40, 4), declaredDataSize);
        pcm.CopyTo(bytes, 44);
        return bytes;
    }

    private static byte[] BuildWavWithoutFmt(byte[] pcm)
    {
        int totalSize = 36 + pcm.Length;
        byte[] bytes = new byte[totalSize];
        Encoding.ASCII.GetBytes("RIFF").CopyTo(bytes, 0);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(4, 4), (uint)(totalSize - 8));
        Encoding.ASCII.GetBytes("WAVE").CopyTo(bytes, 8);
        Encoding.ASCII.GetBytes("data").CopyTo(bytes, 12);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(16, 4), (uint)pcm.Length);
        pcm.CopyTo(bytes, 20);
        return bytes;
    }

    private static byte[] BuildWavWithoutData(ushort format, ushort channels, uint rate, ushort bits)
    {
        int totalSize = 36;
        byte[] bytes = new byte[totalSize];
        Encoding.ASCII.GetBytes("RIFF").CopyTo(bytes, 0);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(4, 4), (uint)(totalSize - 8));
        Encoding.ASCII.GetBytes("WAVE").CopyTo(bytes, 8);
        Encoding.ASCII.GetBytes("fmt ").CopyTo(bytes, 12);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(16, 4), 16);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(20, 2), format);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(22, 2), channels);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(24, 4), rate);
        uint byteRate = rate * (uint)channels * ((uint)bits / 8);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(28, 4), byteRate);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(32, 2), (ushort)(channels * (bits / 8)));
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(34, 2), bits);
        return bytes;
    }

    private static byte[] BuildWavWithShortFmt(byte[] pcm)
    {
        int fmtBody = 10;
        int totalSize = 12 + 8 + fmtBody + 8 + pcm.Length;
        byte[] bytes = new byte[totalSize];
        Encoding.ASCII.GetBytes("RIFF").CopyTo(bytes, 0);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(4, 4), (uint)(totalSize - 8));
        Encoding.ASCII.GetBytes("WAVE").CopyTo(bytes, 8);
        Encoding.ASCII.GetBytes("fmt ").CopyTo(bytes, 12);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(16, 4), (uint)fmtBody);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(20, 2), 1);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(22, 2), 1);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(24, 4), 8000);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(28, 4), 16000);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(30, 2), 0);
        int dataPos = 20 + fmtBody;
        Encoding.ASCII.GetBytes("data").CopyTo(bytes, dataPos);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(dataPos + 4, 4), (uint)pcm.Length);
        pcm.CopyTo(bytes, dataPos + 8);
        return bytes;
    }

    private static byte[] BuildWavWithJunk(byte[] pcm, uint junkSize)
    {
        int junkTotal = 8 + (int)junkSize + (int)(junkSize % 2);
        int totalSize = 12 + 8 + 16 + junkTotal + 8 + pcm.Length;
        byte[] bytes = new byte[totalSize];
        Encoding.ASCII.GetBytes("RIFF").CopyTo(bytes, 0);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(4, 4), (uint)(totalSize - 8));
        Encoding.ASCII.GetBytes("WAVE").CopyTo(bytes, 8);
        Encoding.ASCII.GetBytes("fmt ").CopyTo(bytes, 12);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(16, 4), 16);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(20, 2), 1);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(22, 2), 1);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(24, 4), 8000);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(28, 4), 16000);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(32, 2), 2);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(34, 2), 16);
        int junkPos = 36;
        Encoding.ASCII.GetBytes("JUNK").CopyTo(bytes, junkPos);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(junkPos + 4, 4), junkSize);
        int dataPos = junkPos + junkTotal;
        Encoding.ASCII.GetBytes("data").CopyTo(bytes, dataPos);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(dataPos + 4, 4), (uint)pcm.Length);
        pcm.CopyTo(bytes, dataPos + 8);
        return bytes;
    }

    private static byte[] BuildExtensibleWav(byte[] pcm)
    {
        int fmtBody = 40;
        int totalSize = 12 + 8 + fmtBody + 8 + pcm.Length;
        byte[] bytes = new byte[totalSize];
        Encoding.ASCII.GetBytes("RIFF").CopyTo(bytes, 0);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(4, 4), (uint)(totalSize - 8));
        Encoding.ASCII.GetBytes("WAVE").CopyTo(bytes, 8);
        Encoding.ASCII.GetBytes("fmt ").CopyTo(bytes, 12);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(16, 4), (uint)fmtBody);
        int bodyOffset = 20;
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(bodyOffset, 2), 0xFFFE);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(bodyOffset + 2, 2), 1);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(bodyOffset + 4, 4), 8000);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(bodyOffset + 8, 4), 16000);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(bodyOffset + 12, 2), 2);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(bodyOffset + 14, 2), 16);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(bodyOffset + 16, 2), 22);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(bodyOffset + 18, 2), 16);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(bodyOffset + 20, 4), 0x4);
        BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(bodyOffset + 24, 2), 1);
        int dataPos = bodyOffset + fmtBody;
        Encoding.ASCII.GetBytes("data").CopyTo(bytes, dataPos);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(dataPos + 4, 4), (uint)pcm.Length);
        pcm.CopyTo(bytes, dataPos + 8);
        return bytes;
    }
}
