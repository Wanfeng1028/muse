package com.dramafactory.service.prompt;

import com.dramafactory.service.prompt.PromptLibraryService.PromptDetail;
import com.dramafactory.service.prompt.PromptLibraryService.PromptSummary;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PromptLibraryMultilingualTest {

    @Test
    void testListYuAiMatchesTitle() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptSummary> results = service.list("雨爱");
        assertFalse(results.isEmpty());
        PromptSummary yuai = results.stream()
                .filter(r -> "yuai-deepseek-prompt".equals(r.id()))
                .findFirst()
                .orElseThrow();
        assertEquals("DeepSeek 做《雨爱》MV 的提示词（部分转录）", yuai.title());
    }

    @Test
    void testListFenJingMatchesTitleOrSummaryButNotYuAi() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptSummary> results = service.list("分镜");
        // "分镜"只出现在正文（如 yuai 的"分镜八"、存档说明的"分镜计划"），
        // 不在任何文件的 title/summary 中；而 list 只匹配 title/summary，
        // 因此结果为空——这是搜索范围的行为证明。
        assertTrue(results.isEmpty());
        assertFalse(results.stream().anyMatch(r -> "yuai-deepseek-prompt".equals(r.id())));
    }

    @Test
    void testListTiShiCiMatchesExpectedEntries() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptSummary> results = service.list("提示词");
        assertTrue(results.stream().anyMatch(r -> "yuai-deepseek-prompt".equals(r.id())));
        assertTrue(results.stream().anyMatch(r -> "README".equals(r.id())));
        assertTrue(results.stream().anyMatch(r -> "opus-video-prompts__README".equals(r.id())));
        for (PromptSummary r : results) {
            assertTrue(r.title().contains("提示词") || r.summary().contains("提示词"));
        }
    }

    @Test
    void testListStoryboardCaseInsensitive() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptSummary> lower = service.list("storyboard");
        List<PromptSummary> upper = service.list("STORYBOARD");
        assertTrue(lower.stream().anyMatch(r -> "pdoom-video__STORYBOARD".equals(r.id())));
        assertEquals(
                lower.stream().map(PromptSummary::id).collect(Collectors.toList()),
                upper.stream().map(PromptSummary::id).collect(Collectors.toList())
        );
    }

    @Test
    void testListPDoomMatchesStoryboard() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptSummary> results = service.list("P(doom)");
        assertTrue(results.stream().anyMatch(r -> "pdoom-video__STORYBOARD".equals(r.id())));
    }

    @Test
    void testListMVCaseInsensitive() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptSummary> upper = service.list("MV");
        List<PromptSummary> lower = service.list("mv");
        assertEquals(
                upper.stream().map(PromptSummary::id).collect(Collectors.toList()),
                lower.stream().map(PromptSummary::id).collect(Collectors.toList())
        );
        assertTrue(upper.stream().anyMatch(r -> "yuai-deepseek-prompt".equals(r.id())));
        assertTrue(upper.stream().anyMatch(r -> "xiaozheng-mv-tutorial".equals(r.id())));
    }

    @Test
    void testListYuAiChineseUnaffectedByCaseFolding() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptSummary> results = service.list("雨爱");
        assertFalse(results.isEmpty());
        for (PromptSummary r : results) {
            assertTrue(r.title().contains("雨爱"));
        }
    }

    @Test
    void testGetPDoomStoryboardEmptySummary() {
        PromptLibraryService service = new PromptLibraryService();
        Optional<PromptDetail> detail = service.get("pdoom-video__STORYBOARD");
        assertTrue(detail.isPresent());
        assertNotNull(detail.get().summary());
        assertEquals("", detail.get().summary());
    }

    @Test
    void testListFullWidthParenthesis() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptSummary> fullWidth = service.list("（");
        List<PromptSummary> halfWidth = service.list("(");
        assertFalse(fullWidth.isEmpty());
        for (PromptSummary r : fullWidth) {
            assertTrue(r.title().contains("（") || r.summary().contains("（"));
        }
        assertTrue(fullWidth.stream().anyMatch(r -> "yuai-deepseek-prompt".equals(r.id())));
        assertFalse(halfWidth.stream().anyMatch(r -> "yuai-deepseek-prompt".equals(r.id())));
        assertNotEquals(fullWidth.size(), halfWidth.size());
    }

    @Test
    void testListYuAiTrimWhitespace() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptSummary> withSpaces = service.list("  雨爱  ");
        List<PromptSummary> withoutSpaces = service.list("雨爱");
        assertEquals(
                withoutSpaces.stream().map(PromptSummary::id).collect(Collectors.toList()),
                withSpaces.stream().map(PromptSummary::id).collect(Collectors.toList())
        );
    }

    @Test
    void testListNullAndEmptyReturnAll() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptSummary> nullResult = service.list(null);
        List<PromptSummary> emptyResult = service.list("");
        assertEquals(nullResult.size(), emptyResult.size());
        assertTrue(nullResult.stream().anyMatch(r -> "yuai-deepseek-prompt".equals(r.id())));
        assertTrue(emptyResult.stream().anyMatch(r -> "yuai-deepseek-prompt".equals(r.id())));
    }

    @Test
    void testListJiaoChengMatchesXiaozheng() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptSummary> results = service.list("教程");
        assertTrue(results.stream().anyMatch(r -> "xiaozheng-mv-tutorial".equals(r.id())));
    }
}
