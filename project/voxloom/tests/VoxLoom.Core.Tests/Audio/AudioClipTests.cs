using VoxLoom.Core.Audio;
using Xunit;

namespace VoxLoom.Core.Tests.Audio;

public class AudioClipTests
{
    [Fact]
    public void Constructor_ComputesFramesAndDuration()
    {
        var clip = new AudioClip(48000, 2, new float[48000 * 2]);
        Assert.Equal(48000, clip.Frames);
        Assert.Equal(TimeSpan.FromSeconds(1), clip.Duration);
    }

    [Fact]
    public void Constructor_RejectsMismatchedSampleCount()
    {
        Assert.Throws<ArgumentException>(() => new AudioClip(44100, 2, new float[3]));
    }

    [Fact]
    public void GetMonoSamples_AveragesStereoChannels()
    {
        var clip = new AudioClip(44100, 2, new float[] { 1f, -1f, 0.5f, 0.5f });
        var mono = clip.GetMonoSamples();
        Assert.Equal(new[] { 0f, 0.5f }, mono);
    }

    [Fact]
    public void GetMonoSamples_ReturnsCopyForMonoInput()
    {
        var samples = new float[] { 0.1f, 0.2f, 0.3f };
        var clip = new AudioClip(44100, 1, samples);
        var mono = clip.GetMonoSamples();
        Assert.Equal(samples, mono);
        Assert.NotSame(samples, mono);
    }
}
