package com.dramafactory.controller;

import com.dramafactory.service.prompt.PromptLibraryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;


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
    @Operation(summary = "提示词分页列表",
            description = "page 从 0 开始计数；size 取值范围 1 到 100；page 为负数或 size 越界时返回 400，错误码 invalid_pagination")
    public ResponseEntity<PageDto<PromptSummaryDto>> page(
            @RequestParam(required = false) String q,
            @RequestParam(required = false) String tag,
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer size) {
        int pageNum = page == null ? 0 : page;
        int sizeNum = size == null ? 20 : size;
        if (pageNum < 0) {
            throw new InvalidPaginationException("page 不能为负数");
        }
        if (sizeNum < 1 || sizeNum > 100) {
            throw new InvalidPaginationException("size 必须在 1 到 100 之间");
        }
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

    /**
     * 收藏提示词（幂等）：
     * <ul>
     *   <li>目标存在且未收藏：加入收藏，返回 200；</li>
     *   <li>目标存在且已收藏：不做任何变更，仍返回 200，不会重复收藏；</li>
     *   <li>目标不存在：返回 404。</li>
     * </ul>
     * 并发收藏同一 id 时串行执行，最终只保留一条收藏记录。
     */
    @PostMapping("/{id}/favorite")
    @Operation(summary = "收藏提示词",
            description = "幂等：重复收藏同一提示词仍返回 200，且收藏列表中只保留一条记录；提示词不存在时返回 404")
    public ResponseEntity<Void> addFavorite(@PathVariable String id) {
        if (promptLibraryService.addFavorite(id)) {
            return ResponseEntity.ok().build();
        }
        log.warn("收藏的提示词不存在：{}", id);
        return ResponseEntity.notFound().build();
    }

    /**
     * 取消收藏提示词（幂等）：
     * <ul>
     *   <li>目标存在且已收藏：移除收藏，返回 200；</li>
     *   <li>目标存在但未收藏：不做任何变更，仍返回 200；</li>
     *   <li>目标不存在：返回 404。</li>
     * </ul>
     */
    @DeleteMapping("/{id}/favorite")
    @Operation(summary = "取消收藏提示词",
            description = "幂等：对未收藏的提示词重复取消仍返回 200；提示词不存在时返回 404")
    public ResponseEntity<Void> removeFavorite(@PathVariable String id) {
        if (promptLibraryService.removeFavorite(id)) {
            return ResponseEntity.ok().build();
        }
        log.warn("取消收藏的提示词不存在：{}", id);
        return ResponseEntity.notFound().build();
    }

    @ExceptionHandler(InvalidPaginationException.class)
    public ResponseEntity<Map<String, String>> handleInvalidPagination(InvalidPaginationException e) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(Map.of("code", "invalid_pagination", "message", e.getMessage()));
    }
}


