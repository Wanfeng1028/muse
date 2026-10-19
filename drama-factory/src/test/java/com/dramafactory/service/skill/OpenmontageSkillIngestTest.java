package com.dramafactory.service.skill;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * OpenMontage skill 库收录（任务 C）的验收测试：
 * 1) 从主索引 _index.json 中过滤出 source=calesthio/OpenMontage 的条目；
 * 2) 逐条 SKILL.md 与索引双向一致（round-trip）；
 * 3) 抽查 3 个具体 id 存在且 description 非空。
 * 纯单测：不发真实 HTTP，只读 classpath 资源。
 */
class OpenmontageSkillIngestTest {

    private static final String MAIN_INDEX = "/skills-bundled/_index.json";
    private static final String SOURCE = "calesthio/OpenMontage";
    private static final String SOURCE_URL = "https://github.com/calesthio/OpenMontage";
    private static final String LICENSE = "AGPL-3.0";

    private static String readResource(String path) throws Exception {
        try (InputStream in = OpenmontageSkillIngestTest.class.getResourceAsStream(path)) {
            assertNotNull(in, "资源缺失: " + path);
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private static List<JsonNode> openmontageEntries(JsonNode root) {
        JsonNode skills = root.get("skills");
        assertNotNull(skills, "主索引缺少 skills 数组");
        assertTrue(skills.isArray(), "skills 不是数组");
        List<JsonNode> result = new ArrayList<>();
        for (JsonNode e : skills) {
            if (e.has("source") && SOURCE.equals(e.get("source").asText())) {
                result.add(e);
            }
        }
        return result;
    }

    @Test
    void mainIndexContainsAtLeast150OpenmontageEntries() throws Exception {
        JsonNode root = new ObjectMapper().readTree(readResource(MAIN_INDEX));
        List<JsonNode> entries = openmontageEntries(root);
        assertTrue(entries.size() >= 150,
                "OpenMontage 条目数量不足: " + entries.size());
    }

    @Test
    void mainIndexIdsAreGloballyUnique() throws Exception {
        JsonNode root = new ObjectMapper().readTree(readResource(MAIN_INDEX));
        JsonNode skills = root.get("skills");
        assertNotNull(skills, "主索引缺少 skills 数组");
        assertTrue(skills.isArray(), "skills 不是数组");
        Set<String> seen = new HashSet<>();
        List<String> duplicates = new ArrayList<>();
        for (JsonNode e : skills) {
            String id = e.get("id").asText();
            if (!seen.add(id)) {
                duplicates.add(id);
            }
        }
        assertTrue(duplicates.isEmpty(), "主索引 id 重复: " + duplicates);
    }

    @Test
    void openmontageEntriesRoundTripMatchesSkillMd() throws Exception {
        JsonNode root = new ObjectMapper().readTree(readResource(MAIN_INDEX));
        List<JsonNode> entries = openmontageEntries(root);
        assertTrue(entries.size() >= 150,
                "OpenMontage 条目数量不足: " + entries.size());
        List<String> mismatches = new ArrayList<>();
        for (JsonNode e : entries) {
            String id = e.get("id").asText();
            String md = readResource("/skills-bundled/" + id + "/SKILL.md");
            String license = e.has("license") ? e.get("license").asText() : "";
            String sourceUrl = e.has("sourceUrl") ? e.get("sourceUrl").asText() : "";
            SkillDescriptor d = SkillDescriptor.fromFrontmatter(
                    id, md, SkillDescriptor.Source.BUNDLED, license, "openmontage", sourceUrl);
            if (!d.getName().equals(e.get("name").asText())) {
                mismatches.add(id + ": name");
            }
            if (!d.getVersion().equals(e.get("version").asText())) {
                mismatches.add(id + ": version");
            }
            if (!d.getDescription().equals(e.get("description").asText())) {
                mismatches.add(id + ": description");
            }
            if (!license.equals(d.getLicense())) {
                mismatches.add(id + ": license");
            }
            if (!"openmontage-video-edit".equals(id) && !LICENSE.equals(license)) {
                mismatches.add(id + ": license");
            }
            if (!SOURCE_URL.equals(sourceUrl)) {
                mismatches.add(id + ": sourceUrl");
            }
            if (!e.has("rewritten") || !e.get("rewritten").asBoolean()) {
                mismatches.add(id + ": rewritten");
            }
        }
        assertTrue(mismatches.isEmpty(), "round-trip 不一致: " + mismatches);
    }

    @Test
    void sampleThreeSkillsParse() throws Exception {
        String[] sample = {
                "openmontage-ffmpeg",
                "openmontage-cinematic",
                "openmontage-animation-idea-director",
        };
        for (String id : sample) {
            String md = readResource("/skills-bundled/" + id + "/SKILL.md");
            SkillDescriptor d = SkillDescriptor.fromFrontmatter(
                    id, md, SkillDescriptor.Source.BUNDLED, LICENSE, "openmontage", SOURCE_URL);
            assertEquals(id, d.getName(), "name 不匹配: " + id);
            assertTrue(d.getDescription().length() >= 20, "description 过短: " + id);
        }
    }
}