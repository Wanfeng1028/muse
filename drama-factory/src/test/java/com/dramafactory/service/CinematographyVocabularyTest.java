package com.dramafactory.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * {@link CinematographyVocabulary} 的纯单测，不涉及 Spring 上下文与网络。
 */
class CinematographyVocabularyTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * 默认 classpath 词表应能加载，并渲染出包含关键英文术语的附录。
     */
    @Test
    void loadsDefaultClasspathVocabularyAndRendersAppendix() {
        CinematographyVocabulary vocab = new CinematographyVocabulary(
                "data/cinematography/vocabulary.json", objectMapper);
        String appendix = vocab.renderAppendix();
        assertTrue(appendix.contains("close-up"), "附录应包含 close-up");
        assertTrue(appendix.contains("push-in"), "附录应包含 push-in");
    }

    /**
     * 中文标签精确匹配应返回对应英文术语；未知标签返回 empty。
     */
    @Test
    void englishLookupsMatchExactly() {
        CinematographyVocabulary vocab = new CinematographyVocabulary(
                "data/cinematography/vocabulary.json", objectMapper);
        assertEquals("close-up", vocab.englishShotSize("特写").orElse(null));
        assertFalse(vocab.englishCameraMove("不存在").isPresent());
    }

    /**
     * vocabPath 指向不存在的文件时应回退到 classpath 默认词表。
     */
    @Test
    void fallsBackToClasspathWhenFileMissing() {
        CinematographyVocabulary vocab = new CinematographyVocabulary(
                "data/cinematography/does-not-exist.json", objectMapper);
        assertEquals("close-up", vocab.englishShotSize("特写").orElse(null));
        assertTrue(vocab.renderAppendix().contains("push-in"));
    }

    /**
     * @TempDir 中写入最小合法 JSON 应覆盖 classpath 默认词表。
     */
    @Test
    void tempDirCustomVocabularyOverridesDefault(@TempDir Path tempDir) throws Exception {
        Path file = tempDir.resolve("vocabulary.json");
        String json = "{"
                + "\"version\":\"test-1\","
                + "\"shotSize\":[{\"label\":\"特写\",\"en\":\"custom-close-up\"}],"
                + "\"cameraMove\":[]"
                + "}";
        Files.writeString(file, json, StandardCharsets.UTF_8);

        CinematographyVocabulary vocab = new CinematographyVocabulary(
                file.toString(), objectMapper);
        assertEquals("custom-close-up", vocab.englishShotSize("特写").orElse(null));
        assertEquals("test-1", vocab.getVersion());
    }
}
