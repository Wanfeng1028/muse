namespace VoxLoom.Core.Audio;

/// <summary>
/// 统一音频导入入口：根据文件头魔数（辅以扩展名）识别格式，
/// 再分发给 WavReader（WAV 纯托管）或 FfmpegDecoder（MP3/FLAC/M4A 真实解码）。
/// </summary>
public static class AudioImporter
{
    /// <summary>
    /// 文件选择对话框用的过滤器字符串。
    /// </summary>
    public static string OpenFileFilter { get; } =
        "音频文件|*.wav;*.mp3;*.flac;*.m4a|WAV|*.wav|MP3|*.mp3|FLAC|*.flac|M4A|*.m4a|所有文件|*.*";

    /// <summary>
    /// 根据文件头魔数识别音频格式，认不出时按扩展名兜底。
    /// </summary>
    /// <param name="path">音频文件路径。</param>
    /// <returns>识别出的音频格式。</returns>
    /// <exception cref="ArgumentNullException">path 为 null 时抛出。</exception>
    /// <exception cref="AudioFormatException">文件不存在或格式不支持时抛出。</exception>
    public static AudioFormat DetectFormat(string path)
    {
        if (path is null)
        {
            throw new ArgumentNullException(nameof(path));
        }

        if (!File.Exists(path))
        {
            throw new AudioFormatException($"找不到音频文件：{path}");
        }

        byte[] head;
        try
        {
            using var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
            head = new byte[12];
            int total = 0;
            while (total < head.Length)
            {
                int read = fs.Read(head, total, head.Length - total);
                if (read <= 0)
                {
                    break;
                }
                total += read;
            }

            if (total < head.Length)
            {
                Array.Resize(ref head, total);
            }
        }
        catch (Exception ex)
        {
            throw new AudioFormatException($"读取音频文件头失败：{ex.Message}", ex);
        }

        var byMagic = DetectByMagic(head);
        if (byMagic.HasValue)
        {
            return byMagic.Value;
        }

        var byExt = DetectByExtension(path);
        if (byExt.HasValue)
        {
            return byExt.Value;
        }

        throw new AudioFormatException($"不支持的音频格式：{Path.GetFileName(path)}（仅支持 WAV/MP3/FLAC/M4A）");
    }

    /// <summary>
    /// 识别格式并读取为 AudioClip。
    /// </summary>
    /// <param name="path">音频文件路径。</param>
    /// <param name="ffmpegPath">显式指定的 ffmpeg 路径，可为 null。</param>
    /// <returns>读取到的 AudioClip。</returns>
    public static AudioClip Import(string path, string? ffmpegPath = null)
    {
        var format = DetectFormat(path);
        switch (format)
        {
            case AudioFormat.Wav:
                return WavReader.Read(path);
            case AudioFormat.Mp3:
            case AudioFormat.Flac:
            case AudioFormat.M4a:
                return FfmpegDecoder.Decode(path, ffmpegPath);
            default:
                throw new AudioFormatException($"不支持的音频格式：{Path.GetFileName(path)}（仅支持 WAV/MP3/FLAC/M4A）");
        }
    }

    /// <summary>
    /// 返回格式的显示名。
    /// </summary>
    /// <param name="f">音频格式。</param>
    /// <returns>人类可读的格式名。</returns>
    public static string FormatDisplayName(AudioFormat f)
    {
        return f switch
        {
            AudioFormat.Wav => "WAV",
            AudioFormat.Mp3 => "MP3",
            AudioFormat.Flac => "FLAC",
            AudioFormat.M4a => "M4A",
            _ => f.ToString()
        };
    }

    private static AudioFormat? DetectByMagic(byte[] head)
    {
        if (head.Length >= 12
            && head[0] == (byte)'R' && head[1] == (byte)'I' && head[2] == (byte)'F' && head[3] == (byte)'F'
            && head[8] == (byte)'W' && head[9] == (byte)'A' && head[10] == (byte)'V' && head[11] == (byte)'E')
        {
            return AudioFormat.Wav;
        }

        if (head.Length >= 4 && head[0] == (byte)'f' && head[1] == (byte)'L' && head[2] == (byte)'a' && head[3] == (byte)'C')
        {
            return AudioFormat.Flac;
        }

        if (head.Length >= 3 && head[0] == (byte)'I' && head[1] == (byte)'D' && head[2] == (byte)'3')
        {
            return AudioFormat.Mp3;
        }

        if (head.Length >= 2 && head[0] == 0xFF && (head[1] == 0xFB || head[1] == 0xF3 || head[1] == 0xF2))
        {
            return AudioFormat.Mp3;
        }

        if (head.Length >= 8
            && head[4] == (byte)'f' && head[5] == (byte)'t' && head[6] == (byte)'y' && head[7] == (byte)'p')
        {
            return AudioFormat.M4a;
        }

        return null;
    }

    private static AudioFormat? DetectByExtension(string path)
    {
        var ext = Path.GetExtension(path);
        if (string.IsNullOrEmpty(ext))
        {
            return null;
        }

        return ext.ToLowerInvariant() switch
        {
            ".wav" => AudioFormat.Wav,
            ".mp3" => AudioFormat.Mp3,
            ".flac" => AudioFormat.Flac,
            ".m4a" => AudioFormat.M4a,
            _ => null
        };
    }

}
