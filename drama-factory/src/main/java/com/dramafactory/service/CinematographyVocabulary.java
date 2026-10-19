package com.dramafactory.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Optional;

/**
 * 镜头语言词汇表服务。
 *
 * <p>负责加载镜头语言词汇表（景别 / 运镜 / 机位 / 光线 / 构图），
 * 并把它渲染成英文 prompt 附录，供大模型在生成 videoPrompt 时使用统一的英文术语。</p>
 *
 * <p>加载顺序：优先读 {@code vocabPath} 指向的文件；若文件不存在，则回退读取
 * classpath 下的 {@code cinematography/vocabulary.json}；两者都失败时抛
 * {@link IllegalStateException}（启动期大声失败，绝不静默返回空词表）。</p>
 *
 * <p>本类线程安全：加载后的数据结构不可变，对外暴露的方法均为无状态读取。</p>
 */
@Service
public class CinematographyVocabulary {

    /** classpath 下的默认词表资源路径。 */
    private static final String CLASSPATH_RESOURCE = "cinematography/vocabulary.json";

    /** 词表版本号。 */
    private final String version;

    /** 景别条目（中文 label 与英文术语的映射）。 */
    private final List<Entry> shotSize;

    /** 运镜条目。 */
    private final List<Entry> cameraMove;

    /** 机位条目（中文 zh / 英文 en）。 */
    private final List<ZhEntry> cameraAngle;

    /** 光线条目。 */
    private final List<ZhEntry> lighting;

    /** 构图条目。 */
    private final List<ZhEntry> composition;

    /**
     * 构造器：按顺序尝试从 vocabPath 文件、classpath 资源加载词表。
     *
     * @param vocabPath    自定义词表路径（可为相对或绝对路径）
     * @param objectMapper Jackson 解析器
     * @throws IllegalStateException 两处来源都无法加载或解析失败时抛出
     */
    public CinematographyVocabulary(
            @Value("${drama.cinematography.vocab-path:data/cinematography/vocabulary.json}") String vocabPath,
            ObjectMapper objectMapper) {
        JsonNode root = load(vocabPath, objectMapper);
        this.version = root.path("version").asText("");
        this.shotSize = Collections.unmodifiableList(parseEntries(root.path("shotSize")));
        this.cameraMove = Collections.unmodifiableList(parseEntries(root.path("cameraMove")));
        this.cameraAngle = Collections.unmodifiableList(parseZhEntries(root.path("cameraAngle")));
        this.lighting = Collections.unmodifiableList(parseZhEntries(root.path("lighting")));
        this.composition = Collections.unmodifiableList(parseZhEntries(root.path("composition")));
    }

    /**
     * 按既定顺序加载词表 JSON。
     *
     * @param vocabPath    自定义路径
     * @param objectMapper 解析器
     * @return 根节点
     */
    private static JsonNode load(String vocabPath, ObjectMapper objectMapper) {
        if (vocabPath != null && !vocabPath.isBlank()) {
            Path path = Paths.get(vocabPath);
            if (Files.isRegularFile(path)) {
                try {
                    String text = Files.readString(path, StandardCharsets.UTF_8);
                    return objectMapper.readTree(text);
                } catch (Exception e) {
                    throw new IllegalStateException(
                            "解析镜头语言词汇表文件失败: " + path.toAbsolutePath() + " - " + e.getMessage(), e);
                }
            }
        }
        try (InputStream in = CinematographyVocabulary.class.getClassLoader()
                .getResourceAsStream(CLASSPATH_RESOURCE)) {
            if (in == null) {
                throw new IllegalStateException(
                        "镜头语言词汇表加载失败：文件 " + vocabPath + " 不存在，且 classpath 资源 "
                                + CLASSPATH_RESOURCE + " 缺失");
            }
            String text = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            return objectMapper.readTree(text);
        } catch (IllegalStateException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalStateException(
                    "解析 classpath 镜头语言词汇表失败: " + CLASSPATH_RESOURCE + " - " + e.getMessage(), e);
        }
    }

    /**
     * 解析 label/en/alt 结构数组。
     *
     * @param array JSON 数组节点
     * @return 条目列表
     */
    private static List<Entry> parseEntries(JsonNode array) {
        List<Entry> list = new ArrayList<>();
        if (array != null && array.isArray()) {
            for (JsonNode node : array) {
                String label = node.path("label").asText(null);
                String en = node.path("en").asText(null);
                List<String> alt = new ArrayList<>();
                JsonNode altNode = node.get("alt");
                if (altNode != null && altNode.isArray()) {
                    for (JsonNode a : altNode) {
                        if (a != null && !a.isNull()) {
                            alt.add(a.asText());
                        }
                    }
                }
                list.add(new Entry(label, en, Collections.unmodifiableList(alt)));
            }
        }
        return list;
    }

    /**
     * 解析 zh/en/alt 结构数组。
     *
     * @param array JSON 数组节点
     * @return 条目列表
     */
    private static List<ZhEntry> parseZhEntries(JsonNode array) {
        List<ZhEntry> list = new ArrayList<>();
        if (array != null && array.isArray()) {
            for (JsonNode node : array) {
                String zh = node.path("zh").asText(null);
                String en = node.path("en").asText(null);
                List<String> alt = new ArrayList<>();
                JsonNode altNode = node.get("alt");
                if (altNode != null && altNode.isArray()) {
                    for (JsonNode a : altNode) {
                        if (a != null && !a.isNull()) {
                            alt.add(a.asText());
                        }
                    }
                }
                list.add(new ZhEntry(zh, en, Collections.unmodifiableList(alt)));
            }
        }
        return list;
    }

    /**
     * 渲染英文 prompt 附录，供大模型在生成 videoPrompt 时参考。
     *
     * @return 附录文本；词表为空时返回空串
     */
    public String renderAppendix() {
        StringBuilder sb = new StringBuilder();
        sb.append("## Cinematography vocabulary — use these exact English terms in \"videoPrompt\"\n");
        sb.append("Shot size (map your shotSize field value to English):\n");
        for (Entry e : shotSize) {
            sb.append("- ").append(e.label).append(" -> ").append(e.en);
            if (e.alt != null && !e.alt.isEmpty()) {
                sb.append("; also usable: ").append(String.join(", ", e.alt));
            }
            sb.append("\n");
        }
        sb.append("Camera movement (map your cameraMove field value to English):\n");
        for (Entry e : cameraMove) {
            sb.append("- ").append(e.label).append(" -> ").append(e.en);
            if (e.alt != null && !e.alt.isEmpty()) {
                sb.append("; also usable: ").append(String.join(", ", e.alt));
            }
            sb.append("\n");
        }
        sb.append("Optional camera angles (pick at most one when it fits the shot): ");
        sb.append(joinEn(cameraAngle));
        sb.append("\n");
        sb.append("Optional lighting keywords: ");
        sb.append(joinEn(lighting));
        sb.append("\n");
        sb.append("Optional composition keywords: ");
        sb.append(joinEn(composition));
        sb.append("\n");
        sb.append("Rules:\n");
        sb.append("1. In \"videoPrompt\", express shot size and camera movement ONLY with the English terms above — never invent translations.\n");
        sb.append("2. You MAY add one camera angle and/or one lighting/composition keyword when it fits; do not overload.\n");
        sb.append("3. Keep \"videoPrompt\" one paragraph, cinematic style, 16:9.\n");
        return sb.toString();
    }

    /**
     * 把 zh/en 条目列表拼接为逗号分隔的英文术语串。
     *
     * @param entries 条目列表
     * @return 英文术语串
     */
    private static String joinEn(List<ZhEntry> entries) {
        List<String> parts = new ArrayList<>();
        for (ZhEntry e : entries) {
            if (e.en != null && !e.en.isBlank()) {
                parts.add(e.en);
            }
        }
        return String.join(", ", parts);
    }

    /**
     * 查询景别中文标签对应的英文术语。
     *
     * @param zhLabel 中文标签（会先 trim）
     * @return 匹配的英文术语；找不到返回 {@link Optional#empty()}
     */
    public Optional<String> englishShotSize(String zhLabel) {
        return lookup(shotSize, zhLabel);
    }

    /**
     * 查询运镜中文标签对应的英文术语。
     *
     * @param zhLabel 中文标签（会先 trim）
     * @return 匹配的英文术语；找不到返回 {@link Optional#empty()}
     */
    public Optional<String> englishCameraMove(String zhLabel) {
        return lookup(cameraMove, zhLabel);
    }

    /**
     * 在条目列表中按中文标签精确匹配。
     *
     * @param entries 条目列表
     * @param zhLabel 中文标签
     * @return 英文术语；找不到返回 empty
     */
    private static Optional<String> lookup(List<Entry> entries, String zhLabel) {
        if (zhLabel == null) {
            return Optional.empty();
        }
        String trimmed = zhLabel.trim();
        if (trimmed.isEmpty()) {
            return Optional.empty();
        }
        for (Entry e : entries) {
            if (trimmed.equals(e.label)) {
                return Optional.ofNullable(e.en);
            }
        }
        return Optional.empty();
    }

    /**
     * 获取词表版本号。
     *
     * @return 版本号
     */
    public String getVersion() {
        return version;
    }

    /** label/en/alt 词表条目。 */
    private static final class Entry {
        private final String label;
        private final String en;
        private final List<String> alt;

        private Entry(String label, String en, List<String> alt) {
            this.label = label;
            this.en = en;
            this.alt = alt;
        }
    }

    /** zh/en/alt 词表条目。 */
    private static final class ZhEntry {
        private final String zh;
        private final String en;
        private final List<String> alt;

        private ZhEntry(String zh, String en, List<String> alt) {
            this.zh = zh;
            this.en = en;
            this.alt = alt;
        }
    }
}
