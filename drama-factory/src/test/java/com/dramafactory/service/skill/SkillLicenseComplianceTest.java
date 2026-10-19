package com.dramafactory.service.skill;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 合规处置回归测试（2026-10-20 复审）。
 *
 * 背景：toonflow-canvas / toonflow-workflow / toonflow-v118workflow 三个 skill
 * 与上游原文相似度 0.911-0.982，_index.json 曾误标 rewritten:true，已纠正为
 * rewritten:false 并补入上游 MIT LICENSE。本测试锁定该合规政策，防止未来新增
 * "近乎原文收录"的 skill 漏补 LICENSE。
 *
 * 政策（docs/SKILL_AUDIT_2026-10-19.md）：
 * - rewritten == true  -> 独立重写、无原文复制，豁免携带上游 LICENSE，但必须写 rewriteNote
 * - rewritten 缺失或 false -> 必须在 /skills-bundled/&lt;id&gt;/ 下有 LICENSE 资源
 *
 * 纯 JUnit，不启动 Spring；只通过 classpath 读取资源。
 */
class SkillLicenseComplianceTest {

    private static final String MAIN_INDEX = "/skills-bundled/_index.json";
    private static final String OPENMONTAGE_INDEX = "/skills-bundled/_index.openmontage.json";

    private static final List<String> TOONFLOW_IDS = Arrays.asList(
            "toonflow-canvas",
            "toonflow-workflow",
            "toonflow-v118workflow"
    );

    private static final String UPSTREAM_COPYRIGHT_HOLDER = "HBAI-Ltd";
    private static final String MIT_MARKER = "MIT License";

    private final ObjectMapper objectMapper = new ObjectMapper();

    // ------------------------------------------------------------------
    // 用例 1：非重写 skill 必须携带 LICENSE
    // ------------------------------------------------------------------

    @Test
    void nonRewrittenSkillsMustCarryLicense() throws IOException {
        JsonNode mainRoot = readIndex(MAIN_INDEX);
        assertNotNull(mainRoot, "主索引不可读: " + MAIN_INDEX);

        List<String> missing = new ArrayList<>();
        collectMissingLicenses(mainRoot, missing);

        // openmontage 索引为可选文件：缺失时跳过，不作为失败
        JsonNode openmontageRoot = readIndexOrNull(OPENMONTAGE_INDEX);
        if (openmontageRoot != null) {
            collectMissingLicenses(openmontageRoot, missing);
        }

        assertTrue(missing.isEmpty(),
                "以下非重写 skill 缺少 LICENSE 资源: " + missing);
    }

    private void collectMissingLicenses(JsonNode root, List<String> missing) {
        JsonNode skills = root.get("skills");
        if (skills == null || !skills.isArray()) {
            return;
        }
        for (JsonNode skill : skills) {
            JsonNode idNode = skill.get("id");
            if (idNode == null || idNode.isNull()) {
                continue;
            }
            String id = idNode.asText();
            if (id.isEmpty()) {
                continue;
            }
            if (isRewritten(skill)) {
                continue;
            }
            if (!hasLicenseResource(id)) {
                missing.add("skill 缺 LICENSE: " + id);
            }
        }
    }

    // ------------------------------------------------------------------
    // 用例 2：toonflow 三个 skill 必须带上游 MIT LICENSE，且索引标记为 rewritten=false
    // ------------------------------------------------------------------

    @Test
    void toonflowSkillsHaveUpstreamMitLicense() throws IOException {
        JsonNode root = readIndex(MAIN_INDEX);
        assertNotNull(root, "主索引不可读: " + MAIN_INDEX);

        for (String id : TOONFLOW_IDS) {
            String license = readResource("/skills-bundled/" + id + "/LICENSE");
            assertNotNull(license, "skill 缺 LICENSE: " + id);

            assertTrue(license.contains(MIT_MARKER),
                    "LICENSE 未包含 \"" + MIT_MARKER + "\": " + id);
            assertTrue(license.contains(UPSTREAM_COPYRIGHT_HOLDER),
                    "LICENSE 未包含上游版权方 \"" + UPSTREAM_COPYRIGHT_HOLDER + "\": " + id);

            JsonNode entry = findSkill(root, id);
            assertNotNull(entry, "_index.json 缺少条目: " + id);

            JsonNode rewritten = entry.get("rewritten");
            assertNotNull(rewritten, "_index.json 条目缺少 rewritten 字段: " + id);
            assertFalse(rewritten.asBoolean(true),
                    "_index.json 中 " + id + " 的 rewritten 应为 false（近乎原文收录，已补 LICENSE）");
        }
    }

    // ------------------------------------------------------------------
    // 用例 3：rewritten=true 豁免 LICENSE，但必须标注 rewriteNote
    // ------------------------------------------------------------------

    @Test
    void rewrittenSkillsAreExempt() throws IOException {
        JsonNode root = readIndex(MAIN_INDEX);
        assertNotNull(root, "主索引不可读: " + MAIN_INDEX);

        JsonNode skills = root.get("skills");
        assertNotNull(skills, "_index.json 缺少 skills 数组");
        assertTrue(skills.isArray(), "_index.json 的 skills 不是数组");

        List<String> missingNote = new ArrayList<>();
        for (JsonNode skill : skills) {
            if (!isRewritten(skill)) {
                continue;
            }
            JsonNode idNode = skill.get("id");
            String id = (idNode == null || idNode.isNull()) ? "<unknown>" : idNode.asText();

            // 豁免 LICENSE 断言：仅校验 rewriteNote
            JsonNode note = skill.get("rewriteNote");
            if (note == null || note.isNull() || note.asText().trim().isEmpty()) {
                missingNote.add(id);
            }
        }

        assertTrue(missingNote.isEmpty(),
                "以下 rewritten=true 的 skill 缺少非空 rewriteNote: " + missingNote);
    }

    // ------------------------------------------------------------------
    // 工具方法
    // ------------------------------------------------------------------

    private JsonNode readIndex(String classpathPath) throws IOException {
        JsonNode root = readIndexOrNull(classpathPath);
        assertNotNull(root, "无法读取 classpath 资源: " + classpathPath);
        return root;
    }

    private JsonNode readIndexOrNull(String classpathPath) throws IOException {
        InputStream in = getClass().getResourceAsStream(classpathPath);
        if (in == null) {
            return null;
        }
        try (InputStream stream = in) {
            return objectMapper.readTree(stream);
        }
    }

    private String readResource(String classpathPath) throws IOException {
        InputStream in = getClass().getResourceAsStream(classpathPath);
        if (in == null) {
            return null;
        }
        try (InputStream stream = in) {
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private boolean hasLicenseResource(String id) {
        InputStream in = getClass().getResourceAsStream("/skills-bundled/" + id + "/LICENSE");
        if (in == null) {
            return false;
        }
        try {
            in.close();
        } catch (IOException ignored) {
            // 资源存在即可，关闭失败不影响判定
        }
        return true;
    }

    private boolean isRewritten(JsonNode skill) {
        JsonNode rewritten = skill.get("rewritten");
        return rewritten != null && !rewritten.isNull() && rewritten.asBoolean(false);
    }

    private JsonNode findSkill(JsonNode root, String id) {
        JsonNode skills = root.get("skills");
        if (skills == null || !skills.isArray()) {
            return null;
        }
        for (JsonNode skill : skills) {
            JsonNode idNode = skill.get("id");
            if (idNode != null && !idNode.isNull() && id.equals(idNode.asText())) {
                return skill;
            }
        }
        return null;
    }
}
