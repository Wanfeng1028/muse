using System;
using System.IO;
using Xunit;
using VoxLoom.Core.Audio;

namespace VoxLoom.Core.Tests.Audio;

public class WavWriterDeepTests
{
    private static string TempWavPath()
    {
        return Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".wav");
    }

    // 事实来源：FloatToInt16 使用 Math.Round(value * 32767.0, AwayFromZero) 量化，读回 16-bit PCM 应近似原值。
    [Fact]
    public void Write_RoundTrip_16BitPcm_PreservesSamplesWithinQuantization()
    {
        string path = TempWavPath();
        try
        {
            var clip = new AudioClip(8000, 1, new[] { 0.5f, -0.5f, 0.0f });
            WavWriter.Write(path, clip);

            var read = WavReader.Read(path);

            Assert.Equal(3, read.Samples.Length);
            float tolerance = 1f / 32767f + 1e-6f;
            Assert.True(Math.Abs(read.Samples[0] - 0.5f) < tolerance);
            Assert.True(Math.Abs(read.Samples[1] - (-0.5f)) < tolerance);
            Assert.True(Math.Abs(read.Samples[2] - 0.0f) < tolerance);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：FloatToInt16 中 float.IsNaN(value) 返回 0。
    [Fact]
    public void Write_NaN_SaturatesToZero()
    {
        string path = TempWavPath();
        try
        {
            var clip = new AudioClip(8000, 1, new[] { float.NaN });
            WavWriter.Write(path, clip);

            var read = WavReader.Read(path);

            Assert.Equal(0f, read.Samples[0]);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：FloatToInt16 中 value >= 1f 返回 short.MaxValue，读回时 /32768f。
    [Fact]
    public void Write_AboveUpperBound_SaturatesToShortMaxValue()
    {
        string path = TempWavPath();
        try
        {
            var clip = new AudioClip(8000, 1, new[] { 1.5f });
            WavWriter.Write(path, clip);

            var read = WavReader.Read(path);

            Assert.Equal(32767f / 32768f, read.Samples[0]);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：FloatToInt16 中 value <= -1f 返回 short.MinValue，读回时 /32768f 得 -1.0f。
    [Fact]
    public void Write_BelowLowerBound_SaturatesToShortMinValue()
    {
        string path = TempWavPath();
        try
        {
            var clip = new AudioClip(8000, 1, new[] { -2.0f });
            WavWriter.Write(path, clip);

            var read = WavReader.Read(path);

            Assert.Equal(-1.0f, read.Samples[0]);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：FloatToInt16 中 value >= 1f 与 value <= -1f 分别返回 short.MaxValue / short.MinValue。
    [Fact]
    public void Write_ExactBounds_MapToShortMaxAndMin()
    {
        string path = TempWavPath();
        try
        {
            var clip = new AudioClip(8000, 1, new[] { 1.0f, -1.0f });
            WavWriter.Write(path, clip);

            var read = WavReader.Read(path);

            Assert.Equal(32767f / 32768f, read.Samples[0]);
            Assert.Equal(-1.0f, read.Samples[1]);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：Write 按 clip.Samples 顺序逐样本写入 data chunk，声道数与交错顺序被保留。
    [Fact]
    public void Write_Stereo_RoundTrip_PreservesChannelsAndInterleaving()
    {
        string path = TempWavPath();
        try
        {
            var clip = new AudioClip(44100, 2, new[] { 0.25f, -0.25f, 0.75f, -0.75f });
            WavWriter.Write(path, clip);

            var read = WavReader.Read(path);

            Assert.Equal(2, read.Channels);
            Assert.Equal(4, read.Samples.Length);
            float tolerance = 1f / 32767f + 1e-6f;
            Assert.True(Math.Abs(read.Samples[0] - 0.25f) < tolerance);
            Assert.True(Math.Abs(read.Samples[1] - (-0.25f)) < tolerance);
            Assert.True(Math.Abs(read.Samples[2] - 0.75f) < tolerance);
            Assert.True(Math.Abs(read.Samples[3] - (-0.75f)) < tolerance);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：Write 通过 WriteAscii 依次写入 "RIFF"、"WAVE"、"fmt " 于固定偏移。
    [Fact]
    public void Write_Header_ContainsRiffWaveFmtMarkers()
    {
        string path = TempWavPath();
        try
        {
            var clip = new AudioClip(8000, 1, new[] { 0.0f });
            WavWriter.Write(path, clip);

            byte[] bytes = File.ReadAllBytes(path);

            Assert.Equal("RIFF", System.Text.Encoding.ASCII.GetString(bytes, 0, 4));
            Assert.Equal("WAVE", System.Text.Encoding.ASCII.GetString(bytes, 8, 4));
            Assert.Equal("fmt ", System.Text.Encoding.ASCII.GetString(bytes, 12, 4));
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：Write 中 ArgumentNullException.ThrowIfNull(path)。
    [Fact]
    public void Write_NullPath_ThrowsArgumentNullException()
    {
        var clip = new AudioClip(8000, 1, new[] { 0.0f });

        Assert.Throws<ArgumentNullException>(() => WavWriter.Write(null!, clip));
    }

    // 事实来源：Write 中 ArgumentNullException.ThrowIfNull(clip)。
    [Fact]
    public void Write_NullClip_ThrowsArgumentNullException()
    {
        string path = TempWavPath();
        try
        {
            Assert.Throws<ArgumentNullException>(() => WavWriter.Write(path, null!));
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：Write 中 sampleCount = clip.Samples.Length，dataSize = 0 时仍写出合法头与空 data chunk。
    [Fact]
    public void Write_EmptySamples_ProducesZeroLengthRoundTrip()
    {
        string path = TempWavPath();
        try
        {
            var clip = new AudioClip(8000, 1, Array.Empty<float>());
            WavWriter.Write(path, clip);

            var read = WavReader.Read(path);

            Assert.Equal(0, read.Samples.Length);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    // 事实来源：FloatToInt16 中 Math.Round(0.1 * 32767.0, MidpointRounding.AwayFromZero) 精确量化。
    [Fact]
    public void Write_PointOne_QuantizesWithAwayFromZeroRounding()
    {
        string path = TempWavPath();
        try
        {
            var clip = new AudioClip(8000, 1, new[] { 0.1f });
            WavWriter.Write(path, clip);

            var read = WavReader.Read(path);

            float expected = (float)Math.Round(0.1 * 32767.0, MidpointRounding.AwayFromZero) / 32768f;
            Assert.Equal(expected, read.Samples[0]);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }
}
