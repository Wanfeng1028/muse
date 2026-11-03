package com.dramafactory.service.prompt;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;

class PromptLibraryServiceIntegrityTest {
    private final PromptLibraryService service = new PromptLibraryService();

    @Test
    void integrity_noBlankFields() {
        List<PromptLibraryService.PromptSummary> all = service.list(null);
        for (PromptLibraryService.PromptSummary summary : all) {
            assertFalse(summary.id().isBlank(), "id 不能为空");
            assertFalse(summary.title().isBlank(), "title 不能为空");
            assertFalse(summary.source().isBlank(), "source 不能为空");
            java.util.Optional<PromptLibraryService.PromptDetail> detailOpt = service.get(summary.id());
            assertTrue(detailOpt.isPresent(), "必须能通过 id 取到详情: " + summary.id());
            assertFalse(detailOpt.get().content().isBlank(), "content 不能为空: " + summary.id());
        }
    }

    @Test
    void integrity_idsUnique() {
        List<PromptLibraryService.PromptSummary> all = service.list(null);
        long distinctCount = all.stream()
                .map(PromptLibraryService.PromptSummary::id)
                .distinct()
                .count();
        assertEquals(all.size(), distinctCount, "id 必须全唯一");
    }

    @Test
    void integrity_noSilentDrop() throws Exception {
        Resource[] resources = new PathMatchingResourcePatternResolver()
                .getResources("classpath*:/prompt-library/**/*.md");
        List<PromptLibraryService.PromptSummary> all = service.list(null);
        assertEquals(resources.length, all.size(),
                "资源总数与加载条目数不一致，存在静默丢条目");
    }

    @Test
    void integrity_searchConsistency() {
        List<PromptLibraryService.PromptSummary> all = service.list(null);
        List<PromptLibraryService.PromptSummary> emptySearch = service.list("");
        assertEquals(all.size(), emptySearch.size(), "空查询应返回全部条目");

        List<PromptLibraryService.PromptSummary> rainLove = service.list("雨爱");
        for (PromptLibraryService.PromptSummary summary : rainLove) {
            boolean matches = summary.title().contains("雨爱")
                    || summary.summary().contains("雨爱");
            assertTrue(matches, "搜索结果应包含关键词: " + summary.id());
        }
    }
}
