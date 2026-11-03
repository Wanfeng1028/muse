package com.dramafactory.service.prompt;

import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

class PromptLibraryServiceSearchEdgeTest {

    @Test
    void mixedCaseKeywordEqualsLowerCase() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> upper = service.list("AI MV");
        List<PromptLibraryService.PromptSummary> lower = service.list("ai mv");
        List<String> upperIds = upper.stream().map(PromptLibraryService.PromptSummary::id).collect(Collectors.toList());
        List<String> lowerIds = lower.stream().map(PromptLibraryService.PromptSummary::id).collect(Collectors.toList());
        Assertions.assertEquals(lowerIds, upperIds);
        Assertions.assertFalse(upper.isEmpty());
        Assertions.assertTrue(upperIds.contains("xiaozheng-mv-tutorial"));
    }

    @Test
    void upperCaseEnglishKeyword() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> results = service.list("PDOOM");
        Assertions.assertFalse(results.isEmpty());
        for (PromptLibraryService.PromptSummary summary : results) {
            String title = summary.title() == null ? "" : summary.title().toLowerCase(Locale.ROOT);
            String summaryText = summary.summary() == null ? "" : summary.summary().toLowerCase(Locale.ROOT);
            Assertions.assertTrue(title.contains("pdoom") || summaryText.contains("pdoom"));
        }
    }

    @Test
    void chineseKeyword() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> results = service.list("雨爱");
        Assertions.assertFalse(results.isEmpty());
        List<String> ids = results.stream().map(PromptLibraryService.PromptSummary::id).collect(Collectors.toList());
        Assertions.assertTrue(ids.contains("yuai-deepseek-prompt"));
        for (PromptLibraryService.PromptSummary summary : results) {
            String title = summary.title() == null ? "" : summary.title();
            String summaryText = summary.summary() == null ? "" : summary.summary();
            Assertions.assertTrue(title.contains("雨爱") || summaryText.contains("雨爱"));
        }
    }

    @Test
    void keywordWithSurroundingSpaces() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> withSpaces = service.list("  雨爱  ");
        List<PromptLibraryService.PromptSummary> withoutSpaces = service.list("雨爱");
        List<String> withSpacesIds = withSpaces.stream().map(PromptLibraryService.PromptSummary::id).collect(Collectors.toList());
        List<String> withoutSpacesIds = withoutSpaces.stream().map(PromptLibraryService.PromptSummary::id).collect(Collectors.toList());
        Assertions.assertEquals(withoutSpacesIds, withSpacesIds);
    }

    @Test
    void whitespaceOnlyReturnsAll() {
        PromptLibraryService service = new PromptLibraryService();
        long total = service.list(null).size();
        List<PromptLibraryService.PromptSummary> whitespace = service.list("   ");
        List<PromptLibraryService.PromptSummary> nullQuery = service.list(null);
        Assertions.assertEquals(total, whitespace.size());
        List<String> whitespaceIds = whitespace.stream().map(PromptLibraryService.PromptSummary::id).collect(Collectors.toList());
        List<String> nullIds = nullQuery.stream().map(PromptLibraryService.PromptSummary::id).collect(Collectors.toList());
        Assertions.assertEquals(nullIds, whitespaceIds);
    }

    @Test
    void veryLongKeyword() {
        PromptLibraryService service = new PromptLibraryService();
        Assertions.assertTrue(service.list("x".repeat(200)).isEmpty());
        Assertions.assertTrue(service.list("雨".repeat(200)).isEmpty());
    }

    @Test
    void specialCharsAreLiteral_underscore() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> results = service.list("__");
        for (PromptLibraryService.PromptSummary summary : results) {
            String title = summary.title() == null ? "" : summary.title();
            String summaryText = summary.summary() == null ? "" : summary.summary();
            Assertions.assertTrue(title.contains("__") || summaryText.contains("__"));
        }
    }

    @Test
    void specialCharsAreLiteral_slash() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> results = service.list("/");
        for (PromptLibraryService.PromptSummary summary : results) {
            String title = summary.title() == null ? "" : summary.title();
            String summaryText = summary.summary() == null ? "" : summary.summary();
            Assertions.assertTrue(title.contains("/") || summaryText.contains("/"));
        }
    }

    @Test
    void bracketsAreLiteral() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> results = service.list("《雨爱》");
        List<String> ids = results.stream().map(PromptLibraryService.PromptSummary::id).collect(Collectors.toList());
        Assertions.assertTrue(ids.contains("yuai-deepseek-prompt"));
    }

    @Test
    void nullEqualsEmpty() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> nullQuery = service.list(null);
        List<PromptLibraryService.PromptSummary> emptyQuery = service.list("");
        Assertions.assertEquals(nullQuery.size(), emptyQuery.size());
        List<String> nullIds = nullQuery.stream().map(PromptLibraryService.PromptSummary::id).collect(Collectors.toList());
        List<String> emptyIds = emptyQuery.stream().map(PromptLibraryService.PromptSummary::id).collect(Collectors.toList());
        Assertions.assertEquals(nullIds, emptyIds);
    }

    @Test
    void noResultReturnsEmpty() {
        PromptLibraryService service = new PromptLibraryService();
        Assertions.assertTrue(service.list("zzzz-no-such-word-xyz").isEmpty());
        Assertions.assertTrue(service.list("不存在的词缀qqq").isEmpty());
    }
}
