package com.dramafactory.service.prompt;

import org.junit.jupiter.api.Test;

import com.dramafactory.service.prompt.PromptLibraryService.PromptDetail;
import com.dramafactory.service.prompt.PromptLibraryService.PromptSummary;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class PromptLibraryRobustnessTest {

    private static final PromptLibraryService SERVICE = new PromptLibraryService();

    @Test
    void constructorLoadsAllEntries() {
        // 26 原始 + 9 新增（2026-10-20 W-RES lane：5 个内容原件 + 4 个 _SOURCE.md）
        assertEquals(35, SERVICE.list(null).size());
        assertEquals(35, SERVICE.list("").size());
        Set<String> ids = SERVICE.list(null).stream()
                .map(PromptSummary::id)
                .collect(Collectors.toSet());
        assertEquals(35, ids.size()); // 26 原始 + 9 新增（2026-10-20 W-RES）
    }

    @Test
    void everyEntryRecallableByOwnTitlePrefix() {
        List<PromptSummary> all = SERVICE.list(null);
        int recalled = 0;
        for (PromptSummary summary : all) {
            String kw = summary.title().substring(0, Math.min(4, summary.title().length()));
            List<PromptSummary> hits = SERVICE.list(kw);
            Set<String> hitIds = hits.stream()
                    .map(PromptSummary::id)
                    .collect(Collectors.toSet());
            assertTrue(hitIds.contains(summary.id()),
                    "关键词 [" + kw + "] 未召回 " + summary.id());
            recalled++;
        }
        assertEquals(35, recalled, "应召回全部 35 条"); // 26 原始 + 9 新增（2026-10-20 W-RES）
    }

    @Test
    void getReturnsEveryEntryById() {
        for (PromptSummary summary : SERVICE.list(null)) {
            String id = summary.id();
            Optional<PromptDetail> d = SERVICE.get(id);
            assertTrue(d.isPresent(), "id 未找到: " + id);
            assertEquals(id, d.get().id());
            assertNotNull(d.get().title(), "title 为空: " + id);
            assertFalse(d.get().title().isEmpty(), "title 为空: " + id);
            assertNotNull(d.get().source(), "source 为空: " + id);
            assertFalse(d.get().source().isEmpty(), "source 为空: " + id);
            assertNotNull(d.get().path(), "path 为空: " + id);
            assertFalse(d.get().path().isEmpty(), "path 为空: " + id);
            assertNotNull(d.get().content(), "content 为空: " + id);
            assertFalse(d.get().content().isEmpty(), "content 为空: " + id);
        }
    }

    @Test
    void getBoundaryCases() {
        assertTrue(SERVICE.get(null).isEmpty());
        assertTrue(SERVICE.get("this-id-does-not-exist-zzz").isEmpty());
    }

    @Test
    void largeFileContentMatchesResource() throws Exception {
        Optional<PromptDetail> d = SERVICE.get("opus-video-prompts__README");
        assertTrue(d.isPresent(), "opus-video-prompts__README 未找到");
        assertTrue(d.get().content().length() > 0, "content 为空: opus-video-prompts__README");
        try (InputStream in = getClass().getResourceAsStream("/prompt-library/opus-video-prompts/README.md")) {
            assertNotNull(in, "资源流为 null: /prompt-library/opus-video-prompts/README.md");
            String raw = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            assertEquals(raw, d.get().content(), "content 与资源文件不一致: opus-video-prompts__README");
        }
    }

    @Test
    void summaryLengthWithinLimit() {
        for (PromptSummary summary : SERVICE.list(null)) {
            String id = summary.id();
            Optional<PromptDetail> d = SERVICE.get(id);
            assertTrue(d.isPresent(), "id 未找到: " + id);
            assertTrue(d.get().summary().length() <= 200,
                    "summary 超过 200 字符: " + id);
        }
    }

    @Test
    void sourceDerivedFromPath() {
        for (PromptSummary summary : SERVICE.list(null)) {
            String id = summary.id();
            Optional<PromptDetail> d = SERVICE.get(id);
            assertTrue(d.isPresent(), "id 未找到: " + id);
            String path = d.get().path();
            String source = d.get().source();
            if (!path.contains("/")) {
                assertEquals("根目录", source, "path 不含 '/' 时 source 应为根目录: " + path);
            } else {
                String expected = path.substring(0, path.indexOf('/'));
                assertEquals(expected, source, "source 与 path 首段不一致: " + path);
            }
        }
    }
}