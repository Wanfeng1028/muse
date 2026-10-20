package com.dramafactory.service.skill;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.Optional;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SkillRegistryTest {

    @Test
    void bundledLoadsFromClasspath() {
        SkillRegistry registry = new SkillRegistry("nonexistent-dir-xyz");
        List<SkillDescriptor> b = registry.bundled();

        assertTrue(containsId(b, "video-shots"));
        assertTrue(containsId(b, "video-sync"));
        assertTrue(containsId(b, "video-scrub"));
        assertTrue(containsId(b, "captions"));
        assertTrue(containsId(b, "video-editor-ffmpeg"));
        assertTrue(containsId(b, "video-editor-remotion"));
        assertTrue(containsId(b, "editor"));

        SkillDescriptor shots = registry.bundledOf("video-shots").orElseThrow();
        assertEquals("Apache-2.0", shots.getLicense());
        assertEquals(SkillDescriptor.Source.BUNDLED, shots.getSource());

        SkillDescriptor ffmpeg = registry.bundledOf("video-editor-ffmpeg").orElseThrow();
        assertEquals("MIT", ffmpeg.getLicense());
        assertEquals("video-editor", ffmpeg.getOriginId());
    }

    @Test
    void bundledOfUnknownReturnsEmpty() {
        SkillRegistry registry = new SkillRegistry("nonexistent-dir-xyz");

        assertTrue(registry.bundledOf("no-such-skill").isEmpty());
        assertTrue(registry.bundledOf(null).isEmpty());
    }

    @Test
    void installedScansTempDir(@TempDir Path tmp) throws Exception {
        Path dir = tmp.resolve("demo-skill");
        Files.createDirectories(dir);
        Files.writeString(dir.resolve("SKILL.md"),
                "---\nname: demo-skill\nversion: 2.1.0\ndescription: demo\n---\n正文\n",
                StandardCharsets.UTF_8);

        SkillRegistry registry = new SkillRegistry(tmp.toString());
        List<SkillRegistry.InstalledSkill> list = registry.installed();

        assertEquals(1, list.size());
        assertEquals("demo-skill", list.get(0).id());
        assertEquals("2.1.0", list.get(0).version());

        Optional<SkillRegistry.InstalledSkill> found = registry.installedOf("demo-skill");
        assertTrue(found.isPresent());
        assertEquals("2.1.0", found.get().version());
    }

    @Test
    void installedSkipsBadDirAndCleanup(@TempDir Path tmp) throws Exception {
        Path badDir = tmp.resolve("bad dir");
        Files.createDirectories(badDir);
        Files.writeString(badDir.resolve("SKILL.md"),
                "---\nname: bad dir\nversion: 1.0.0\ndescription: bad\n---\n正文\n",
                StandardCharsets.UTF_8);

        Path goodDir = tmp.resolve("good-skill");
        Files.createDirectories(goodDir);
        Files.writeString(goodDir.resolve("SKILL.md"),
                "---\nname: good-skill\nversion: 1.0.0\ndescription: good\n---\n正文\n",
                StandardCharsets.UTF_8);

        SkillRegistry registry = new SkillRegistry(tmp.toString());
        List<SkillRegistry.InstalledSkill> list = registry.installed();

        assertEquals(1, list.size());
        assertEquals("good-skill", list.get(0).id());
        assertFalse(registry.installedOf("bad dir").isPresent());

        deleteRecursively(goodDir);

        List<SkillRegistry.InstalledSkill> after = registry.installed();
        assertTrue(after.isEmpty());
    }

    @Test
    void rewrittenEntriesLoadAsBundledWithSourceUrl() {
        SkillRegistry registry = new SkillRegistry("nonexistent-dir-xyz");

        SkillDescriptor openmontage = registry.bundledOf("openmontage-video-edit").orElseThrow();
        assertEquals(SkillDescriptor.Source.BUNDLED, openmontage.getSource());
        assertEquals("MIT", openmontage.getLicense());
        assertEquals("https://github.com/calesthio/OpenMontage", openmontage.getSourceUrl());

        SkillDescriptor watzing = registry.bundledOf("watzing-video-editor").orElseThrow();
        assertEquals("https://github.com/watzing/claude-video-editor", watzing.getSourceUrl());

        assertEquals("https://github.com/jordantobyll/video-editing-skills",
                registry.bundledOf("jordantobyll-video-edit").orElseThrow().getSourceUrl());
        assertEquals("https://github.com/jordantobyll/video-editing-skills",
                registry.bundledOf("jordantobyll-pan-3d-transition").orElseThrow().getSourceUrl());

        // 非改写条目 sourceUrl 为空
        assertEquals("", registry.bundledOf("video-shots").orElseThrow().getSourceUrl());
        assertEquals("", registry.bundledOf("shorz-mcp").orElseThrow().getSourceUrl());
    }

    @Test
    void bundledCountMatchesIndexEntries() throws Exception {
        Set<String> ids = new HashSet<>();
        ids.addAll(indexIds("/skills-bundled/_index.json"));
        ids.addAll(indexIds("/skills-bundled/_index.openmontage.json"));

        SkillRegistry registry = new SkillRegistry("nonexistent-dir-xyz");
        assertEquals(ids.size(), registry.bundled().size());
    }

    private static Set<String> indexIds(String resource) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        Set<String> ids = new HashSet<>();
        try (InputStream in = SkillRegistryTest.class.getResourceAsStream(resource)) {
            org.junit.jupiter.api.Assertions.assertNotNull(in, "索引资源缺失: " + resource);
            JsonNode skills = mapper.readTree(in).get("skills");
            for (JsonNode entry : skills) {
                ids.add(entry.get("id").asText());
            }
        }
        return ids;
    }

    private static boolean containsId(List<SkillDescriptor> list, String id) {
        for (SkillDescriptor descriptor : list) {
            if (id.equals(descriptor.getId())) {
                return true;
            }
        }
        return false;
    }

    private static void deleteRecursively(Path p) throws IOException {
        if (!Files.exists(p)) {
            return;
        }
        try (Stream<Path> stream = Files.walk(p)) {
            List<Path> paths = stream.sorted((a, b) -> b.getNameCount() - a.getNameCount()).toList();
            for (Path path : paths) {
                Files.delete(path);
            }
        }
    }
}
