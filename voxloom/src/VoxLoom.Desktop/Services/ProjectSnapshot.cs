using System.Text.Json;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Desktop.Services;

public static class ProjectSnapshot
{
    public static void Write(string directory, AudioClip clip, TranscriptDoc? doc, string projectName, string? sourceAudioPath)
    {
        if (clip is null) throw new ArgumentException("没有可备份的音频", nameof(clip));
        if (string.IsNullOrWhiteSpace(directory)) throw new ArgumentException("快照目录不能为空", nameof(directory));

        Directory.CreateDirectory(directory);

        WavWriter.Write(Path.Combine(directory, "audio.wav"), clip);

        var words = doc is null
            ? new List<object>()
            : doc.Words.Select(w => (object)new
            {
                text = w.Text,
                start = w.Start.TotalSeconds,
                end = w.End.TotalSeconds,
                confidence = w.Confidence
            }).ToList();

        var transcript = new
        {
            version = 1,
            durationSeconds = (doc?.Duration ?? clip.Duration).TotalSeconds,
            words
        };
        File.WriteAllText(Path.Combine(directory, "transcript.json"),
            JsonSerializer.Serialize(transcript, new JsonSerializerOptions { WriteIndented = true }));

        var meta = new
        {
            version = 1,
            projectName,
            createdUtc = DateTime.UtcNow.ToString("o"),
            sourceAudioPath,
            voxloomVersion = typeof(ProjectSnapshot).Assembly.GetName().Version?.ToString() ?? "0.0.0"
        };
        File.WriteAllText(Path.Combine(directory, "meta.json"),
            JsonSerializer.Serialize(meta, new JsonSerializerOptions { WriteIndented = true }));
    }

    public static (AudioClip Clip, TranscriptDoc Doc, string ProjectName)? Read(string directory)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(directory)) return null;
            if (!Directory.Exists(directory)) return null;

            var wavPath = Path.Combine(directory, "audio.wav");
            var transcriptPath = Path.Combine(directory, "transcript.json");
            var metaPath = Path.Combine(directory, "meta.json");

            if (!File.Exists(wavPath)) return null;
            if (!File.Exists(transcriptPath)) return null;

            var clip = WavReader.Read(wavPath);
            if (clip is null) return null;

            using var tdoc = JsonDocument.Parse(File.ReadAllText(transcriptPath));
            var root = tdoc.RootElement;

            double durationSeconds = root.TryGetProperty("durationSeconds", out var dEl) && dEl.ValueKind == JsonValueKind.Number
                ? dEl.GetDouble()
                : clip.Duration.TotalSeconds;

            var words = new List<TranscriptWord>();
            if (root.TryGetProperty("words", out var wordsEl) && wordsEl.ValueKind == JsonValueKind.Array)
            {
                foreach (var w in wordsEl.EnumerateArray())
                {
                    var text = w.TryGetProperty("text", out var tEl) ? (tEl.GetString() ?? string.Empty) : string.Empty;
                    var start = w.TryGetProperty("start", out var sEl) && sEl.ValueKind == JsonValueKind.Number
                        ? sEl.GetDouble() : 0d;
                    var end = w.TryGetProperty("end", out var eEl) && eEl.ValueKind == JsonValueKind.Number
                        ? eEl.GetDouble() : start;
                    var confidence = w.TryGetProperty("confidence", out var cEl) && cEl.ValueKind == JsonValueKind.Number
                        ? (float)cEl.GetDouble() : 1f;
                    words.Add(new TranscriptWord(text, TimeSpan.FromSeconds(start), TimeSpan.FromSeconds(end), confidence));
                }
            }

            words.Sort((a, b) => a.Start.CompareTo(b.Start));
            var transcriptDoc = new TranscriptDoc(words, TimeSpan.FromSeconds(durationSeconds));

            var projectName = "project";
            if (File.Exists(metaPath))
            {
                try
                {
                    using var mdoc = JsonDocument.Parse(File.ReadAllText(metaPath));
                    if (mdoc.RootElement.TryGetProperty("projectName", out var pEl) &&
                        pEl.ValueKind == JsonValueKind.String)
                    {
                        var p = pEl.GetString();
                        if (!string.IsNullOrEmpty(p)) projectName = p!;
                    }
                }
                catch
                {
                }
            }

            return (clip, transcriptDoc, projectName);
        }
        catch
        {
            return null;
        }
    }
}
