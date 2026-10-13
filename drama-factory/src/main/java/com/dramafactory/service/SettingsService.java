package com.dramafactory.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 设置中心读写服务。
 *
 * <p>负责读写 {@value #SETTINGS_PATH}，提供掩码视图与 schema 元数据。</p>
 */
@Service
public class SettingsService {

    /** 设置文件相对工作目录路径，与环境后置处理器共用。 */
    public static final String SETTINGS_PATH = "data/settings.json";

    /** secret 键集合，这些键在返回给前端时会被掩码。 */
    public static final Set<String> SECRET_KEYS = Set.of(
            "deepseek.api-key",
            "dashscope.api-key",
            "agnes.api-key"
    );

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final Path settingsPath;

    /** Spring 构造器：使用默认路径。 */
    public SettingsService() {
        this(Paths.get(SETTINGS_PATH));
    }

    /** 测试构造器：使用隔离路径，避免污染真实 data/settings.json。 */
    SettingsService(Path settingsPath) {
        this.settingsPath = settingsPath;
    }

    /**
     * 读取全部设置。
     *
     * @return 键值映射；文件不存在返回空 Map
     */
    public Map<String, String> loadAll() {
        Path path = settingsPath;
        if (!Files.isRegularFile(path)) {
            return new LinkedHashMap<>();
        }
        try {
            byte[] bytes = Files.readAllBytes(path);
            if (bytes.length == 0) {
                return new LinkedHashMap<>();
            }
            Map<String, String> raw = MAPPER.readValue(bytes, new TypeReference<LinkedHashMap<String, String>>() {
            });
            Map<String, String> result = new LinkedHashMap<>();
            if (raw != null) {
                for (Map.Entry<String, String> e : raw.entrySet()) {
                    if (e.getKey() == null || e.getKey().isBlank()) {
                        continue;
                    }
                    result.put(e.getKey(), e.getValue() == null ? "" : e.getValue());
                }
            }
            return result;
        } catch (IOException e) {
            throw new IllegalStateException("解析设置文件失败: " + SETTINGS_PATH, e);
        }
    }

    /**
     * 合并保存设置。
     *
     * <p>patch 中 value 为 null 或空字符串表示删除该键；
     * 但 secret 键空字符串表示"保持原值不改"。</p>
     *
     * @param patch 待合并的键值对
     */
    public synchronized void saveAll(Map<String, String> patch) {
        Map<String, String> current = loadAll();
        if (patch != null) {
            for (Map.Entry<String, String> e : patch.entrySet()) {
                String key = e.getKey();
                if (key == null || key.isBlank()) {
                    continue;
                }
                String value = e.getValue();
                boolean blank = value == null || value.isEmpty();
                if (SECRET_KEYS.contains(key)) {
                    if (blank) {
                        // secret 空串 = 保持原值
                        continue;
                    }
                    current.put(key, value);
                } else {
                    if (blank) {
                        current.remove(key);
                    } else {
                        current.put(key, value);
                    }
                }
            }
        }
        write(current);
    }

    private void write(Map<String, String> data) {
        Path path = settingsPath;
        try {
            Path parent = path.getParent();
            if (parent != null && !Files.isDirectory(parent)) {
                Files.createDirectories(parent);
            }
            String json = MAPPER.writerWithDefaultPrettyPrinter().writeValueAsString(data);
            Files.write(path, json.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        } catch (IOException e) {
            throw new IllegalStateException("写入设置文件失败: " + SETTINGS_PATH, e);
        }
    }

    /**
     * 返回全部设置，secret 键以掩码呈现。
     *
     * @return 掩码视图
     */
    public Map<String, Object> maskedView() {
        Map<String, String> all = loadAll();
        Map<String, Object> view = new LinkedHashMap<>();
        for (Map.Entry<String, String> e : all.entrySet()) {
            String key = e.getKey();
            String value = e.getValue();
            if (SECRET_KEYS.contains(key)) {
                view.put(key, mask(value));
            } else {
                view.put(key, value == null ? "" : value);
            }
        }
        return view;
    }

    /**
     * 对密钥值进行掩码，保留后 4 位。
     *
     * @param value 原始值
     * @return 掩码字符串；空值返回空串
     */
    static String mask(String value) {
        if (value == null || value.isEmpty()) {
            return "";
        }
        if (value.length() <= 4) {
            return "****";
        }
        return "****" + value.substring(value.length() - 4);
    }

    /**
     * 返回设置字段元数据。
     *
     * @return schema 列表
     */
    public List<Map<String, Object>> schema() {
        List<Map<String, Object>> list = new ArrayList<>();
        list.add(field("deepseek.api-key", "DeepSeek API Key", "password", true, false, null,
                "用于编剧与 AI 对话；留空则使用内置鉴权"));
        list.add(field("deepseek.base-url", "DeepSeek Base URL", "text", false, true, null,
                "默认 https://api.deepseek.com"));
        list.add(field("deepseek.model", "编剧模型", "text", false, true, null,
                "默认 deepseek-chat"));
        list.add(field("dashscope.api-key", "DashScope API Key", "password", true, false, null,
                "用于千问视频通道（wan2.5）"));
        list.add(field("agnes.api-key", "Agnes API Key", "password", true, false, null,
                "用于 Agnes 降级通道"));
        list.add(field("drama.video.provider", "默认视频通道", "select", false, false,
                List.of("mock", "qwen", "agnes"), "默认 mock（本地模拟，不花钱）；改后立即生效"));
        list.add(field("harness.qc.manual-approval", "质检人工审批", "boolean", false, false, null,
                "默认开启；关闭后质检自动通过"));
        list.add(field("drama.video.max-attempts", "视频任务最大重试次数", "text", false, true, null,
                "默认 3"));
        list.add(field("drama.video.poll-interval-ms", "轮询间隔毫秒", "text", false, true, null,
                "默认 5000"));
        list.add(field("drama.storage", "媒体存储路径", "text", false, true, null,
                "默认 ./data/media"));
        list.add(field("harness.ui.theme", "默认主题", "select", false, false,
                List.of("light", "dark"), "默认 light"));
        list.add(field("harness.ui.language", "语言", "select", false, false,
                List.of("zh"), "预留，仅中文"));
        return list;
    }

    private Map<String, Object> field(String key, String label, String type, boolean secret,
                                      boolean restartRequired, List<String> options, String hint) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("key", key);
        m.put("label", label);
        m.put("type", type);
        m.put("secret", secret);
        m.put("restartRequired", restartRequired);
        if (options != null) {
            m.put("options", options);
        }
        if (hint != null) {
            m.put("hint", hint);
        }
        return m;
    }

    /**
     * 返回 schema 中允许的全部键集合。
     *
     * @return 键集合
     */
    public Set<String> allowedKeys() {
        Set<String> keys = new LinkedHashSet<>();
        for (Map<String, Object> f : schema()) {
            keys.add(String.valueOf(f.get("key")));
        }
        return keys;
    }
}
