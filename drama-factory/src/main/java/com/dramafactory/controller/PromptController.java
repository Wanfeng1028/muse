package com.dramafactory.controller;

import com.dramafactory.service.prompt.PromptLibraryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/prompts")
@Tag(name = "提示词库", description = "收集的实测提示词与教程拆解：浏览、搜索、查看全文")
public class PromptController {

    private static final Logger log = LoggerFactory.getLogger(PromptController.class);

    private final PromptLibraryService promptLibraryService;

    public PromptController(PromptLibraryService promptLibraryService) {
        this.promptLibraryService = promptLibraryService;
    }

    public record PromptSummaryDto(String id, String title, String source, String path, String summary) {}

    public record PromptDetailDto(String id, String title, String source, String path, String summary, String content) {}

    @GetMapping("")
    @Operation(summary = "提示词列表与搜索")
    public ResponseEntity<List<PromptSummaryDto>> list(@RequestParam(required = false) String q) {
        List<PromptSummaryDto> result = promptLibraryService.list(q).stream()
                .map(s -> new PromptSummaryDto(s.id(), s.title(), s.source(), s.path(), s.summary()))
                .toList();
        return ResponseEntity.ok(result);
    }

    @GetMapping("/{id}")
    @Operation(summary = "查看提示词全文")
    public ResponseEntity<PromptDetailDto> detail(@PathVariable String id) {
        return promptLibraryService.get(id)
                .map(d -> ResponseEntity.ok(new PromptDetailDto(d.id(), d.title(), d.source(),
                        d.path(), d.summary(), d.content())))
                .orElseGet(() -> {
                    log.warn("提示词不存在：{}", id);
                    return ResponseEntity.notFound().build();
                });
    }
}
