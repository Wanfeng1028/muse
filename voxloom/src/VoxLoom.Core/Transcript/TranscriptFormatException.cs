using System;

namespace VoxLoom.Core.Transcript;

/// <summary>
/// 转写稿格式解析失败时抛出的异常。
/// </summary>
public sealed class TranscriptFormatException : Exception
{
    /// <summary>使用消息构造。</summary>
    public TranscriptFormatException(string message) : base(message)
    {
    }

    /// <summary>使用消息与内部异常构造。</summary>
    public TranscriptFormatException(string message, Exception innerException) : base(message, innerException)
    {
    }
}
