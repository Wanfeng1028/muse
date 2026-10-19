package com.dramafactory.service.skill;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SkillDescriptorTest {

    private static final String SAMPLE_A = """
            ---
            name: video-scrub
            version: 1.0.0
            description: |
              把一条视频重建成「只有画面和声音」的干净文件。
              零依赖、零 API key，只要 node 和 ffmpeg。
            metadata:
              license: Apache-2.0
            ---
            正文忽略
            """;

    private static final String SAMPLE_B = """
            ---
            name: captions
            description: Add subtitles to a video.
            ---
            """;

    @Test
    void fromFrontmatterSampleA() {
        SkillDescriptor d = SkillDescriptor.fromFrontmatter(
                "video-scrub", SAMPLE_A, SkillDescriptor.Source.BUNDLED, "MIT", null);
        assertEquals("video-scrub", d.getName());
        assertEquals("1.0.0", d.getVersion());
        assertEquals("把一条视频重建成「只有画面和声音」的干净文件。\n零依赖、零 API key，只要 node 和 ffmpeg。\n", d.getDescription());
        assertEquals("Apache-2.0", d.getLicense());
    }

    @Test
    void fromFrontmatterSampleB() {
        SkillDescriptor d = SkillDescriptor.fromFrontmatter(
                "captions", SAMPLE_B, SkillDescriptor.Source.BUNDLED, "MIT", "cap");
        assertEquals("captions", d.getName());
        assertEquals("", d.getVersion());
        assertEquals("MIT", d.getLicense());
        assertEquals("cap", d.getOriginId());
    }

    @Test
    void fromFrontmatterMissingFrontmatter() {
        assertThrows(IllegalArgumentException.class, () ->
                SkillDescriptor.fromFrontmatter("x", "name: x\n", SkillDescriptor.Source.BUNDLED, "MIT", null));
    }

    @Test
    void fromFrontmatterMissingName() {
        String content = """
                ---
                version: 1.0.0
                ---
                """;
        assertThrows(IllegalArgumentException.class, () ->
                SkillDescriptor.fromFrontmatter("x", content, SkillDescriptor.Source.BUNDLED, "MIT", null));
    }

    @Test
    void fromFrontmatterSourceUrlOverload() {
        SkillDescriptor d = SkillDescriptor.fromFrontmatter(
                "captions", SAMPLE_B, SkillDescriptor.Source.BUNDLED, "MIT", "cap",
                "https://github.com/watzing/claude-video-editor");
        assertEquals("captions", d.getId());
        assertEquals("https://github.com/watzing/claude-video-editor", d.getSourceUrl());
        assertEquals(SkillDescriptor.Source.BUNDLED, d.getSource());
    }

    @Test
    void fromFrontmatterDefaultsSourceUrlEmpty() {
        SkillDescriptor d = SkillDescriptor.fromFrontmatter(
                "captions", SAMPLE_B, SkillDescriptor.Source.BUNDLED, "MIT", "cap");
        assertEquals("", d.getSourceUrl());
    }

    @Test
    void compareVersions() {
        assertEquals(0, SkillDescriptor.compareVersions("1.0.0", "1.0.0"));
        assertTrue(SkillDescriptor.compareVersions("1.2.0", "1.10.0") < 0);
        assertTrue(SkillDescriptor.compareVersions("2.0", "1.9.9") > 0);
        assertEquals(0, SkillDescriptor.compareVersions("1.0", "1.0.0"));
        assertTrue(SkillDescriptor.compareVersions("", "1.0.0") < 0);
        assertTrue(SkillDescriptor.compareVersions(null, "0.0.1") < 0);
    }
}
