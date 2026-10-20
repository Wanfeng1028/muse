package com.dramafactory.service.prompt;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

@Service

public class PromptLibraryService {

    private static final Logger log = LoggerFactory.getLogger(PromptLibraryService.class);

    private static final String LOCATION_PATTERN = "classpath*:/prompt-library/**/*.md";
    private static final String MARKER = "/prompt-library/";
    private static final String ROOT_SOURCE = "根目录";
    private static final int SUMMARY_MAX = 200;
    private static final String FAVORITES_DIR = ".drama-factory";
    private static final String FAVORITES_FILE = "prompt-favorites.json";

    private final List<PromptDetail> entries;

    private final Map<String, PromptDetail> byId;
    private final Set<String> favorites = ConcurrentHashMap.newKeySet();

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
        loadFavorites();
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

    public Page<PromptSummary> list(String q, String tag, int page, int size) {
        String keyword = q == null ? "" : q.trim().toLowerCase(Locale.ROOT);
        String tagFilter = tag == null ? "" : tag.trim();
        List<PromptSummary> filtered = new ArrayList<>();
        for (PromptDetail detail : entries) {
            if (!keyword.isEmpty() && !matches(detail, keyword)) {
                continue;
            }
            if (!tagFilter.isEmpty() && !tagFilter.equals(detail.source())) {
                continue;
            }
            filtered.add(new PromptSummary(detail.id(), detail.title(), detail.source(),
                    detail.path(), detail.summary()));
        }
        int normalizedPage = page < 0 ? 0 : page;
        int normalizedSize = size <= 0 ? 20 : Math.min(size, 100);
        long totalElements = filtered.size();
        int totalPages = totalElements == 0 ? 0 : (int) ((totalElements + normalizedSize - 1) / normalizedSize);
        long from = (long) normalizedPage * normalizedSize;
        List<PromptSummary> content;
        if (from >= totalElements) {
            content = new ArrayList<>();
        } else {
            int start = (int) from;
            int end = (int) Math.min(from + normalizedSize, totalElements);
            content = new ArrayList<>(filtered.subList(start, end));
        }

        return new Page<>(content, normalizedPage, normalizedSize, totalElements, totalPages);
    }

    public Optional<PromptDetail> get(String id) {

        if (id == null) {
            return Optional.empty();
        }
        return Optional.ofNullable(byId.get(id));
    }

    public List<String> tags() {
        Set<String> unique = new LinkedHashSet<>();
        for (PromptDetail detail : entries) {
            unique.add(detail.source());
        }
        List<String> result = new ArrayList<>(unique);
        result.sort(Comparator.naturalOrder());
        return result;
    }


    public boolean addFavorite(String id) {
        if (id == null || !byId.containsKey(id)) {
            return false;
        }
        if (favorites.contains(id)) {
            return true;
        }
        favorites.add(id);
        saveFavorites();
        return true;
    }

    public boolean removeFavorite(String id) {
        if (id == null || !byId.containsKey(id)) {
            return false;
        }
        if (!favorites.contains(id)) {
            return true;
        }
        favorites.remove(id);
        saveFavorites();
        return true;
    }

    public boolean isFavorite(String id) {
        if (id == null) {
            return false;
        }
        return favorites.contains(id);
    }

    public List<PromptSummary> favorites() {
        List<PromptSummary> result = new ArrayList<>();
        for (PromptDetail detail : entries) {
            if (favorites.contains(detail.id())) {
                result.add(new PromptSummary(detail.id(), detail.title(), detail.source(),
                        detail.path(), detail.summary()));
            }
        }
        return result;
    }

    private void loadFavorites() {
        Path file = favoritesFile();
        if (file == null) {
            log.warn("无法确定用户主目录，跳过收藏加载");
            return;
        }
        if (!Files.exists(file)) {
            return;
        }
        try {
            ObjectMapper mapper = new ObjectMapper();
            List<String> ids = mapper.readValue(file.toFile(), new TypeReference<List<String>>() {});
            if (ids != null) {
                for (String id : ids) {
                    if (id != null && byId.containsKey(id)) {
                        favorites.add(id);
                    }
                }
            }
        } catch (Exception e) {
            log.warn("加载收藏失败，使用空集合：{}", e.getMessage());
            favorites.clear();
        }
    }


    private void saveFavorites() {
        Path file = favoritesFile();
        if (file == null) {
            log.warn("无法确定用户主目录，跳过收藏保存");
            return;
        }
        try {
            Files.createDirectories(file.getParent());
            List<String> ids = new ArrayList<>(favorites);
            Collections.sort(ids);
            ObjectMapper mapper = new ObjectMapper();
            Path tmp = Files.createTempFile(file.getParent(), "prompt-favorites", ".tmp");
            try {
                mapper.writeValue(tmp.toFile(), ids);
                try {
                    Files.move(tmp, file, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
                } catch (AtomicMoveNotSupportedException e) {
                    Files.move(tmp, file, StandardCopyOption.REPLACE_EXISTING);
                }
            } finally {
                Files.deleteIfExists(tmp);
            }
        } catch (Exception e) {
            log.warn("保存收藏失败：{}", e.getMessage());
        }
    }

    private Path favoritesFile() {
        String home = System.getProperty("user.home");
        if (home == null || home.isBlank()) {
            return null;
        }
        return Paths.get(home, FAVORITES_DIR, FAVORITES_FILE);
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

    public record Page<T>(List<T> content, int page, int size, long totalElements, int totalPages) {}

    public record PromptSummary(String id, String title, String source, String path, String summary) {}

    public record PromptDetail(String id, String title, String source, String path, String summary, String content) {}
}
