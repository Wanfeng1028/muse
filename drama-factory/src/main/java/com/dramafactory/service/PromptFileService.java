package com.dramafactory.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

/**
 * 外置提示词文件服务。
 *
 * <p>提示词以带 frontmatter 的 Markdown 文件形式存放在数据目录（默认 {@code data/prompts}），
 * 修改提示词无需改代码、无需重启：每次读取前按文件 mtime 判断是否需要重新加载。</p>
 *
 * <p>文件格式：</p>
 * <pre>
 * ---
 * name: shot-splitter
 * version: 1.0.0
 * description: 分镜拆分系统提示词
 * ---
 *
 * 正文……
 * </pre>
 *
 * <p>正文中支持 {@code {{key}}} 占位符，通过 {@link #render(String, Map)} 替换。</p>
 */
@Service
public class PromptFileService {

    private static final Logger log = LoggerFactory.getLogger(PromptFileService.class);

    /** 允许的提示词文件名。 */
    private static final Pattern FILE_NAME_PATTERN = Pattern.compile("^[a-zA-Z0-9][a-zA-Z0-9._-]*\\.md$");

    /** {{key}} 占位符。 */
    private static final Pattern VARIABLE_PATTERN = Pattern.compile("\\{\\{\\s*([a-zA-Z0-9_.-]+)\\s*}}");

    private final Path dir;

    private final Map<String, CachedPrompt> cache = new HashMap<>();

    public PromptFileService(@Value("${drama.prompts.dir:data/prompts}") String dir) {
        this.dir = Paths.get(dir);
    }

    /**
     * 提示词文件解析结果。
     *
     * @param name        提示词名称（frontmatter 中的 name）
     * @param version     版本，缺省空串
     * @param description 描述，缺省空串
     * @param body        正文（分隔线之后全文，去掉开头空行）
     */
    public record PromptFile(String name, String version, String description, String body) {
    }

    private record CachedPrompt(Path file, long mtime, PromptFile prompt) {
    }

    /**
     * 按 mtime 检查并重新加载提示词目录。目录不存在时直接返回。
     * 遍历目录下一级 {@code *.md}（不递归，跳过 "." 开头的文件），
     * 文件名不匹配、解析失败、mtime 未变则跳过，并移除已删除文件的缓存。
     */
    public synchronized void reloadIfChanged() {
        if (!Files.isDirectory(dir)) {
            return;
        }
        Set<String> seen = new HashSet<>();
        try (Stream<Path> stream = Files.list(dir)) {
            stream.filter(Files::isRegularFile)
                    .filter(p -> !p.getFileName().toString().startsWith("."))
                    .filter(p -> FILE_NAME_PATTERN.matcher(p.getFileName().toString()).matches())
                    .forEach(p -> {
                        try {
                            long mtime = Files.getLastModifiedTime(p).toMillis();
                            CachedPrompt existing = cache.get(p.getFileName().toString());
                            if (existing != null && existing.mtime() == mtime) {
                                seen.add(p.getFileName().toString());
                                return;
                            }
                            PromptFile parsed = parse(p);
                            if (parsed == null) {
                                return;
                            }
                            cache.put(p.getFileName().toString(), new CachedPrompt(p, mtime, parsed));
                            seen.add(p.getFileName().toString());
                        } catch (IOException e) {
                            log.warn("读取提示词文件失败，跳过: {} ({})", p, e.getMessage());
                        }
                    });
        } catch (IOException e) {
            log.warn("遍历提示词目录失败: {} ({})", dir, e.getMessage());
            return;
        }
        cache.keySet().removeIf(k -> !seen.contains(k));
    }

    /**
     * 读取指定名称提示词的正文。
     *
     * @param name 提示词名称（不含 .md 后缀）
     * @throws IllegalArgumentException 未找到对应提示词文件
     */
    public String body(String name) {
        reloadIfChanged();
        PromptFile prompt = cache.get(name + ".md") != null
                ? cache.get(name + ".md").prompt()
                : null;
        if (prompt == null) {
            throw new IllegalArgumentException("未找到提示词文件: " + name + "（在 data/prompts/ 下放置 <name>.md）");
        }
        return prompt.body();
    }

    /**
     * 读取提示词正文并替换 {@code {{key}}} 占位符，缺失的 key 替换为空串。
     */
    public String render(String name, Map<String, String> vars) {
        String body = body(name);
        if (vars == null || vars.isEmpty()) {
            return VARIABLE_PATTERN.matcher(body).replaceAll("");
        }
        Matcher matcher = VARIABLE_PATTERN.matcher(body);
        StringBuilder sb = new StringBuilder();
        while (matcher.find()) {
            String key = matcher.group(1);
            String value = vars.get(key);
            matcher.appendReplacement(sb, Matcher.quoteReplacement(value == null ? "" : value));
        }
        matcher.appendTail(sb);
        return sb.toString();
    }

    /**
     * 返回已加载的提示词名称集合副本（不含 .md 后缀）。
     */
    public Set<String> names() {
        reloadIfChanged();
        Set<String> result = new HashSet<>();
        for (String fileName : cache.keySet()) {
            if (fileName.endsWith(".md")) {
                result.add(fileName.substring(0, fileName.length() - 3));
            }
        }
        return result;
    }

    /**
     * 解析单个提示词文件。无 frontmatter 或 name 为空时返回 null。
     */
    private PromptFile parse(Path file) {
        String content;
        try {
            content = Files.readString(file, StandardCharsets.UTF_8);
        } catch (IOException e) {
            log.warn("读取提示词文件失败，跳过: {} ({})", file, e.getMessage());
            return null;
        }
        if (!content.startsWith("---\n")) {
            log.warn("提示词文件缺少 frontmatter，跳过: {}", file);
            return null;
        }
        int end = content.indexOf("\n---\n", 3);
        if (end < 0) {
            log.warn("提示词文件 frontmatter 未闭合，跳过: {}", file);
            return null;
        }
        String header = content.substring(4, end);
        String body = content.substring(end + 5);
        // 规范化：去掉开头空行（含 \r\n）与结尾所有空白字符。
        // 手写 md 文件难免带结尾换行，结尾空白对提示词语义无影响，规范化后行为可预测。
        int start = 0;
        while (start < body.length() && (body.charAt(start) == '\n' || body.charAt(start) == '\r')) {
            start++;
        }
        int stop = body.length();
        while (stop > start && Character.isWhitespace(body.charAt(stop - 1))) {
            stop--;
        }
        body = body.substring(start, stop);

        String name = null;

        String version = "";
        String description = "";
        for (String line : header.split("\n", -1)) {
            int idx = line.indexOf(':');
            if (idx < 0) {
                continue;
            }
            String key = line.substring(0, idx).trim();
            String value = line.substring(idx + 1).trim();
            switch (key) {
                case "name" -> name = value;
                case "version" -> version = value;
                case "description" -> description = value;
                default -> {
                }
            }
        }
        if (name == null || name.isEmpty()) {
            log.warn("提示词文件 frontmatter 缺少 name，跳过: {}", file);
            return null;
        }
        return new PromptFile(name, version, description, body);
    }
}

