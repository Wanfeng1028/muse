package com.dramafactory.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * {@link CinematographyVocabulary} 纯单测，验证合并后的词表查询与分镜 prompt 组装。
 *
 * <p>不依赖 Spring 容器，直接 new 出词表实例。数据文件从类路径加载。</p>
 */
class CinematographyVocabularyMergeTest {

    /** 被测词表实例。 */
    private final CinematographyVocabulary vocabulary =
            new CinematographyVocabulary("data/cinematography/vocabulary.json", new ObjectMapper());

    // ---------------- englishLighting ----------------

    @Test
    @DisplayName("englishLighting：霓虹 → neon glow")
    void englishLightingNeon() {
        assertEquals(Optional.of("neon glow"), vocabulary.englishLighting("霓虹"));
    }

    @Test
    @DisplayName("englishLighting：不存在 → empty")
    void englishLightingUnknown() {
        assertEquals(Optional.empty(), vocabulary.englishLighting("不存在"));
    }

    // ---------------- englishComposition ----------------

    @Test
    @DisplayName("englishComposition：深景深 → deep focus")
    void englishCompositionDeepFocus() {
        assertEquals(Optional.of("deep focus"), vocabulary.englishComposition("深景深"));
    }

    // ---------------- englishCameraMove / englishShotSize ----------------

    @Test
    @DisplayName("englishCameraMove：手持 → handheld")
    void englishCameraMoveHandheld() {
        assertEquals(Optional.of("handheld"), vocabulary.englishCameraMove("手持"));
    }

    @Test
    @DisplayName("englishShotSize：建立镜头 → establishing shot")
    void englishShotSizeEstablishing() {
        assertEquals(Optional.of("establishing shot"), vocabulary.englishShotSize("建立镜头"));
    }

    // ---------------- buildShotPrompt ----------------

    @Test
    @DisplayName("buildShotPrompt：五层顺序 camera→movement→subject→lighting→style")
    void buildShotPromptFullLayers() {
        String prompt = vocabulary.buildShotPrompt(
                "特写", "推镜头", "a girl runs", List.of("rain"), "霓虹", "cyberpunk");
        assertEquals("close-up. push-in. a girl runs, rain. neon glow. Style: cyberpunk", prompt);
    }

    @Test
    @DisplayName("buildShotPrompt：全部为 null → 空串")
    void buildShotPromptAllNull() {
        String prompt = vocabulary.buildShotPrompt(null, null, null, null, null, null);
        assertEquals("", prompt);
    }

    @Test
    @DisplayName("buildShotPrompt：未知景别标签跳过该层，固定机位正常拼装")
    void buildShotPromptUnknownLayerSkipped() {
        String prompt = vocabulary.buildShotPrompt("不存在", "固定机位", "x", null, null, null);
        assertEquals("static shot. x", prompt);
    }

    // ---------------- renderAppendix ----------------

    @Test
    @DisplayName("renderAppendix：包含 handheld 与 neon glow，且仍包含 close-up")
    void renderAppendixContainsMergedAndExistingEntries() {
        String appendix = vocabulary.renderAppendix();
        assertTrue(appendix.contains("handheld"));
        assertTrue(appendix.contains("neon glow"));
        assertTrue(appendix.contains("close-up"));
        assertFalse(appendix.isEmpty());
    }
}
