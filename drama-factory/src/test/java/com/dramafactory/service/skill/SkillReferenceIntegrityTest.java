package com.dramafactory.service.skill;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * SKILL.md 引用完整性回归测试（2026-10-22）。
 *
 * 背景：2026-10-20 复审补强建议第 2 项要求锁定 SKILL.md 中引用的相对路径 .md
 * 必须在包内真实存在。2026-10-22 已把上游 31 个 references 文件原样补入
 * toonflow-canvas / toonflow-workflow / toonflow-v118workflow 三个 skill 目录。
 * 当前全 bundle 另有 268 处其他 skill 的悬空引用属历史遗留，本测试暂只锁定
 * toonflow 三个 skill，后续再扩面。
 *
 * 纯 JUnit，不启动 Spring；只通过 classpath 定位 skills-bundled 根目录。
 */
class SkillReferenceIntegrityTest {

    private static final String BUNDLE_ROOT = "/skills-bundled";

    private static final List<String> TOONFLOW_IDS = Arrays.asList(
            "toonflow-canvas",
            "toonflow-workflow",
            "toonflow-v118workflow"
    );

    /**
     * 已知悬空引用例外。
     *
     * toonflow-canvas 的 ../script/references/assetGuide.md 与
     * ../script/references/productionGuide.md 在上游 HBAI-Ltd/Toonflow-app 原文里
     * 就悬空：上游没有 script 这个 skill。属于上游继承问题，暂不作为失败；
     * 若上游未来补齐，请从该例外清单中移除。
     */
    private static final Set<String> KNOWN_DANGLING_REFERENCES = new HashSet<>(Arrays.asList(
            "toonflow-canvas:../script/references/assetGuide.md",
            "toonflow-canvas:../script/references/productionGuide.md"
    ));

    private static final Pattern MARKDOWN_LINK = Pattern.compile("\\[([^\\]]*)\\]\\(([^)]+)\\)");

    // ------------------------------------------------------------------
    // 用例：SKILL.md 中引用的相对路径 .md 必须解析到 bundle 内真实文件
    // ------------------------------------------------------------------

    @Test
    void toonflowSkillMarkdownReferencesMustResolveInsideBundle() throws Exception {
        URL bundleUrl = getClass().getResource(BUNDLE_ROOT);
        assertNotNull(bundleUrl, "classpath 资源不存在: " + BUNDLE_ROOT);

        Path bundleRoot = Paths.get(bundleUrl.toURI()).normalize();
        assertTrue(Files.isDirectory(bundleRoot), "skills-bundled 目录不可读: " + bundleRoot);

        List<String> missing = new ArrayList<>();

        for (String id : TOONFLOW_IDS) {
            Path skillDir = bundleRoot.resolve(id).normalize();
            assertTrue(Files.isDirectory(skillDir), "skill 目录不存在: " + id);

            String skillMd = readSkillMd(skillDir);
            Matcher matcher = MARKDOWN_LINK.matcher(skillMd);

            while (matcher.find()) {
                String target = matcher.group(2).trim();

                if (shouldSkip(target)) {
                    continue;
                }

                if (isKnownDangling(id, target)) {
                    continue;
                }

                int anchorIdx = target.indexOf('#');
                String pathPart = anchorIdx >= 0 ? target.substring(0, anchorIdx) : target;
                Path resolved = skillDir.resolve(pathPart).normalize();

                if (!resolved.startsWith(bundleRoot)) {
                    missing.add("引用越界: " + id + " -> " + target + " (解析为 " + resolved + ")");
                    continue;
                }

                if (!Files.isRegularFile(resolved)) {
                    missing.add("引用缺失: " + id + " -> " + target + " (期望文件 " + resolved + ")");
                }
            }
        }

        assertTrue(missing.isEmpty(),
                "SKILL.md 中存在未满足的 .md 引用: " + missing);
    }

    // ------------------------------------------------------------------
    // 工具方法
    // ------------------------------------------------------------------

    private String readSkillMd(Path skillDir) throws IOException {
        Path skillMd = skillDir.resolve("SKILL.md");
        assertTrue(Files.isRegularFile(skillMd), "SKILL.md 不存在: " + skillMd);
        return new String(Files.readAllBytes(skillMd), StandardCharsets.UTF_8);
    }

    private boolean shouldSkip(String target) {
        if (target.isEmpty() || target.startsWith("#")) {
            return true;
        }

        if (target.startsWith("http://") || target.startsWith("https://") || target.startsWith("mailto:")) {
            return true;
        }

        int anchorIndex = target.indexOf('#');
        String path = anchorIndex >= 0 ? target.substring(0, anchorIndex) : target;

        return path.isEmpty() || !path.endsWith(".md");
    }

    private boolean isKnownDangling(String id, String target) {
        return KNOWN_DANGLING_REFERENCES.contains(id + ":" + target);
    }
}