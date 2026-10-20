package com.dramafactory.service.skill;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import static org.assertj.core.api.Assertions.assertThat;

class SkillRegistryIndexDeepR2Test {

    private static final String INDEX_RESOURCE = "/skills-bundled/_index.json";
    private static final Path BUNDLED_DIR = Paths.get("src/main/resources/skills-bundled");

    private static SkillRegistry registry;
    private static JsonNode indexRoot;

    @BeforeAll
    static void loadAll() throws Exception {
        registry = new SkillRegistry("data/skills-nonexistent-deep-r2");
        ObjectMapper mapper = new ObjectMapper();
        try (InputStream in = SkillRegistryIndexDeepR2Test.class.getResourceAsStream(INDEX_RESOURCE)) {
            assertThat(in).as("主索引必须存在: " + INDEX_RESOURCE).isNotNull();
            indexRoot = mapper.readTree(new String(in.readAllBytes(), StandardCharsets.UTF_8));
        }
    }

    private static List<JsonNode> indexEntries() {
        List<JsonNode> list = new ArrayList<>();
        for (JsonNode entry : indexRoot.get("skills")) {
            list.add(entry);
        }
        return list;
    }

    private static Set<String> indexIds() {
        Set<String> ids = new HashSet<>();
        for (JsonNode entry : indexEntries()) {
            ids.add(entry.get("id").asText());
        }
        return ids;
    }

    private static Set<String> directoryIds() throws Exception {
        Set<String> ids = new HashSet<>();
        try (Stream<Path> stream = Files.list(BUNDLED_DIR)) {
            stream.filter(Files::isDirectory)
                    .forEach(p -> ids.add(p.getFileName().toString()));
        }
        return ids;
    }

    @Test
    void directoryCountEqualsIndexEntryCount() throws Exception {
        assertThat(directoryIds().size()).isEqualTo(indexEntries().size());
    }

    @Test
    void indexEntryCountMatchesDirectoryCount() throws Exception {
        // 不硬编码数量（技能库在持续扩充）：只断言索引条目数与目录数一致且大于 0
        assertThat(indexEntries().size()).isEqualTo(directoryIds().size());
        assertThat(indexEntries()).isNotEmpty();
    }

    @Test
    void everyDirectoryIdExistsInIndex() throws Exception {
        Set<String> indexIds = indexIds();
        List<String> missing = directoryIds().stream()
                .filter(id -> !indexIds.contains(id))
                .collect(Collectors.toList());
        assertThat(missing).isEmpty();
    }

    @Test
    void everyIndexIdHasCorrespondingDirectory() throws Exception {
        Set<String> dirIds = directoryIds();
        List<String> missing = indexIds().stream()
                .filter(id -> !dirIds.contains(id))
                .collect(Collectors.toList());
        assertThat(missing).isEmpty();
    }

    @Test
    void everyIndexIdHasSkillMdFile() throws Exception {
        List<String> missing = new ArrayList<>();
        for (String id : indexIds()) {
            if (!Files.isRegularFile(BUNDLED_DIR.resolve(id).resolve("SKILL.md"))) {
                missing.add(id);
            }
        }
        assertThat(missing).isEmpty();
    }

    @Test
    void noasssertionLicenseEntriesContainKwindlaCaptionClip() {
        assertThat(noasssertionIds()).contains("kwindla-caption-clip");
    }

    @Test
    void noasssertionLicenseEntriesContainElsalvatoreVideoEditor() {
        assertThat(noasssertionIds()).contains("elsalvatore-video-editor");
    }

    @Test
    void noasssertionLicenseEntriesContainWatzingVideoEditor() {
        assertThat(noasssertionIds()).contains("watzing-video-editor");
    }

    @Test
    void noasssertionLicenseEntriesContainJordantobyllVideoEdit() {
        assertThat(noasssertionIds()).contains("jordantobyll-video-edit");
    }

    @Test
    void noasssertionLicenseEntriesContainJordantobyllPan3dTransition() {
        assertThat(noasssertionIds()).contains("jordantobyll-pan-3d-transition");
    }

    private static Set<String> noasssertionIds() {
        Set<String> ids = new HashSet<>();
        for (JsonNode entry : indexEntries()) {
            JsonNode license = entry.get("license");
            if (license != null && "NOASSERTION".equals(license.asText())) {
                ids.add(entry.get("id").asText());
            }
        }
        return ids;
    }

    @Test
    void licenseRulingEntriesHaveRewrittenFalse() {
        // 2026-10-20 许可证裁决的 17 个条目必须保持 rewritten=false（其余新增条目由其他 lane 负责）
        Set<String> rulingIds = Set.of("talking-head-guide",
                "waoowaoo-creative-core", "waoowaoo-creative-direction", "waoowaoo-script-development",
                "waoowaoo-asset-development", "waoowaoo-video-direction", "waoowaoo-music-direction",
                "huobao-extractor", "huobao-script-rewriter", "huobao-storyboard-breaker",
                "huobao-character-prompt", "huobao-scene-prompt", "huobao-prop-prompt", "huobao-video-prompt",
                "watzing-video-editor", "jordantobyll-video-edit", "jordantobyll-pan-3d-transition");
        Map<String, JsonNode> byId = new java.util.HashMap<>();
        for (JsonNode entry : indexEntries()) {
            byId.put(entry.get("id").asText(), entry);
        }
        List<String> offenders = new ArrayList<>();
        for (String id : rulingIds) {
            JsonNode e = byId.get(id);
            if (e == null) {
                offenders.add(id + "(缺失)");
            } else if (e.get("rewritten") == null || e.get("rewritten").asBoolean()) {
                offenders.add(id);
            }
        }
        assertThat(offenders).isEmpty();
    }

    @Test
    void noLicenseFieldContainsRewrittenSuffix() {
        List<String> offenders = new ArrayList<>();
        for (JsonNode entry : indexEntries()) {
            JsonNode license = entry.get("license");
            if (license != null && license.asText().contains("(rewritten)")) {
                offenders.add(entry.get("id").asText());
            }
        }
        assertThat(offenders).isEmpty();
    }

    @Test
    void restoredWaoowaooEntriesLookupByIdAndHaveNonEmptySourceUrl() {
        List<String> waoowaoo = indexIds().stream()
                .filter(id -> id.startsWith("waoowaoo"))
                .collect(Collectors.toList());
        assertThat(waoowaoo).hasSize(6);
        Map<String, String> sourceUrls = sourceUrlById();
        for (String id : waoowaoo) {
            assertThat(registry.bundledOf(id)).as("registry 应能查到 " + id).isPresent();
            assertThat(sourceUrls.get(id)).as(id + " sourceUrl 非空").isNotBlank();
        }
    }

    @Test
    void restoredHuobaoEntriesLookupByIdAndHaveNonEmptySourceUrl() {
        List<String> huobao = indexIds().stream()
                .filter(id -> id.startsWith("huobao"))
                .collect(Collectors.toList());
        assertThat(huobao).hasSize(7);
        Map<String, String> sourceUrls = sourceUrlById();
        for (String id : huobao) {
            assertThat(registry.bundledOf(id)).as("registry 应能查到 " + id).isPresent();
            assertThat(sourceUrls.get(id)).as(id + " sourceUrl 非空").isNotBlank();
        }
    }

    private static Map<String, String> sourceUrlById() {
        Map<String, String> map = new HashMap<>();
        for (JsonNode entry : indexEntries()) {
            JsonNode sourceUrl = entry.get("sourceUrl");
            if (sourceUrl != null && !sourceUrl.isNull()) {
                map.put(entry.get("id").asText(), sourceUrl.asText());
            }
        }
        return map;
    }
}