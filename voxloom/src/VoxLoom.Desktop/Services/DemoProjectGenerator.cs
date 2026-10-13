using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Desktop.Services;

/// <summary>
/// 生成演示项目数据，方便快速体验界面。
/// </summary>
public static class DemoProjectGenerator
{
    public static (AudioClip Clip, TranscriptDoc Doc) Generate()
    {
        const int sampleRate = 44100;
        const int channels = 1;
        const double totalSeconds = 12.0;

        // 生成一段模拟语音：音节式 burst（浊音段+气口静音），包络像真人说话
        var sampleCount = (int)(totalSeconds * sampleRate);
        var samples = new float[sampleCount];
        var rng = new Random(20240501);
        var idx = 0;
        while (idx < sampleCount)
        {
            // 一个"音节"：0.12–0.30 秒浊音
            var sylLen = (int)((0.12 + rng.NextDouble() * 0.18) * sampleRate);
            var freq = 110 + rng.NextDouble() * 140;      // 基频随机，像语调起伏
            var amp = 0.25 + rng.NextDouble() * 0.25;     // 音量随机
            for (var i = 0; i < sylLen && idx < sampleCount; i++, idx++)
            {
                var t = i / (double)sampleRate;
                // 音节包络：快起慢落
                var env = Math.Min(1.0, i / (0.015 * sampleRate))
                        * Math.Exp(-2.2 * i / sylLen);
                var vibrato = 1 + 0.02 * Math.Sin(2 * Math.PI * 5.5 * t);
                var voiced = Math.Sin(2 * Math.PI * freq * vibrato * t) * 0.7
                           + Math.Sin(2 * Math.PI * freq * 2.02 * t) * 0.2;
                var noise = (rng.NextDouble() - 0.5) * 0.04;
                samples[idx] = (float)(amp * env * (voiced + noise));
            }
            // 气口：0.04–0.16 秒近静音
            var gapLen = (int)((0.04 + rng.NextDouble() * 0.12) * sampleRate);
            for (var i = 0; i < gapLen && idx < sampleCount; i++, idx++)
            {
                samples[idx] = (float)((rng.NextDouble() - 0.5) * 0.008);
            }
        }
        var clip = new AudioClip(sampleRate, channels, samples);

        // 构造演示文本
        var text =
            "大家好，欢迎来到声纹工坊。嗯，今天我们演示一下，呃，如何清理音频中的口癖。" +
            "你看，这一段就是典型的口语素材，对吧？然后我们会把它导出为 EDL。";

        var doc = TranscriptImporter.ParsePlainText(text, TimeSpan.FromSeconds(totalSeconds));

        // 手动调整时间轴，让演示数据更自然
        var demoWords = new List<TranscriptWord>();
        var cursor = 0.0;
        foreach (var w in doc.Words)
        {
            var dur = Math.Max(0.18, w.Text.Length * 0.09);
            var start = cursor;
            var end = start + dur;
            if (end > totalSeconds) break;
            demoWords.Add(new TranscriptWord(
                w.Text,
                TimeSpan.FromSeconds(start),
                TimeSpan.FromSeconds(end),
                (float)Math.Min(0.99, 0.72 + (w.Text.Length % 5) * 0.05)));
            cursor = end + 0.05;
        }
        return (clip, new TranscriptDoc(demoWords, TimeSpan.FromSeconds(totalSeconds)));
    }

    /// <summary>
    /// 生成演示音频 WAV 与 LRC 转写稿到指定路径（供冒烟测试与截图使用）。
    /// </summary>
    public static void WriteFiles(string wavPath, string? lrcPath)
    {
        var (clip, doc) = Generate();
        WavWriter.Write(wavPath, clip);
        if (lrcPath is not null)
        {
            var sb = new System.Text.StringBuilder();
            foreach (var w in doc.Words)
            {
                sb.Append(CultureInfo.InvariantCulture,
                    $"[{w.Start:mm\\:ss\\.ff}] {w.Text}\n");
            }
            File.WriteAllText(lrcPath, sb.ToString());
        }
    }
}
