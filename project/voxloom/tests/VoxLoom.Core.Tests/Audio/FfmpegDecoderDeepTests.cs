using System;
using System.IO;
using System.Linq;
using VoxLoom.Core.Audio;
using Xunit;

namespace VoxLoom.Core.Tests.Audio;

public class FfmpegDecoderDeepTests
{
    private static string Fixture(string name) =>
        Path.Combine(AppContext.BaseDirectory, "Fixtures", name);

    [Fact]
    public void IsAvailable_BogusPath_ReturnsFalse()
    {
        // 源码 IsAvailable 内部捕获所有异常并返回 false；
        // 传入不存在的 ffmpeg 路径必然失败（进程无法启动），故期望 false。
        Assert.False(FfmpegDecoder.IsAvailable("/nonexistent/ffmpeg-xyz"));
    }

    [Fact]
    public void Decode_NullPath_ThrowsArgumentNull()
    {
        // 源码：path 为 null → ArgumentNullException。
        Assert.Throws<ArgumentNullException>(() => FfmpegDecoder.Decode(null!));
    }

    [Fact]
    public void Decode_MissingFile_ThrowsAudioFormat()
    {
        // 源码：文件不存在 → AudioFormatException。
        var missing = Path.Combine(AppContext.BaseDirectory, "no-such-file-xyz.flac");
        Assert.False(File.Exists(missing));
        Assert.Throws<AudioFormatException>(() => FfmpegDecoder.Decode(missing));
    }

    [Fact]
    public void Decode_Flac_RealDecode()
    {
        // fixture tone.flac：44100Hz 单声道 2.0s。
        // 期望帧数 = 2.0 * 44100 = 88200；留编解码帧对齐余量 [88100, 88300]。
        var clip = FfmpegDecoder.Decode(Fixture("tone.flac"));

        Assert.Equal(44100, clip.SampleRate);
        Assert.Equal(1, clip.Channels);
        Assert.InRange(clip.Samples.Length, 88100, 88300);
        Assert.Equal(2.0, clip.Duration.TotalSeconds, 2);
    }

    [Fact]
    public void Decode_Flac_SamplesAreRealAudio()
    {
        // 440Hz 正弦不可能全静音；取绝对值最大应显著大于 0.1。
        var clip = FfmpegDecoder.Decode(Fixture("tone.flac"));

        var peak = clip.Samples.Max(s => Math.Abs(s));
        Assert.True(peak > 0.1f, $"expected peak > 0.1, got {peak}");
    }

    [Fact]
    public void Decode_M4a_RealDecode()
    {
        // fixture tone.m4a：44100Hz 单声道 2.0s；AAC 允许填充帧，不做精确长度断言。
        var clip = FfmpegDecoder.Decode(Fixture("tone.m4a"));

        Assert.Equal(44100, clip.SampleRate);
        Assert.Equal(1, clip.Channels);
        Assert.True(clip.Samples.Length > 80000, $"samples={clip.Samples.Length}");
        Assert.InRange(clip.Duration.TotalSeconds, 1.9, 2.1);
    }

    [Fact]
    public void ResolveFfmpegPath_WhitespaceConfiguredPath_FallsThrough()
    {
        // 源码：IsNullOrWhiteSpace(configuredPath) 为真时穿透到环境变量。
        // 环境变量设置时返回环境变量；清空后返回默认 "ffmpeg"。
        var original = Environment.GetEnvironmentVariable("VOXLOOM_FFMPEG_PATH");
        try
        {
            Environment.SetEnvironmentVariable("VOXLOOM_FFMPEG_PATH", "/env/ffmpeg");
            Assert.Equal("/env/ffmpeg", FfmpegDecoder.ResolveFfmpegPath("   "));

            Environment.SetEnvironmentVariable("VOXLOOM_FFMPEG_PATH", null);
            Assert.Equal("ffmpeg", FfmpegDecoder.ResolveFfmpegPath("\t"));
        }
        finally
        {
            Environment.SetEnvironmentVariable("VOXLOOM_FFMPEG_PATH", original);
        }
    }

    [Fact]
    public void IsAvailable_EnvVarPath_Respected()
    {
        // 源码：configuredPath 为 null 时回落到环境变量 VOXLOOM_FFMPEG_PATH。
        // 指向真实 /usr/bin/ffmpeg，应可用。
        var original = Environment.GetEnvironmentVariable("VOXLOOM_FFMPEG_PATH");
        try
        {
            Environment.SetEnvironmentVariable("VOXLOOM_FFMPEG_PATH", "/usr/bin/ffmpeg");
            Assert.True(FfmpegDecoder.IsAvailable(null));
        }
        finally
        {
            Environment.SetEnvironmentVariable("VOXLOOM_FFMPEG_PATH", original);
        }
    }
}
