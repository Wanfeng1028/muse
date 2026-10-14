using System.Buffers.Binary;
using System.Diagnostics;
using System.Globalization;
using System.Text;

namespace VoxLoom.Core.Audio;

/// <summary>
/// 通过外部 ffmpeg / ffprobe 进程真实解码 FLAC、M4A 等 NAudio 无法纯托管解码的格式。
/// 采样率与声道数用 ffprobe 获取，PCM 数据用 ffmpeg 输出 f32le 原始小端 float32 交错数据。
/// </summary>
public static class FfmpegDecoder
{
    private const int FfprobeTimeoutMs = 30_000;
    private const int DecodeTimeoutMs = 120_000;
    private const long MaxDecodedBytes = 1L * 1024 * 1024 * 1024; // 1GB
    private const int StderrTailLength = 2000;

    /// <summary>
    /// 决定最终要调用的 ffmpeg 可执行文件路径。
    /// 优先级：configuredPath（非空即用）→ 环境变量 VOXLOOM_FFMPEG_PATH → "ffmpeg"（走 PATH）。
    /// </summary>
    /// <param name="configuredPath">调用方显式指定的路径，可为 null。</param>
    /// <returns>最终使用的 ffmpeg 路径字符串。</returns>
    public static string ResolveFfmpegPath(string? configuredPath)
    {
        if (!string.IsNullOrWhiteSpace(configuredPath))
        {
            return configuredPath!;
        }

        var envPath = Environment.GetEnvironmentVariable("VOXLOOM_FFMPEG_PATH");
        if (!string.IsNullOrWhiteSpace(envPath))
        {
            return envPath!;
        }

        return "ffmpeg";
    }

    /// <summary>
    /// 检查 ffmpeg 是否可用（跑一次 ffmpeg -version）。任何异常都吞掉并返回 false。
    /// </summary>
    /// <param name="configuredPath">调用方显式指定的路径，可为 null。</param>
    /// <returns>可用返回 true，否则返回 false。</returns>
    public static bool IsAvailable(string? configuredPath = null)
    {
        try
        {
            var ffmpegPath = ResolveFfmpegPath(configuredPath);
            var psi = new ProcessStartInfo
            {
                FileName = ffmpegPath,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };
            psi.ArgumentList.Add("-version");

            using var process = Process.Start(psi);
            if (process is null)
            {
                return false;
            }

            process.StandardOutput.ReadToEnd();
            process.StandardError.ReadToEnd();

            if (!process.WaitForExit(10_000))
            {
                try { process.Kill(entireProcessTree: true); } catch { }
                return false;
            }

            return process.ExitCode == 0;
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// 用 ffmpeg 解码指定音频文件，返回统一交错的 AudioClip。
    /// </summary>
    /// <param name="path">音频文件路径。</param>
    /// <param name="ffmpegPath">显式指定的 ffmpeg 路径，可为 null。</param>
    /// <returns>解码后的 AudioClip。</returns>
    /// <exception cref="ArgumentNullException">path 为 null 时抛出。</exception>
    /// <exception cref="AudioFormatException">文件不存在、缺少 ffmpeg、解析失败、解码失败等情况下抛出。</exception>
    public static AudioClip Decode(string path, string? ffmpegPath = null)
    {
        if (path is null)
        {
            throw new ArgumentNullException(nameof(path));
        }

        if (!File.Exists(path))
        {
            throw new AudioFormatException($"找不到音频文件：{path}");
        }

        if (!BitConverter.IsLittleEndian)
        {
            throw new AudioFormatException("当前平台不是小端字节序，暂不支持解码此格式。");
        }

        if (!IsAvailable(ffmpegPath))
        {
            throw new AudioFormatException(
                "解码此格式需要 ffmpeg，但没找到。请安装：Ubuntu/Debian 执行 sudo apt install ffmpeg；" +
                "macOS 执行 brew install ffmpeg；或到 ffmpeg.org 下载，并确认 ffmpeg 在 PATH 中，" +
                "也可用环境变量 VOXLOOM_FFMPEG_PATH 指定路径。");
        }

        var resolvedFfmpeg = ResolveFfmpegPath(ffmpegPath);
        var ffprobePath = DeriveFfprobePath(resolvedFfmpeg);

        var (sampleRate, channels) = ProbeAudioInfo(ffprobePath, path);

        var samples = DecodePcm(resolvedFfmpeg, path, sampleRate, channels);
        return new AudioClip(sampleRate, channels, samples);
    }

    private static string DeriveFfprobePath(string ffmpegPath)
    {
        // 尝试把 ffmpeg 换成 ffprobe（同目录下通常并存）。
        try
        {
            var dir = Path.GetDirectoryName(ffmpegPath);
            var name = Path.GetFileName(ffmpegPath);
            if (!string.IsNullOrEmpty(name) && name.StartsWith("ffmpeg", StringComparison.OrdinalIgnoreCase))
            {
                var probeName = "ffprobe" + name.Substring("ffmpeg".Length);
                if (!string.IsNullOrEmpty(dir))
                {
                    var candidate = Path.Combine(dir, probeName);
                    if (File.Exists(candidate))
                    {
                        return candidate;
                    }
                }
                return probeName;
            }
        }
        catch
        {
            // 忽略，回退到默认名字。
        }

        return "ffprobe";
    }

    private static (int SampleRate, int Channels) ProbeAudioInfo(string ffprobePath, string inputPath)
    {
        var psi = new ProcessStartInfo
        {
            FileName = ffprobePath,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };
        psi.ArgumentList.Add("-v");
        psi.ArgumentList.Add("error");
        psi.ArgumentList.Add("-select_streams");
        psi.ArgumentList.Add("a:0");
        psi.ArgumentList.Add("-show_entries");
        psi.ArgumentList.Add("stream=sample_rate,channels");
        psi.ArgumentList.Add("-of");
        psi.ArgumentList.Add("csv=p=0");
        psi.ArgumentList.Add(inputPath);

        string stdout;
        string stderr;
        int exitCode;
        try
        {
            using var process = Process.Start(psi)
                ?? throw new AudioFormatException("无法启动 ffprobe 进程。");

            stdout = process.StandardOutput.ReadToEnd();
            stderr = process.StandardError.ReadToEnd();

            if (!process.WaitForExit(FfprobeTimeoutMs))
            {
                try { process.Kill(entireProcessTree: true); } catch { }
                throw new AudioFormatException("调用 ffprobe 超时（30 秒），已终止进程。");
            }

            exitCode = process.ExitCode;
        }
        catch (AudioFormatException)
        {
            throw;
        }
        catch (Exception ex)
        {
            throw new AudioFormatException($"调用 ffprobe 失败：{ex.Message}", ex);
        }

        if (exitCode != 0)
        {
            var tail = Tail(stderr, StderrTailLength);
            throw new AudioFormatException($"ffprobe 解析音频信息失败（退出码 {exitCode}）：{tail}");
        }

        // 期望输出形如：44100,2 或 48000,1
        var line = stdout.Trim().Split('\n', '\r')
            .FirstOrDefault(s => !string.IsNullOrWhiteSpace(s))?.Trim() ?? string.Empty;

        var parts = line.Split(',');
        if (parts.Length < 2
            || !int.TryParse(parts[0].Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var sampleRate)
            || !int.TryParse(parts[1].Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var channels))
        {
            throw new AudioFormatException($"无法从 ffprobe 输出解析采样率与声道数：{line}");
        }

        if (sampleRate <= 0)
        {
            throw new AudioFormatException($"采样率非法：{sampleRate}");
        }

        if (channels != 1 && channels != 2)
        {
            throw new AudioFormatException($"仅支持单声道或立体声，当前为 {channels} 声道。");
        }

        return (sampleRate, channels);
    }

    private static float[] DecodePcm(string ffmpegPath, string inputPath, int sampleRate, int channels)
    {
        var psi = new ProcessStartInfo
        {
            FileName = ffmpegPath,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };
        psi.ArgumentList.Add("-v");
        psi.ArgumentList.Add("error");
        psi.ArgumentList.Add("-i");
        psi.ArgumentList.Add(inputPath);
        psi.ArgumentList.Add("-map");
        psi.ArgumentList.Add("0:a:0");
        psi.ArgumentList.Add("-f");
        psi.ArgumentList.Add("f32le");
        psi.ArgumentList.Add("-acodec");
        psi.ArgumentList.Add("pcm_f32le");
        psi.ArgumentList.Add("-ar");
        psi.ArgumentList.Add(sampleRate.ToString(CultureInfo.InvariantCulture));
        psi.ArgumentList.Add("-ac");
        psi.ArgumentList.Add(channels.ToString(CultureInfo.InvariantCulture));
        psi.ArgumentList.Add("pipe:1");

        using var process = Process.Start(psi)
            ?? throw new AudioFormatException("无法启动 ffmpeg 进程。");

        var stdout = process.StandardOutput.BaseStream;
        var stderrTask = Task.Run(() => process.StandardError.ReadToEnd());

        using var buffer = new MemoryStream();
        var chunk = new byte[64 * 1024];
        var timedOut = false;

        // 用 Task 读取，配合整体超时。
        var readTask = Task.Run(() =>
        {
            int read;
            while ((read = stdout.Read(chunk, 0, chunk.Length)) > 0)
            {
                buffer.Write(chunk, 0, read);
                if (buffer.Length > MaxDecodedBytes)
                {
                    try { process.Kill(entireProcessTree: true); } catch { }
                    throw new AudioFormatException("解码后数据过大（>1GB），拒绝载入");
                }
            }
        });

        if (!readTask.Wait(DecodeTimeoutMs))
        {
            timedOut = true;
            try { process.Kill(entireProcessTree: true); } catch { }
        }

        try
        {
            process.WaitForExit(5_000);
        }
        catch
        {
            // 忽略
        }

        if (timedOut)
        {
            throw new AudioFormatException("调用 ffmpeg 解码超时（120 秒），已终止进程。");
        }

        // 读取过程若抛了异常，这里会重新抛出。
        readTask.GetAwaiter().GetResult();

        var stderr = stderrTask.GetAwaiter().GetResult();

        int exitCode;
        try
        {
            exitCode = process.ExitCode;
        }
        catch (InvalidOperationException)
        {
            exitCode = -1;
        }

        if (exitCode != 0)
        {
            var tail = Tail(stderr, StderrTailLength);
            throw new AudioFormatException($"ffmpeg 解码失败（退出码 {exitCode}）：{tail}");
        }

        var raw = buffer.ToArray();
        int bytesPerFrame = 4 * channels;
        if (raw.Length % bytesPerFrame != 0)
        {
            throw new AudioFormatException("解码后数据长度不是帧长的整数倍，文件可能已损坏。");
        }

        int sampleCount = raw.Length / 4;
        var samples = new float[sampleCount];
        for (int i = 0; i < sampleCount; i++)
        {
            var value = BinaryPrimitives.ReadSingleLittleEndian(raw.AsSpan(i * 4, 4));
            samples[i] = value;
        }

        return samples;
    }

    private static string Tail(string text, int max)
    {
        if (string.IsNullOrEmpty(text))
        {
            return string.Empty;
        }
        text = text.Trim();
        if (text.Length <= max)
        {
            return text;
        }
        return text.Substring(text.Length - max);
    }
}
