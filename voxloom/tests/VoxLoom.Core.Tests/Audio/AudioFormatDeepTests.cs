using System;
using System.Linq;
using VoxLoom.Core.Audio;
using Xunit;

namespace VoxLoom.Core.Tests.Audio;

public class AudioFormatDeepTests
{
    // 事实来源：AudioFormat 源码只定义了 Wav/Mp3/Flac/M4a 四个成员。
    [Fact]
    public void AudioFormat_HasExactlyFourMembers()
    {
        var values = Enum.GetValues<AudioFormat>();
        Assert.Equal(4, values.Length);
    }

    // 事实来源：AudioFormat 枚举成员采用默认递增赋值，底层值互不相同。
    [Fact]
    public void AudioFormat_UnderlyingValues_AreDistinct()
    {
        var values = Enum.GetValues<AudioFormat>().Cast<int>().ToArray();
        Assert.Equal(values.Length, values.Distinct().Count());
    }

    // 事实来源：AudioFormat 源码定义了名为 Mp3 的成员。
    [Fact]
    public void EnumParse_Mp3_ReturnsMp3Member()
    {
        Assert.Equal(AudioFormat.Mp3, Enum.Parse<AudioFormat>("Mp3"));
    }

    // 事实来源：AudioFormat 源码定义了名为 Flac 的成员。
    [Fact]
    public void EnumParse_Flac_ReturnsFlacMember()
    {
        Assert.Equal(AudioFormat.Flac, Enum.Parse<AudioFormat>("Flac"));
    }

    // 事实来源：AudioFormat 源码定义了名为 M4a 的成员。
    [Fact]
    public void EnumParse_M4a_ReturnsM4aMember()
    {
        Assert.Equal(AudioFormat.M4a, Enum.Parse<AudioFormat>("M4a"));
    }

    // 事实来源：AudioFormat 源码定义了名为 Wav 的成员。
    [Fact]
    public void EnumParse_Wav_ReturnsWavMember()
    {
        Assert.Equal(AudioFormat.Wav, Enum.Parse<AudioFormat>("Wav"));
    }

    // 事实来源：枚举成员名即其 ToString 往返字符串。
    [Fact]
    public void ToString_RoundTrip_Wav()
    {
        Assert.Equal("Wav", AudioFormat.Wav.ToString());
    }

    // 事实来源：枚举成员名即其 ToString 往返字符串。
    [Fact]
    public void ToString_RoundTrip_Mp3()
    {
        Assert.Equal("Mp3", AudioFormat.Mp3.ToString());
    }

    // 事实来源：枚举成员名即其 ToString 往返字符串。
    [Fact]
    public void ToString_RoundTrip_Flac()
    {
        Assert.Equal("Flac", AudioFormat.Flac.ToString());
    }

    // 事实来源：枚举成员名即其 ToString 往返字符串。
    [Fact]
    public void ToString_RoundTrip_M4a()
    {
        Assert.Equal("M4a", AudioFormat.M4a.ToString());
    }

    // 事实来源：AudioFormat 源码定义了名为 Wav 的成员，故 IsDefined 为 true。
    [Fact]
    public void IsDefined_Wav_ReturnsTrue()
    {
        Assert.True(Enum.IsDefined(typeof(AudioFormat), "Wav"));
    }

    // 事实来源：AudioFormat 源码未定义 Aac 成员，故 IsDefined 为 false。
    [Fact]
    public void IsDefined_Aac_ReturnsFalse()
    {
        Assert.False(Enum.IsDefined(typeof(AudioFormat), "Aac"));
    }

    // 事实来源：AudioImporter.OpenFileFilter 包含 *.wav;*.mp3;*.flac;*.m4a 全部扩展名。
    [Fact]
    public void OpenFileFilter_ContainsAllFourExtensions()
    {
        var filter = AudioImporter.OpenFileFilter;
        Assert.Contains("*.wav", filter);
        Assert.Contains("*.mp3", filter);
        Assert.Contains("*.flac", filter);
        Assert.Contains("*.m4a", filter);
    }

    // 事实来源：AudioImporter.FormatDisplayName 的 switch 对 Wav 返回 "WAV"。
    [Fact]
    public void FormatDisplayName_Wav_ReturnsWAV()
    {
        Assert.Equal("WAV", AudioImporter.FormatDisplayName(AudioFormat.Wav));
    }

    // 事实来源：AudioImporter.FormatDisplayName 的 switch 对 Mp3 返回 "MP3"。
    [Fact]
    public void FormatDisplayName_Mp3_ReturnsMP3()
    {
        Assert.Equal("MP3", AudioImporter.FormatDisplayName(AudioFormat.Mp3));
    }

    // 事实来源：AudioImporter.FormatDisplayName 的 switch 对 Flac 返回 "FLAC"。
    [Fact]
    public void FormatDisplayName_Flac_ReturnsFLAC()
    {
        Assert.Equal("FLAC", AudioImporter.FormatDisplayName(AudioFormat.Flac));
    }

    // 事实来源：AudioImporter.FormatDisplayName 的 switch 对 M4a 返回 "M4A"。
    [Fact]
    public void FormatDisplayName_M4a_ReturnsM4A()
    {
        Assert.Equal("M4A", AudioImporter.FormatDisplayName(AudioFormat.M4a));
    }
}