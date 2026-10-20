package com.dramafactory.service.prompt;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class PromptLibraryServiceTest {

    private final PromptLibraryService service = new PromptLibraryService();

    @Test
    void loadsAllMarkdownEntries() {
        List<PromptLibraryService.PromptSummary> all = service.list(null);
        assertEquals(35, all.size());

        List<String> ids = all.stream().map(PromptLibraryService.PromptSummary::id).toList();
        assertTrue(ids.contains("yuai-deepseek-prompt"));
        assertTrue(ids.contains("xiaozheng-mv-tutorial"));
        assertTrue(ids.contains("opus-video-prompts__prompts__01-inference-startup-launch"));
        assertTrue(ids.contains("pdoom-video__STORYBOARD"));
    }

    @Test
    void detailCarriesTitleSourceAndContent() {
        Optional<PromptLibraryService.PromptDetail> yuai = service.get("yuai-deepseek-prompt");
        assertTrue(yuai.isPresent());
        assertEquals("DeepSeek 做《雨爱》MV 的提示词（部分转录）", yuai.get().title());
        assertEquals("根目录", yuai.get().source());
        assertTrue(yuai.get().content().startsWith("# DeepSeek"));

        Optional<PromptLibraryService.PromptDetail> opus =
                service.get("opus-video-prompts__prompts__01-inference-startup-launch");
        assertTrue(opus.isPresent());
        assertEquals("推理创业公司发布视频", opus.get().title());
        assertEquals("opus-video-prompts", opus.get().source());

        Optional<PromptLibraryService.PromptDetail> pdoom = service.get("pdoom-video__STORYBOARD");
        assertTrue(pdoom.isPresent());
        assertEquals("I'm Upping My P(doom): storyboard", pdoom.get().title());
        assertEquals("pdoom-video", pdoom.get().source());
    }

    @Test
    void searchFiltersByTitleOrSummary() {
        List<PromptLibraryService.PromptSummary> hits = service.list("雨爱");
        assertFalse(hits.isEmpty());
        for (PromptLibraryService.PromptSummary summary : hits) {
            assertTrue(summary.title().contains("雨爱") || summary.summary().contains("雨爱"));
        }
        assertTrue(hits.stream().map(PromptLibraryService.PromptSummary::id).toList()
                .contains("yuai-deepseek-prompt"));

        assertTrue(service.list("zzzz-no-such-word").isEmpty());
        assertEquals(service.list(null).size(), service.list("").size());
    }

    @Test
    void unknownIdReturnsEmpty() {
        assertTrue(service.get("no-such-id").isEmpty());
        assertTrue(service.get(null).isEmpty());
    }
}
