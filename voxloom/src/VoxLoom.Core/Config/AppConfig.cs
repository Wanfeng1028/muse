using System.Text.Json;

namespace VoxLoom.Core.Config;

public sealed class ConfigValidationException : Exception
{
    public ConfigValidationException(string message) : base(message) { }
    public ConfigValidationException(string message, Exception inner) : base(message, inner) { }
}

public sealed class AppConfig
{
    public string FfmpegPath { get; private set; } = "ffmpeg";
    public string LogDirectory { get; private set; } = string.Empty;
    public string BackupDirectory { get; private set; } = string.Empty;
    public string ProjectsDirectory { get; private set; } = string.Empty;
    public int BackupRetentionCount { get; private set; } = 10;
    public bool AutoBackupEnabled { get; private set; } = true;
    public int AutoBackupIntervalMinutes { get; private set; } = 60;
    public int AutoBackupRetentionCount { get; private set; } = 5;


    public static string AppDataDir => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "VoxLoom");

    private static readonly string[] ForbiddenKeyTokens =
    {
        "password", "passwd", "secret", "token", "apikey", "api_key"
    };

    public static AppConfig Load(string? configPath = null)
    {
        var path = configPath ?? Path.Combine(AppDataDir, "config.json");

        var cfg = new AppConfig
        {
            FfmpegPath = "ffmpeg",
            LogDirectory = Path.Combine(AppDataDir, "logs"),
            BackupDirectory = Path.Combine(AppDataDir, "backups"),
            ProjectsDirectory = Path.Combine(AppDataDir, "projects"),
            BackupRetentionCount = 10
        };

        if (File.Exists(path))
        {
            string json;
            try
            {
                json = File.ReadAllText(path);
            }
            catch (Exception ex)
            {
                throw new ConfigValidationException($"读取配置文件失败：{path}", ex);
            }

            JsonDocument doc;
            try
            {
                doc = JsonDocument.Parse(json);
            }
            catch (Exception ex)
            {
                throw new ConfigValidationException($"配置文件不是合法 JSON：{path}", ex);
            }

            using (doc)
            {
                var root = doc.RootElement;
                if (root.ValueKind != JsonValueKind.Object)
                    throw new ConfigValidationException("配置文件根节点必须是 JSON 对象");

                foreach (var prop in root.EnumerateObject())
                {
                    if (IsForbiddenKey(prop.Name))
                        throw new ConfigValidationException(
                            $"配置文件不许放密钥（检测到键“{prop.Name}”）…请改用环境变量");

                    switch (prop.Name)
                    {
                        case "ffmpegPath":
                            cfg.FfmpegPath = ReadString(prop, "ffmpegPath");
                            break;
                        case "logDirectory":
                            cfg.LogDirectory = ReadString(prop, "logDirectory");
                            break;
                        case "backupDirectory":
                            cfg.BackupDirectory = ReadString(prop, "backupDirectory");
                            break;
                        case "projectsDirectory":
                            cfg.ProjectsDirectory = ReadString(prop, "projectsDirectory");
                            break;
                        case "backupRetentionCount":
                            cfg.BackupRetentionCount = ReadInt(prop, "backupRetentionCount");
                            break;
                        case "autoBackupEnabled":
                            cfg.AutoBackupEnabled = ReadBool(prop, "autoBackupEnabled");
                            break;
                        case "autoBackupIntervalMinutes":
                            cfg.AutoBackupIntervalMinutes = ReadInt(prop, "autoBackupIntervalMinutes");
                            break;
                        case "autoBackupRetentionCount":
                            cfg.AutoBackupRetentionCount = ReadInt(prop, "autoBackupRetentionCount");
                            break;

                        default:
                            break;
                    }
                }
            }
        }

        ApplyEnvOverride("VOXLOOM_FFMPEG_PATH", v => cfg.FfmpegPath = v);
        ApplyEnvOverride("VOXLOOM_LOG_DIR", v => cfg.LogDirectory = v);
        ApplyEnvOverride("VOXLOOM_BACKUP_DIR", v => cfg.BackupDirectory = v);
        ApplyEnvOverride("VOXLOOM_PROJECTS_DIR", v => cfg.ProjectsDirectory = v);

        var retentionEnv = Environment.GetEnvironmentVariable("VOXLOOM_BACKUP_RETENTION");
        if (!string.IsNullOrEmpty(retentionEnv))
        {
            if (!int.TryParse(retentionEnv, out var n))
                throw new ConfigValidationException($"环境变量 VOXLOOM_BACKUP_RETENTION 不是整数：{retentionEnv}");
            cfg.BackupRetentionCount = n;
        }

        var autoEnabledEnv = Environment.GetEnvironmentVariable("VOXLOOM_AUTOBACKUP_ENABLED");
        if (!string.IsNullOrEmpty(autoEnabledEnv))
        {
            if (!bool.TryParse(autoEnabledEnv, out var b))
                throw new ConfigValidationException($"环境变量 VOXLOOM_AUTOBACKUP_ENABLED 不是布尔值：{autoEnabledEnv}");
            cfg.AutoBackupEnabled = b;
        }
        var autoIntervalEnv = Environment.GetEnvironmentVariable("VOXLOOM_AUTOBACKUP_INTERVAL_MINUTES");
        if (!string.IsNullOrEmpty(autoIntervalEnv))
        {
            if (!int.TryParse(autoIntervalEnv, out var autoInterval))
                throw new ConfigValidationException($"环境变量 VOXLOOM_AUTOBACKUP_INTERVAL_MINUTES 不是整数：{autoIntervalEnv}");
            cfg.AutoBackupIntervalMinutes = autoInterval;
        }
        var autoRetentionEnv = Environment.GetEnvironmentVariable("VOXLOOM_AUTOBACKUP_RETENTION");
        if (!string.IsNullOrEmpty(autoRetentionEnv))
        {
            if (!int.TryParse(autoRetentionEnv, out var autoRetention))
                throw new ConfigValidationException($"环境变量 VOXLOOM_AUTOBACKUP_RETENTION 不是整数：{autoRetentionEnv}");
            cfg.AutoBackupRetentionCount = autoRetention;
        }


        return cfg;
    }

    private static void ApplyEnvOverride(string name, Action<string> apply)
    {
        var v = Environment.GetEnvironmentVariable(name);
        if (!string.IsNullOrEmpty(v)) apply(v);
    }

    private static bool IsForbiddenKey(string key)
    {
        var lower = key.ToLowerInvariant();
        foreach (var token in ForbiddenKeyTokens)
        {
            if (lower.Contains(token)) return true;
        }
        return false;
    }

    private static string ReadString(JsonProperty prop, string name)
    {
        if (prop.Value.ValueKind != JsonValueKind.String)
            throw new ConfigValidationException($"配置项 {name} 类型错误，应为字符串");
        return prop.Value.GetString() ?? string.Empty;
    }

    private static int ReadInt(JsonProperty prop, string name)
    {
        if (prop.Value.ValueKind != JsonValueKind.Number || !prop.Value.TryGetInt32(out var v))
            throw new ConfigValidationException($"配置项 {name} 类型错误，应为整数");
        return v;
    }

    private static bool ReadBool(JsonProperty prop, string name)
    {
        if (prop.Value.ValueKind != JsonValueKind.True && prop.Value.ValueKind != JsonValueKind.False)
            throw new ConfigValidationException($"配置项 {name} 类型错误，应为布尔值");
        return prop.Value.GetBoolean();
    }

    public void Validate()
    {
        var problems = new List<string>();

        CheckDirectory(LogDirectory, "日志目录", problems);
        CheckDirectory(BackupDirectory, "备份目录", problems);
        CheckDirectory(ProjectsDirectory, "项目目录", problems);

        if (AutoBackupIntervalMinutes < 1 || AutoBackupIntervalMinutes > 1440)
            problems.Add("autoBackupIntervalMinutes 必须在 1~1440 之间");
        if (AutoBackupRetentionCount < 1 || AutoBackupRetentionCount > 100)
            problems.Add("autoBackupRetentionCount 必须在 1~100 之间");
        if (BackupRetentionCount < 1 || BackupRetentionCount > 100)
            problems.Add($"备份保留数量必须在 1..100 之间，当前为 {BackupRetentionCount}");

        if (problems.Count > 0)
        {
            var msg = "配置校验失败：\n" + string.Join("\n", problems.Select(p => "- " + p));
            throw new ConfigValidationException(msg);
        }
    }

    private static void CheckDirectory(string dir, string label, List<string> problems)
    {
        if (string.IsNullOrWhiteSpace(dir))
        {
            problems.Add($"{label}不能为空");
            return;
        }
        try
        {
            Directory.CreateDirectory(dir);
        }
        catch (Exception ex)
        {
            problems.Add($"{label}无法创建：{dir}（{ex.Message}）");
            return;
        }
        try
        {
            var probe = Path.Combine(dir, $".voxloom-write-test-{Guid.NewGuid():N}");
            File.WriteAllText(probe, "");
            File.Delete(probe);
        }
        catch (Exception ex)
        {
            problems.Add($"{label}不可写：{dir}（{ex.Message}）");
        }
    }
}
