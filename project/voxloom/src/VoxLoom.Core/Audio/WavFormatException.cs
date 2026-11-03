namespace VoxLoom.Core.Audio;

/// <summary>
/// 表示 WAV 文件格式非法或不受支持时抛出的异常。
/// </summary>
public class WavFormatException : Exception
{
    /// <summary>
    /// 使用指定的错误信息构造异常。
    /// </summary>
    /// <param name="message">简体中文错误信息。</param>
    public WavFormatException(string message) : base(message)
    {
    }

    /// <summary>
    /// 使用指定的错误信息与内部异常构造异常。
    /// </summary>
    /// <param name="message">简体中文错误信息。</param>
    /// <param name="innerException">触发本异常的内部异常。</param>
    public WavFormatException(string message, Exception innerException) : base(message, innerException)
    {
    }
}
