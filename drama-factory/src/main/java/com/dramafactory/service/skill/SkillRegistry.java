package com.dramafactory.service.skill;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Stream;

@Service
public class SkillRegistry {

    private static final Logger log = LoggerFactory.getLogger(SkillRegistry.class);

    private static final Pattern DIR_NAME_PATTERN = Pattern.compile("^[a-z0-9][a-z0-9._-]*$");

    private static final String BUNDLED_INDEX = "/skills-bundled/_index.json";

    private final Path skillsDir;

    private final List<SkillDescriptor> bundled = new ArrayList<>();

    private final Map<String, CachedInstalled> cache = new HashMap<>();

    private record CachedInstalled(Path dir, long mtime, InstalledSkill skill) {
    }

    public SkillRegistry(@Value("${drama.skills.dir:data/skills}") String skillsDir) {
        this.skillsDir = Paths.get(skillsDir);
        loadBundled();
    }

    private void loadBundled() {
        try (InputStream in = getClass().getResourceAsStream(BUNDLED_INDEX)) {
            if (in == null) {
                log.error("内置 skill 索引缺失，bundled 列表为空: {}", BUNDLED_INDEX);
                return;
            }
            ObjectMapper mapper = new ObjectMapper();
            JsonNode root = mapper.readTree(new String(in.readAllBytes(), StandardCharsets.UTF_8));
            JsonNode skills = root.get("skills");
            if (skills == null || !skills.isArray()) {
                log.error("内置 skill 索引格式非法，bundled 列表为空: {}", BUNDLED_INDEX);
                return;
            }
            for (JsonNode entry : skills) {
                String id = text(entry, "id");
                if (id == null || id.isBlank()) {
                    log.error("内置 skill 条目缺少 id，跳过: {}", entry);
                    continue;
                }
                String license = text(entry, "license");
                String originId = text(entry, "originId");
                String resource = "/skills-bundled/" + id + "/SKILL.md";
                try (InputStream skillIn = getClass().getResourceAsStream(resource)) {
                    if (skillIn == null) {
                        log.error("内置 skill 文件缺失，跳过: id={}, resource={}", id, resource);
                        continue;
                    }
                    String content = new String(skillIn.readAllBytes(), StandardCharsets.UTF_8);
                    SkillDescriptor descriptor;
                    try {
                        descriptor = SkillDescriptor.fromFrontmatter(
                                id, content, SkillDescriptor.Source.BUNDLED, license, originId);
                    } catch (IllegalArgumentException e) {
                        log.error("内置 skill 解析失败，跳过: id={}, resource={}, reason={}", id, resource, e.getMessage());
                        continue;
                    }
                    bundled.add(descriptor);
                } catch (IOException e) {
                    log.error("读取内置 skill 失败，跳过: id={}, resource={}, reason={}", id, resource, e.getMessage());
                }
            }
            bundled.sort(Comparator.comparing(SkillDescriptor::getId));
        } catch (IOException e) {
            log.error("解析内置 skill 索引失败，bundled 列表为空: {} ({})", BUNDLED_INDEX, e.getMessage());
        }
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node.get(field);
        return value == null || value.isNull() ? null : value.asText();
    }

    public List<SkillDescriptor> bundled() {
        return List.copyOf(bundled);
    }

    public Optional<SkillDescriptor> bundledOf(String id) {
        if (id == null || id.isBlank()) {
            return Optional.empty();
        }
        return bundled.stream().filter(s -> id.equals(s.getId())).findFirst();
    }

    public synchronized void reloadIfChanged() {
        if (!Files.isDirectory(skillsDir)) {
            return;
        }
        Set<String> seen = new HashSet<>();
        try (Stream<Path> stream = Files.list(skillsDir)) {
            stream.filter(Files::isDirectory)
                    .filter(p -> !p.getFileName().toString().startsWith("."))
                    .forEach(dir -> {
                        String id = dir.getFileName().toString();
                        if (!DIR_NAME_PATTERN.matcher(id).matches()) {
                            log.warn("安装目录名非法，跳过: {}", id);
                            return;
                        }
                        Path skillMd = dir.resolve("SKILL.md");
                        if (!Files.isRegularFile(skillMd)) {
                            return;
                        }
                        long mtime;
                        try {
                            mtime = Files.getLastModifiedTime(skillMd).toMillis();
                        } catch (IOException e) {
                            log.warn("读取已安装 skill 修改时间失败: {} ({})", skillMd, e.getMessage());
                            return;
                        }
                        CachedInstalled cached = cache.get(id);
                        if (cached != null && cached.mtime() == mtime && cached.dir().equals(dir)) {
                            seen.add(id);
                            return;
                        }
                        String content;
                        try {
                            content = Files.readString(skillMd, StandardCharsets.UTF_8);
                        } catch (IOException e) {
                            log.warn("读取已安装 skill 失败: {} ({})", skillMd, e.getMessage());
                            return;
                        }
                        SkillDescriptor descriptor;
                        try {
                            descriptor = SkillDescriptor.fromFrontmatter(id, content, SkillDescriptor.Source.SKILLHUB, "", null);
                        } catch (IllegalArgumentException e) {
                            log.warn("已安装 skill frontmatter 非法，跳过: {} ({})", skillMd, e.getMessage());
                            return;
                        }
                        cache.put(id, new CachedInstalled(dir, mtime, new InstalledSkill(id, descriptor.getVersion(), dir)));
                        seen.add(id);
                    });
            cache.keySet().removeIf(k -> !seen.contains(k));
        } catch (IOException e) {
            log.warn("遍历已安装 skill 目录失败: {} ({})", skillsDir, e.getMessage());
            return;
        }
    }

    public List<InstalledSkill> installed() {
        reloadIfChanged();
        List<InstalledSkill> list = new ArrayList<>();
        for (CachedInstalled c : cache.values()) {
            list.add(c.skill());
        }
        list.sort(Comparator.comparing(InstalledSkill::id));
        return list;
    }

    public Optional<InstalledSkill> installedOf(String id) {
        reloadIfChanged();
        if (id == null || id.isEmpty()) {
            return Optional.empty();
        }
        CachedInstalled c = cache.get(id);
        return c == null ? Optional.empty() : Optional.of(c.skill());
    }

    public record InstalledSkill(String id, String version, Path dir) {
    }
}
