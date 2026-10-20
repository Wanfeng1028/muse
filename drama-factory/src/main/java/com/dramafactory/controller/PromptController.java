package com.dramafactory.controller;

import com.dramafactory.service.prompt.PromptLibraryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
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

    public record PageDto<T>(List<T> content, int page, int size, long totalElements, int totalPages) {}

    private PromptSummaryDto toDto(PromptLibraryService.PromptSummary s) {
        return new PromptSummaryDto(s.id(), s.title(), s.source(), s.path(), s.summary());
    }

    @GetMapping("")
    @Operation(summary = "提示词列表与搜索")
    public ResponseEntity<List<PromptSummaryDto>> list(@RequestParam(required = false) String q) {
        List<PromptSummaryDto> result = promptLibraryService.list(q).stream()
                .map(this::toDto)
                .toList();
        return ResponseEntity.ok(result);
    }

    @GetMapping("/page")
    @Operation(summary = "提示词分页列表")
    public ResponseEntity<PageDto<PromptSummaryDto>> page(
            @RequestParam(required = false) String q,
            @RequestParam(required = false) String tag,
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer size) {
        int pageNum = page == null ? 0 : page;
        int sizeNum = size == null ? 20 : size;
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> result = promptLibraryService.list(q, tag, pageNum, sizeNum);
        List<PromptSummaryDto> content = result.content().stream()
                .map(this::toDto)
                .toList();
        PageDto<PromptSummaryDto> pageDto = new PageDto<>(content, result.page(), result.size(), result.totalElements(), result.totalPages());
        return ResponseEntity.ok(pageDto);
    }

    @GetMapping("/tags")
    @Operation(summary = "提示词标签列表")
    public ResponseEntity<List<String>> tags() {
        return ResponseEntity.ok(promptLibraryService.tags());
    }

    @GetMapping("/favorites")
    @Operation(summary = "收藏的提示词")
    public ResponseEntity<List<PromptSummaryDto>> favorites() {
        List<PromptSummaryDto> result = promptLibraryService.favorites().stream()
                .map(this::toDto)
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

    @PostMapping("/{id}/favorite")
    @Operation(summary = "收藏提示词")
    public ResponseEntity<Void> addFavorite(@PathVariable String id) {
        if (promptLibraryService.addFavorite(id)) {
            return ResponseEntity.ok().build();
        }
        log.warn("收藏的提示词不存在：{}", id);
        return ResponseEntity.notFound().build();
    }

    @DeleteMapping("/{id}/favorite")
    @Operation(summary = "取消收藏提示词")
    public ResponseEntity<Void> removeFavorite(@PathVariable String id) {
        if (promptLibraryService.removeFavorite(id)) {
            return ResponseEntity.ok().build();
        }
        log.warn("取消收藏的提示词不存在：{}", id);
        return ResponseEntity.notFound().build();
    }
}


