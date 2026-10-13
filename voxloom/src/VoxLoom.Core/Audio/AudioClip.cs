namespace VoxLoom.Core.Audio;

/// <summary>
/// 不可变的音频片段模型。
/// <para>
/// 采样数据以 <see cref="Samples"/> 存放，采用 <b>交错（interleaved）</b> 布局：
/// 对于 <c>Channels = C</c> 的音频，第 <c>f</c> 帧的第 <c>c</c> 个声道样本位于
/// <c>Samples[f * C + c]</c>。每个样本取值范围为 <c>[-1.0f, 1.0f]</c>。
/// </para>
/// </summary>
public sealed class AudioClip
{
    /// <summary>采样率（Hz），例如 44100、48000。</summary>
    public int SampleRate { get; }

    /// <summary>声道数，例如 1（单声道）或 2（立体声）。</summary>
    public int Channels { get; }

    /// <summary>交错存放的浮点采样数据，取值范围 [-1, 1]。</summary>
    public float[] Samples { get; }

    /// <summary>帧数（每帧包含 <see cref="Channels"/> 个样本）。</summary>
    public long Frames { get; }

    /// <summary>
    /// 构造一个音频片段。
    /// </summary>
    /// <param name="sampleRate">采样率（Hz），必须大于 0。</param>
    /// <param name="channels">声道数，必须大于 0。</param>
    /// <param name="samples">交错布局的采样数据，长度必须为 <paramref name="channels"/> 的整数倍。</param>
    /// <exception cref="ArgumentOutOfRangeException">采样率或声道数不合法。</exception>
    /// <exception cref="ArgumentNullException"><paramref name="samples"/> 为 null。</exception>
    /// <exception cref="ArgumentException">样本长度与声道数不匹配。</exception>
    public AudioClip(int sampleRate, int channels, float[] samples)
    {
        ArgumentNullException.ThrowIfNull(samples);

        if (sampleRate <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(sampleRate), sampleRate, "采样率必须大于 0。");
        }

        if (channels <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(channels), channels, "声道数必须大于 0。");
        }

        if (samples.Length % channels != 0)
        {
            throw new ArgumentException(
                $"样本数组长度（{samples.Length}）必须是声道数（{channels}）的整数倍。",
                nameof(samples));
        }

        SampleRate = sampleRate;
        Channels = channels;
        Samples = samples;
        Frames = samples.Length / channels;
    }

    /// <summary>
    /// 片段时长。
    /// </summary>
    public TimeSpan Duration =>
        SampleRate > 0 ? TimeSpan.FromSeconds((double)Frames / SampleRate) : TimeSpan.Zero;

    /// <summary>
    /// 将多声道数据混合为单声道（对所有声道取算术平均）。
    /// 单声道输入将返回一份拷贝。
    /// </summary>
    /// <returns>长度为 <see cref="Frames"/> 的单声道浮点数组，取值范围 [-1, 1]。</returns>
    public float[] GetMonoSamples()
    {
        long frames = Frames;
        if (frames == 0)
        {
            return Array.Empty<float>();
        }

        // 长度超过 int.MaxValue 时无法一次性分配数组；此处保守处理。
        if (frames > int.MaxValue)
        {
            throw new InvalidOperationException("音频帧数超出单数组可表示范围。");
        }

        var mono = new float[(int)frames];

        if (Channels == 1)
        {
            Array.Copy(Samples, mono, mono.Length);
            return mono;
        }

        int channels = Channels;
        float inv = 1f / channels;
        var src = Samples;

        for (int f = 0; f < mono.Length; f++)
        {
            int baseIndex = f * channels;
            float sum = 0f;
            for (int c = 0; c < channels; c++)
            {
                sum += src[baseIndex + c];
            }
            mono[f] = sum * inv;
        }

        return mono;
    }
}
