using System;
using VoxLoom.Core.Audio;
using Xunit;

namespace VoxLoom.Core.Tests.Audio
{
    public sealed class AudioClipDeepTests
    {
        [Fact]
        public void Constructor_NullSamples_ThrowsArgumentNull()
        {
            Assert.Throws<ArgumentNullException>(() => new AudioClip(44100, 1, null!));
        }

        [Fact]
        public void Constructor_ZeroSampleRate_ThrowsOutOfRange()
        {
            var ex = Assert.Throws<ArgumentOutOfRangeException>(
                () => new AudioClip(0, 1, new float[4]));
            Assert.Equal("sampleRate", ex.ParamName);
        }

        [Fact]
        public void Constructor_NegativeChannels_ThrowsOutOfRange()
        {
            var ex = Assert.Throws<ArgumentOutOfRangeException>(
                () => new AudioClip(44100, -2, new float[4]));
            Assert.Equal("channels", ex.ParamName);
        }

        [Fact]
        public void Constructor_FramesAndDuration_Math()
        {
            var clip = new AudioClip(16000, 1, new float[32000]);

            Assert.Equal(32000, clip.Frames);
            Assert.Equal(TimeSpan.FromSeconds(2.0), clip.Duration);
        }

        [Fact]
        public void GetMonoSamples_EmptyStereo_ReturnsEmpty()
        {
            var clip = new AudioClip(44100, 2, new float[0]);

            var mono = clip.GetMonoSamples();

            Assert.NotNull(mono);
            Assert.Empty(mono);
            Assert.Equal(0, mono.Length);
        }

        [Fact]
        public void GetMonoSamples_ThreeChannels_Averages()
        {
            var clip = new AudioClip(44100, 3, new[] { 1f, 2f, 3f });

            var mono = clip.GetMonoSamples();

            Assert.Single(mono);
            Assert.Equal(2.0f, mono[0]);
        }

        [Fact]
        public void GetMonoSamples_Stereo_ReturnsFreshArray()
        {
            var clip = new AudioClip(44100, 2, new[] { 1f, 3f, 5f, 7f });

            var first = clip.GetMonoSamples();
            var second = clip.GetMonoSamples();

            Assert.NotSame(first, second);

            first[0] = 123f;
            var third = clip.GetMonoSamples();

            Assert.Equal(2f, second[0]);
            Assert.Equal(2f, third[0]);
        }
    }
}
