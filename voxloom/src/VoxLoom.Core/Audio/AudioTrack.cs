namespace VoxLoom.Core.Audio;

/// <summary>
/// 一条音频轨的 ffprobe 描述。
/// </summary>
/// <param name="AudioIndex">音频轨顺序号（从 0 起，只在音频流中计数）。</param>
/// <param name="StreamIndex">ffprobe 流号（在全部流中计数，含视频/字幕流）。</param>
/// <param name="CodecName">编码名，例如 aac、flac、mp3。</param>
/// <param name="SampleRate">采样率（Hz）。</param>
/// <param name="Channels">声道数。</param>
public sealed record AudioTrack(int AudioIndex, int StreamIndex, string CodecName, int SampleRate, int Channels);
