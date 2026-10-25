using System;
using System.IO;
using VoxLoom.Core.Audio;
using Xunit;

namespace VoxLoom.Core.Tests.Audio;

/// <summary>
/// 多轨选轨测试：偿还 TECH_DEBT TD-004（此前只取第一条音轨）。
/// fixture dual-tone.m4a：两条 AAC 单声道轨，轨 0 为 440Hz 正弦、轨 1 为 880Hz 正弦，各 2.0 秒、44100Hz。
/// 用过零率区分频率：纯正弦的过零率约为频率的 2 倍，AAC 编解码留宽容差。
/// </summary>
public class AudioTrackSelectionTests
{
    private static string Fixture(string name) =>
        Path.Combine(AppContext.BaseDirectory, "Fixtures", name);

    private static double ZeroCrossingRate(AudioClip clip)
    {
        long crossings = 0;
        for (int i = 1; i < clip.Samples.Length; i++)
        {
            if ((clip.Samples[i - 1] < 0) != (clip.Samples[i] < 0))
            {
                crossings++;
            }
        }

        return crossings / clip.Duration.TotalSeconds;
    }

    [Fact]
    public void ListAudioTracks_SingleTrackFlac_ReturnsOneTrack()
    {
        var tracks = FfmpegDecoder.ListAudioTracks(Fixture("tone.flac"));

        Assert.Single(tracks);
        Assert.Equal(0, tracks[0].AudioIndex);
        Assert.Equal(0, tracks[0].StreamIndex);
        Assert.Equal("flac", tracks[0].CodecName);
        Assert.Equal(44100, tracks[0].SampleRate);
        Assert.Equal(1, tracks[0].Channels);
    }

    [Fact]
    public void ListAudioTracks_NullPath_ThrowsArgumentNull()
    {
        Assert.Throws<ArgumentNullException>(() => FfmpegDecoder.ListAudioTracks(null!));
    }

    [Fact]
    public void ListAudioTracks_MissingFile_ThrowsAudioFormat()
    {
        var missing = Path.Combine(AppContext.BaseDirectory, "no-such-file-xyz.m4a");
        Assert.False(File.Exists(missing));
        Assert.Throws<AudioFormatException>(() => FfmpegDecoder.ListAudioTracks(missing));
    }

    [Fact]
    public void ListAudioTracks_DualToneM4a_ReturnsTwoTracks()
    {
        var tracks = FfmpegDecoder.ListAudioTracks(Fixture("dual-tone.m4a"));

        Assert.Equal(2, tracks.Count);
        Assert.Equal(0, tracks[0].AudioIndex);
        Assert.Equal(1, tracks[1].AudioIndex);
        Assert.Equal("aac", tracks[0].CodecName);
        Assert.Equal("aac", tracks[1].CodecName);
        Assert.Equal(44100, tracks[0].SampleRate);
        Assert.Equal(44100, tracks[1].SampleRate);
        Assert.Equal(1, tracks[0].Channels);
        Assert.Equal(1, tracks[1].Channels);
    }

    [Fact]
    public void Decode_TrackIndexOutOfRange_ThrowsAudioFormat()
    {
        var path = Fixture("dual-tone.m4a");
        Assert.Throws<AudioFormatException>(() => FfmpegDecoder.Decode(path, null, 2));
        Assert.Throws<AudioFormatException>(() => FfmpegDecoder.Decode(path, null, -1));
    }

    [Fact]
    public void Decode_DualTone_Track0_Is440Hz()
    {
        var clip = FfmpegDecoder.Decode(Fixture("dual-tone.m4a"), null, 0);

        Assert.Equal(44100, clip.SampleRate);
        Assert.True(clip.Samples.Length > 80000, $"samples={clip.Samples.Length}");
        Assert.InRange(ZeroCrossingRate(clip), 600, 1200);
    }

    [Fact]
    public void Decode_DualTone_Track1_Is880Hz()
    {
        var clip = FfmpegDecoder.Decode(Fixture("dual-tone.m4a"), null, 1);

        Assert.Equal(44100, clip.SampleRate);
        Assert.True(clip.Samples.Length > 80000, $"samples={clip.Samples.Length}");
        Assert.InRange(ZeroCrossingRate(clip), 1400, 2200);
    }

    [Fact]
    public void Import_DualTone_Track1_Is880Hz()
    {
        var clip = AudioImporter.Import(Fixture("dual-tone.m4a"), null, 1);

        Assert.Equal(44100, clip.SampleRate);
        Assert.InRange(ZeroCrossingRate(clip), 1400, 2200);
    }

    [Fact]
    public void Import_Wav_NonZeroTrack_ThrowsAudioFormat()
    {
        Assert.Throws<AudioFormatException>(() => AudioImporter.Import(Fixture("tone.wav"), null, 1));
    }
}
