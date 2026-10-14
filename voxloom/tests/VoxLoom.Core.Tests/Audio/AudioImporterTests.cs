using System;
using System.IO;
using VoxLoom.Core.Audio;
using Xunit;

namespace VoxLoom.Core.Tests.Audio;

public class AudioImporterTests
{
    private static string Fixture(string name) =>
        Path.Combine(AppContext.BaseDirectory, "Fixtures", name);

    private static string NewTmpDir()
    {
        var dir = Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        Directory.CreateDirectory(dir);
        return dir;
    }

    private static double MeanAbs(float[] samples, int count)
    {
        int n = Math.Min(count, samples.Length);
        if (n == 0) return 0.0;
        double sum = 0;
        for (int i = 0; i < n; i++) sum += Math.Abs(samples[i]);
        return sum / n;
    }

    [Fact]
    public void DetectFormat_KnownFiles()
    {
        Assert.Equal(AudioFormat.Wav, AudioImporter.DetectFormat(Fixture("tone.wav")));
        Assert.Equal(AudioFormat.Mp3, AudioImporter.DetectFormat(Fixture("tone.mp3")));
        Assert.Equal(AudioFormat.Flac, AudioImporter.DetectFormat(Fixture("tone.flac")));
        Assert.Equal(AudioFormat.M4a, AudioImporter.DetectFormat(Fixture("tone.m4a")));
    }

    [Fact]
    public void Import_Wav_StillWorks()
    {
        var clip = AudioImporter.Import(Fixture("tone.wav"));
        Assert.Equal(88200, clip.Frames);
        Assert.Equal(44100, clip.SampleRate);
        Assert.True(MeanAbs(clip.Samples, 44100) > 0.3);
    }

    [Fact]
    public void Import_Mp3_DecodesRealAudio()
    {
        var clip = AudioImporter.Import(Fixture("tone.mp3"));
        Assert.Equal(44100, clip.SampleRate);
        Assert.True(clip.Channels == 1 || clip.Channels == 2, $"Channels={clip.Channels}");
        Assert.InRange(clip.Frames, 88200, 95000);
        Assert.True(MeanAbs(clip.Samples, 44100) > 0.3);
    }

    [Fact]
    public void Import_Flac_DecodesRealAudio()
    {
        var clip = AudioImporter.Import(Fixture("tone.flac"));
        Assert.Equal(88200, clip.Frames);
        Assert.True(MeanAbs(clip.Samples, 44100) > 0.3);
    }

    [Fact]
    public void Import_M4a_DecodesRealAudio()
    {
        var clip = AudioImporter.Import(Fixture("tone.m4a"));
        Assert.Equal(44100, clip.SampleRate);
        Assert.InRange(clip.Frames, 88200, 95000);
        Assert.True(MeanAbs(clip.Samples, 44100) > 0.3);
    }

    [Fact]
    public void DetectFormat_UnknownFile_Throws()
    {
        var dir = NewTmpDir();
        try
        {
            var path = Path.Combine(dir, "garbage.xyz");
            var bytes = new byte[256];
            new Random(42).NextBytes(bytes);
            File.WriteAllBytes(path, bytes);
            Assert.Throws<AudioFormatException>(() => AudioImporter.DetectFormat(path));
        }
        finally
        {
            try { Directory.Delete(dir, true); } catch { }
        }
    }

    [Fact]
    public void Import_NullPath_ThrowsArgumentNull()
    {
        Assert.Throws<ArgumentNullException>(() => AudioImporter.Import(null!));
    }

    [Fact]
    public void Import_MissingFile_ThrowsAudioFormatException()
    {
        var missing = Path.Combine(AppContext.BaseDirectory, "test-missing-" + Guid.NewGuid().ToString("N") + ".wav");
        Assert.Throws<AudioFormatException>(() => AudioImporter.Import(missing));
    }

    [Fact]
    public void FfmpegDecoder_IsAvailable_ReturnsTrue()
    {
        Assert.True(FfmpegDecoder.IsAvailable());
    }

    [Fact]
    public void FfmpegDecoder_BogusPath_ThrowsHelpfulMessage()
    {
        var ex = Assert.Throws<AudioFormatException>(() =>
            FfmpegDecoder.Decode(Fixture("tone.flac"), "/nonexistent/ffmpeg-xyz"));
        Assert.Contains("ffmpeg", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ResolveFfmpegPath_Priority()
    {
        var old = Environment.GetEnvironmentVariable("VOXLOOM_FFMPEG_PATH");
        try
        {
            Environment.SetEnvironmentVariable("VOXLOOM_FFMPEG_PATH", null);
            Assert.Equal("/explicit/ffmpeg", FfmpegDecoder.ResolveFfmpegPath("/explicit/ffmpeg"));

            Environment.SetEnvironmentVariable("VOXLOOM_FFMPEG_PATH", "/env/ffmpeg");
            Assert.Equal("/env/ffmpeg", FfmpegDecoder.ResolveFfmpegPath(null));

            Assert.Equal("/explicit/ffmpeg", FfmpegDecoder.ResolveFfmpegPath("/explicit/ffmpeg"));

            Environment.SetEnvironmentVariable("VOXLOOM_FFMPEG_PATH", null);
            Assert.Equal("ffmpeg", FfmpegDecoder.ResolveFfmpegPath(null));
        }
        finally
        {
            Environment.SetEnvironmentVariable("VOXLOOM_FFMPEG_PATH", old);
        }
    }

    [Fact]
    public void FormatDisplayName_AllFormats()
    {
        Assert.Equal("WAV", AudioImporter.FormatDisplayName(AudioFormat.Wav));
        Assert.Equal("MP3", AudioImporter.FormatDisplayName(AudioFormat.Mp3));
        Assert.Equal("FLAC", AudioImporter.FormatDisplayName(AudioFormat.Flac));
        Assert.Equal("M4A", AudioImporter.FormatDisplayName(AudioFormat.M4a));
    }
}
