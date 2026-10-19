package com.dramafactory.service.skill;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.yaml.snakeyaml.Yaml;

import java.util.Map;
import java.util.Objects;

public final class SkillDescriptor {

    private static final Logger log = LoggerFactory.getLogger(SkillDescriptor.class);

    private final String id;
    private final String name;
    private final String version;
    private final String description;
    private final String author;
    private final String license;
    private final String originId;
    private final Source source;

    public enum Source {
        BUNDLED,
        SKILLHUB
    }

    public SkillDescriptor(String id, String name, String version, String description,
                           String author, String license, String originId, Source source) {
        if (id == null || id.isEmpty()) {
            throw new IllegalArgumentException("id 不能为 null 或空");
        }
        if (name == null || name.isEmpty()) {
            throw new IllegalArgumentException("name 不能为 null 或空");
        }
        if (source == null) {
            throw new IllegalArgumentException("source 不能为 null");
        }
        this.id = id;
        this.name = name;
        this.version = version == null ? "" : version;
        this.description = description == null ? "" : description;
        this.author = author == null ? "" : author;
        this.license = license == null ? "" : license;
        this.originId = originId;
        this.source = source;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getVersion() {
        return version;
    }

    public String getDescription() {
        return description;
    }

    public String getAuthor() {
        return author;
    }

    public String getLicense() {
        return license;
    }

    public String getOriginId() {
        return originId;
    }

    public Source getSource() {
        return source;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) {
            return true;
        }
        if (!(o instanceof SkillDescriptor other)) {
            return false;
        }
        return Objects.equals(id, other.id)
                && Objects.equals(name, other.name)
                && Objects.equals(version, other.version)
                && Objects.equals(description, other.description)
                && Objects.equals(author, other.author)
                && Objects.equals(license, other.license)
                && Objects.equals(originId, other.originId)
                && source == other.source;
    }

    @Override
    public int hashCode() {
        return Objects.hash(id, name, version, description, author, license, originId, source);
    }

    @Override
    public String toString() {
        return "SkillDescriptor{"
                + "id='" + id + '\''
                + ", name='" + name + '\''
                + ", version='" + version + '\''
                + ", description='" + description + '\''
                + ", author='" + author + '\''
                + ", license='" + license + '\''
                + ", originId='" + originId + '\''
                + ", source=" + source
                + '}';
    }

    public static SkillDescriptor fromFrontmatter(String id, String skillMd, Source source,
                                                  String defaultLicense, String originId) {
        if (id == null || id.isEmpty()) {
            throw new IllegalArgumentException("id 不能为 null 或空");
        }
        if (skillMd == null) {
            throw new IllegalArgumentException("skill.md 内容为 null: " + id);
        }
        if (source == null) {
            throw new IllegalArgumentException("source 不能为 null: " + id);
        }
        if (!skillMd.startsWith("---\n")) {
            throw new IllegalArgumentException("skill.md 缺少 frontmatter 起始标记 '---': " + id);
        }
        int end = skillMd.indexOf("\n---\n", 3);
        if (end < 0) {
            throw new IllegalArgumentException("skill.md 缺少 frontmatter 结束标记 '---': " + id);
        }
        String yamlBlock = skillMd.substring(3, end + 1);
        try {
            Object loaded = new Yaml().load(yamlBlock);
            if (loaded == null) {
                throw new IllegalArgumentException("frontmatter 为空: " + id);
            }
            if (!(loaded instanceof Map<?, ?> raw)) {
                throw new IllegalArgumentException("frontmatter 不是 Map: " + id);
            }
            @SuppressWarnings("unchecked")
            Map<String, Object> typed = (Map<String, Object>) raw;
            Object nameObj = typed.get("name");
            String name = asString(nameObj);
            if (name == null || name.trim().isEmpty()) {
                throw new IllegalArgumentException("Missing required 'name' in frontmatter for skill id=" + id);
            }
            String version = asString(typed.get("version"));
            if (version == null) {
                version = "";
            }
            String description = asString(typed.get("description"));
            if (description == null) {
                description = "";
            }
            String author = asString(typed.get("author"));
            if (author == null) {
                author = "";
            }
            String license = null;
            Object metadataObj = typed.get("metadata");
            if (metadataObj instanceof Map) {
                Map<?, ?> metadata = (Map<?, ?>) metadataObj;
                license = asString(metadata.get("license"));
            }
            if (license == null) {
                license = defaultLicense == null ? "" : defaultLicense;
            }
            return new SkillDescriptor(id, name, version, description, author, license, originId, source);
        } catch (RuntimeException e) {
            throw new IllegalArgumentException("frontmatter YAML 解析失败: " + id + " (" + e.getMessage() + ")", e);
        }
    }

    private static String asString(Object o) {
        return o == null ? null : String.valueOf(o);
    }

    public static int compareVersions(String a, String b) {
        String left = a == null ? "" : a;
        String right = b == null ? "" : b;
        if (left.equals(right)) {
            return 0;
        }
        String[] leftTokens = left.split("[.-]");
        String[] rightTokens = right.split("[.-]");
        int max = Math.max(leftTokens.length, rightTokens.length);
        for (int i = 0; i < max; i++) {
            String lt = i < leftTokens.length ? leftTokens[i] : "0";
            String rt = i < rightTokens.length ? rightTokens[i] : "0";
            boolean ln = lt.matches("\\d+");
            boolean rn = rt.matches("\\d+");
            int cmp;
            if (ln && rn) {
                long lv;
                long rv;
                try {
                    lv = Long.parseLong(lt);
                } catch (NumberFormatException e) {
                    lv = -1L;
                }
                try {
                    rv = Long.parseLong(rt);
                } catch (NumberFormatException e) {
                    rv = -1L;
                }
                if (lv >= 0 && rv >= 0) {
                    cmp = Long.compare(lv, rv);
                } else {
                    cmp = lt.compareTo(rt);
                }
            } else {
                cmp = lt.compareTo(rt);
            }
            if (cmp != 0) {
                return cmp;
            }
        }
        return 0;
    }
}
