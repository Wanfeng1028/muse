using System;
using System.IO;
using VoxLoom.Core.Audio;
using Xunit;

namespace VoxLoom.Core.Tests.Audio;

public class AudioImporterDetectDeepTests
{
    // 事实来源：AudioImporter.DetectByMagic 中 head.Length >= 3 且前三字节 "ID3" 返回 AudioFormat.Mp3，且 DetectFormat 中 byMagic 命中优先于扩展名。
    [Fact]
    public void DetectFormat_Id3Magic_WithTxtExtension_ReturnsMp3()
    {
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".txt");
        try
        {
            File.WriteAllBytes(path, new byte[] { (byte)'I', (byte)'D', (byte)'3', 0x00, 0x00, 0x00 });
            var result = AudioImporter.DetectFormat(path);
            Assert.Equal(AudioFormat.Mp3, result);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：AudioImporter.DetectByMagic 中 head.Length >= 4 且前四字节 "fLaC" 返回 AudioFormat.Flac。
    [Fact]
    public void DetectFormat_FlacMagic_WithBinExtension_ReturnsFlac()
    {
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".bin");
        try
        {
            File.WriteAllBytes(path, new byte[] { (byte)'f', (byte)'L', (byte)'a', (byte)'C', 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 });
            var result = AudioImporter.DetectFormat(path);
            Assert.Equal(AudioFormat.Flac, result);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：AudioImporter.DetectByMagic 中 head.Length >= 2 且 head[0]==0xFF 且 head[1]==0xFB 返回 AudioFormat.Mp3。
    [Fact]
    public void DetectFormat_FrameSync0xFFFB_WithDatExtension_ReturnsMp3()
    {
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".dat");
        try
        {
            File.WriteAllBytes(path, new byte[] { 0xFF, 0xFB, 0x00, 0x00, 0x00, 0x00 });
            var result = AudioImporter.DetectFormat(path);
            Assert.Equal(AudioFormat.Mp3, result);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：AudioImporter.DetectByMagic 中 head.Length >= 8 且第 4-7 字节为 "ftyp" 返回 AudioFormat.M4a。
    [Fact]
    public void DetectFormat_FtypAtOffset4_WithBinExtension_ReturnsM4a()
    {
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".bin");
        try
        {
            File.WriteAllBytes(path, new byte[] { 0x00, 0x00, 0x00, 0x00, (byte)'f', (byte)'t', (byte)'y', (byte)'p', 0x00, 0x00, 0x00, 0x00 });
            var result = AudioImporter.DetectFormat(path);
            Assert.Equal(AudioFormat.M4a, result);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：AudioImporter.DetectByMagic 中 head.Length >= 12 且前四字节 "RIFF" 且 8-11 字节 "WAVE" 返回 AudioFormat.Wav。
    [Fact]
    public void DetectFormat_RiffWaveMagic_WithBinExtension_ReturnsWav()
    {
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".bin");
        try
        {
            File.WriteAllBytes(path, new byte[] { (byte)'R', (byte)'I', (byte)'F', (byte)'F', 0x00, 0x00, 0x00, 0x00, (byte)'W', (byte)'A', (byte)'V', (byte)'E' });
            var result = AudioImporter.DetectFormat(path);
            Assert.Equal(AudioFormat.Wav, result);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：AudioImporter.DetectFormat 中 byMagic 命中直接返回，不再看扩展名。
    [Fact]
    public void DetectFormat_FlacMagic_WithWavExtension_MagicWins_ReturnsFlac()
    {
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".wav");
        try
        {
            File.WriteAllBytes(path, new byte[] { (byte)'f', (byte)'L', (byte)'a', (byte)'C', 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 });
            var result = AudioImporter.DetectFormat(path);
            Assert.Equal(AudioFormat.Flac, result);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：AudioImporter.DetectByExtension 使用 ext.ToLowerInvariant() 做大小写不敏感匹配。
    [Fact]
    public void DetectFormat_UppercaseWavExtension_WithGarbage_ReturnsWav()
    {
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".WAV");
        try
        {
            File.WriteAllBytes(path, new byte[] { 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C });
            var result = AudioImporter.DetectFormat(path);
            Assert.Equal(AudioFormat.Wav, result);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：AudioImporter.DetectFormat 中 byMagic 与 byExt 均为 null 时抛出 AudioFormatException。
    [Fact]
    public void DetectFormat_GarbageContent_NoExtension_ThrowsAudioFormatException()
    {
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));
        try
        {
            File.WriteAllBytes(path, new byte[] { 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C });
            Assert.Throws<AudioFormatException>(() => AudioImporter.DetectFormat(path));
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：AudioImporter.DetectFormat 中 path is null 时抛出 ArgumentNullException。
    [Fact]
    public void DetectFormat_NullPath_ThrowsArgumentNullException()
    {
        Assert.Throws<ArgumentNullException>(() => AudioImporter.DetectFormat(null!));
    }

    // 事实来源：AudioImporter.DetectFormat 中 !File.Exists(path) 分支抛出 AudioFormatException。
    [Fact]
    public void DetectFormat_NonExistentFile_ThrowsAudioFormatException()
    {
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".wav");
        Assert.Throws<AudioFormatException>(() => AudioImporter.DetectFormat(path));
    }

    // 事实来源：AudioImporter.DetectFormat 中 head 被 Resize 为实际长度 0，魔数全失败后走扩展名兜底 .mp3。
    [Fact]
    public void DetectFormat_EmptyFile_WithMp3Extension_ReturnsMp3()
    {
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".mp3");
        try
        {
            File.WriteAllBytes(path, Array.Empty<byte>());
            var result = AudioImporter.DetectFormat(path);
            Assert.Equal(AudioFormat.Mp3, result);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：AudioImporter.OpenFileFilter 字符串常量包含 "*.wav" 与 "*.mp3"。
    [Fact]
    public void OpenFileFilter_ContainsWavAndMp3Patterns()
    {
        Assert.Contains("*.wav", AudioImporter.OpenFileFilter);
        Assert.Contains("*.mp3", AudioImporter.OpenFileFilter);
    }

    // 事实来源：AudioImporter.DetectByMagic 要求 head[8..11]=="WAVE"，不满足则魔数失败，DetectFormat 走扩展名兜底 .mp3。
    [Fact]
    public void DetectFormat_RiffNonWave_WithMp3Extension_ReturnsMp3()
    {
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".mp3");
        try
        {
            File.WriteAllBytes(path, new byte[] { (byte)'R', (byte)'I', (byte)'F', (byte)'F', 0x00, 0x00, 0x00, 0x00, (byte)'X', (byte)'X', (byte)'X', (byte)'X' });
            var result = AudioImporter.DetectFormat(path);
            Assert.Equal(AudioFormat.Mp3, result);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }
}