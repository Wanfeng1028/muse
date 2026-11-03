using VoxLoom.Core.Audio;
using Xunit;

namespace VoxLoom.Core.Tests.Audio;

public class WavRoundTripTests
{
    [Fact]
    public void WriteThenRead_PreservesPcm16Mono()
    {
        int sampleRate = 16000;
        int channels = 1;
        var samples = new float[1600];
        for (int i = 0; i < samples.Length; i++)
        {
            samples[i] = MathF.Sin(2f * MathF.PI * 440f * i / sampleRate) * 0.5f;
        }

        var original = new AudioClip(sampleRate, channels, samples);

        string temp = Path.Combine(Path.GetTempPath(), $"voxloom-{Guid.NewGuid():N}.wav");
        try
        {
            WavWriter.Write(temp, original);
            var roundTripped = WavReader.Read(temp);

            Assert.Equal(sampleRate, roundTripped.SampleRate);
            Assert.Equal(channels, roundTripped.Channels);
            Assert.Equal(original.Frames, roundTripped.Frames);

            for (int i = 0; i < samples.Length; i++)
            {
                Assert.InRange(Math.Abs(samples[i] - roundTripped.Samples[i]), 0f, 1f / 32767f + 1e-6f);
            }
        }
        finally
        {
            if (File.Exists(temp))
            {
                File.Delete(temp);
            }
        }
    }

    [Fact]
    public void Read_RejectsNonRiffData()
    {
        var data = new byte[32];
        Assert.Throws<WavFormatException>(() => WavReader.Read(data));
    }
}
