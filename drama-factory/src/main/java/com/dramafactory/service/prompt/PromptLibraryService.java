package com.dramafactory.service.prompt;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

@Service
public class PromptLibraryService {

    private static final Logger log = LoggerFactory.getLogger(PromptLibraryService.class);

    private static final String LOCATION_PATTERN = "classpath*:/prompt-library/**/*.md";
    private static final String MARKER = "/prompt-library/";
    private static final String ROOT_SOURCE = "根目录";
    private static final int SUMMARY_MAX = 200;

    private final List<PromptDetail> entries;
    private final Map<String, PromptDetail> byId;

    public PromptLibraryService() {
        List<PromptDetail> loaded = new ArrayList<>();
        PathMatchingResourcePatternResolver resolver = new PathMatchingResourcePatternResolver();
        try {
            Resource[] resources = resolver.getResources(LOCATION_PATTERN);
            for (Resource resource : resources) {
                try {
                    String relativePath = relativePathOf(resource);
                    if (relativePath == null || relativePath.isEmpty()) {
                        log.warn("提示词库文件路径无法解析，跳过：{}", resource.getDescription());
                        continue;
                    }
                    String content = readContent(resource);
                    String id = buildId(relativePath);
                    if (id.isEmpty()) {
                        log.warn("提示词库文件 id 为空，跳过：{}", relativePath);
                        continue;
                    }
                    String title = extractTitle(content, relativePath);
                    String source = extractSource(relativePath);
                    String summary = extractSummary(content);
                    loaded.add(new PromptDetail(id, title, source, relativePath, summary, content));
                } catch (Exception e) {
                    log.warn("读取提示词库文件失败，跳过：{}，原因：{}", resource.getDescription(), e.getMessage());
                }
            }
        } catch (IOException e) {
            log.warn("扫描提示词库失败：{}", e.getMessage());
        }

        loaded.sort(Comparator.comparing(PromptDetail::path));

        Map<String, PromptDetail> index = new LinkedHashMap<>();
        for (PromptDetail detail : loaded) {
            if (index.containsKey(detail.id())) {
                log.warn("提示词库 id 冲突，保留首次：{}", detail.id());
                continue;
            }
            index.put(detail.id(), detail);
        }
        this.entries = List.copyOf(index.values());
        this.byId = index;
        log.info("提示词库加载完成，共 {} 条记录", this.entries.size());
    }

    public List<PromptSummary> list(String q) {
        String keyword = q == null ? "" : q.trim().toLowerCase(Locale.ROOT);
        List<PromptSummary> result = new ArrayList<>();
        for (PromptDetail detail : entries) {
            if (keyword.isEmpty() || matches(detail, keyword)) {
                result.add(new PromptSummary(detail.id(), detail.title(), detail.source(),
                        detail.path(), detail.summary()));
            }
        }
        return result;
    }

    public Optional<PromptDetail> get(String id) {
        if (id == null) {
            return Optional.empty();
        }
        return Optional.ofNullable(byId.get(id));
    }

    private boolean matches(PromptDetail detail, String keyword) {
        String title = detail.title() == null ? "" : detail.title().toLowerCase(Locale.ROOT);
        String summary = detail.summary() == null ? "" : detail.summary().toLowerCase(Locale.ROOT);
        return title.contains(keyword) || summary.contains(keyword);
    }

    private String relativePathOf(Resource resource) throws IOException {
        String url = resource.getURL().toString();
        int idx = url.indexOf(MARKER);
        if (idx < 0) {
            return null;
        }
        String tail = url.substring(idx + MARKER.length());
        return URLDecoder.decode(tail, StandardCharsets.UTF_8);
    }

    private String readContent(Resource resource) throws IOException {
        try (InputStream in = resource.getInputStream()) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private String buildId(String relativePath) {
        String base = relativePath;
        if (base.toLowerCase(Locale.ROOT).endsWith(".md")) {
            base = base.substring(0, base.length() - 3);
        }
        return base.replace("/", "__");
    }

    private String extractTitle(String content, String relativePath) {
        for (String line : content.split("\\r?\\n")) {
            String trimmed = line.trim();
            if (trimmed.startsWith("# ")) {
                String title = trimmed.substring(2).trim();
                if (!title.isEmpty()) {
                    return title;
                }
            }
        }
        return fileNameWithoutExt(relativePath);
    }

    private String extractSource(String relativePath) {
        int slash = relativePath.indexOf('/');
        if (slash < 0) {
            return ROOT_SOURCE;
        }
        String first = relativePath.substring(0, slash);
        return first.isEmpty() ? ROOT_SOURCE : first;
    }

    private String extractSummary(String content) {
        String[] lines = content.split("\\r?\\n");
        boolean titleSeen = false;
        boolean paragraphStarted = false;
        StringBuilder paragraph = new StringBuilder();
        for (String line : lines) {
            String trimmed = line.trim();
            if (!titleSeen) {
                if (trimmed.startsWith("# ")) {
                    titleSeen = true;
                }
                continue;
            }
            if (trimmed.startsWith("#")) {
                break;
            }
            if (trimmed.isEmpty()) {
                if (paragraphStarted) {
                    break;
                }
                continue;
            }
            if (paragraphStarted) {
                paragraph.append(' ');
            }
            paragraph.append(trimmed);
            paragraphStarted = true;
        }
        if (!paragraphStarted) {
            return "";
        }
        String flat = paragraph.toString().replaceAll("\\s+", " ").trim();
        if (flat.isEmpty()) {
            return "";
        }
        if (flat.length() > SUMMARY_MAX) {
            return flat.substring(0, SUMMARY_MAX);
        }
        return flat;
    }

    private String fileNameWithoutExt(String relativePath) {
        String name = relativePath;
        int slash = name.lastIndexOf('/');
        if (slash >= 0) {
            name = name.substring(slash + 1);
        }
        if (name.toLowerCase(Locale.ROOT).endsWith(".md")) {
            name = name.substring(0, name.length() - 3);
        }
        return name;
    }

    public record PromptSummary(String id, String title, String source, String path, String summary) {}

    public record PromptDetail(String id, String title, String source, String path, String summary, String content) {}
}
