using System;
using VoxLoom.Core.Audio;
using Xunit;

namespace VoxLoom.Core.Tests.Audio;

// 依据：Audio/AudioFormatException.cs 与 Audio/WavFormatException.cs 的事实来源，
// 两个类型均只暴露 (string message) 与 (string message, Exception innerException) 两个构造器，
// 且都直接继承自 System.Exception。测试只调用这两个真实存在的构造器。
public class AudioExceptionDeepTests
{
    // 依据用例 1：AudioFormatException(string message) 构造器，Message 应等于传入的 message。
    [Fact]
    public void AudioFormatException_Message_Preserved()
    {
        var ex = new AudioFormatException("oops");
        Assert.Equal("oops", ex.Message);
    }

    // 依据用例 2：AudioFormatException(string message, Exception innerException) 构造器，
    // Message 保留为传入 message，InnerException 应为同一个实例（引用相等）。
    [Fact]
    public void AudioFormatException_Inner_Preserved()
    {
        var inner = new InvalidOperationException("root");
        var ex = new AudioFormatException("wrap", inner);
        Assert.Equal("wrap", ex.Message);
        Assert.Same(inner, ex.InnerException);
    }

    // 依据用例 3：AudioFormatException 继承自 Exception，应可赋值给 Exception。
    [Fact]
    public void AudioFormatException_IsException()
    {
        var ex = new AudioFormatException("x");
        Assert.IsAssignableFrom<Exception>(ex);
    }

    // 依据用例 4：抛出 AudioFormatException 后，Assert.Throws 应能按类型精确捕获。
    [Fact]
    public void AudioFormatException_Catchable()
    {
        Action act = () => { throw new AudioFormatException("x"); };
        var caught = Assert.Throws<AudioFormatException>(act);
        Assert.Equal("x", caught.Message);
    }

    // 依据用例 5：WavFormatException(string message) 构造器，Message 应等于传入的 message。
    [Fact]
    public void WavFormatException_Message_Preserved()
    {
        var ex = new WavFormatException("oops");
        Assert.Equal("oops", ex.Message);
    }

    // 依据用例 6：WavFormatException(string message, Exception innerException) 构造器，
    // Message 保留为传入 message，InnerException 应为同一个实例（引用相等）。
    [Fact]
    public void WavFormatException_Inner_Preserved()
    {
        var inner = new InvalidOperationException("root");
        var ex = new WavFormatException("wrap", inner);
        Assert.Equal("wrap", ex.Message);
        Assert.Same(inner, ex.InnerException);
    }

    // 依据用例 7 与加分项：WavFormatException 继承自 Exception 且与 AudioFormatException 是两个独立类型，
    // 因此可赋值给 Exception，但不是 AudioFormatException 类型。
    [Fact]
    public void WavFormatException_IsException_And_DistinctFromAudioFormatException()
    {
        var ex = new WavFormatException("x");
        Assert.IsAssignableFrom<Exception>(ex);
        Assert.IsNotType<AudioFormatException>(ex);
    }
}
