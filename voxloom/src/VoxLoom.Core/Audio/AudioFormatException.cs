namespace VoxLoom.Core.Audio;

/// <summary>
/// 音频格式相关的异常。当文件格式不支持、文件头损坏、
/// 缺少外部解码器（比如 ffmpeg）等情况下抛出。
/// </summary>
public class AudioFormatException : Exception
{
    /// <summary>
    /// 用一条错误信息构造异常。
    /// </summary>
    /// <param name="message">错误信息。</param>
    public AudioFormatException(string message) : base(message) { }

    /// <summary>
    /// 用一条错误信息和内部异常构造异常。
    /// </summary>
    /// <param name="message">错误信息。</param>
    /// <param name="innerException">内部异常。</param>
    public AudioFormatException(string message, Exception innerException) : base(message, innerException) { }
}
