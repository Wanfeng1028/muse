package com.dramafactory.tools.controller;

import com.dramafactory.controller.AssetController;
import com.dramafactory.tools.model.ToolOpLog;
import com.dramafactory.tools.repository.ToolOpLogRepository;
import com.dramafactory.tools.service.QuickToolsService;
import com.dramafactory.tools.service.ToolOpLogService;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/tools")
@io.swagger.v3.oas.annotations.tags.Tag(name = "快捷工具", description = "素材批量处理与视频转换工具接口")
public class QuickToolsController {


    private final QuickToolsService quickToolsService;
    private final ToolOpLogService toolOpLogService;
    private final ToolOpLogRepository toolOpLogRepository;

    public QuickToolsController(QuickToolsService quickToolsService,
                                ToolOpLogService toolOpLogService,
                                ToolOpLogRepository toolOpLogRepository) {
        this.quickToolsService = quickToolsService;
        this.toolOpLogService = toolOpLogService;
        this.toolOpLogRepository = toolOpLogRepository;
    }

    public record BatchTagRequest(List<Long> ids, String tags, String mode) {
    }

    public record BatchRenameRequest(Map<Long, String> renames) {
    }

    public record ConvertRequest(Long assetId, String format, Integer maxWidth) {
    }

    public record ExtractAudioRequest(Long assetId, String format) {
    }

    @PostMapping("/assets/batch-tag")
    @io.swagger.v3.oas.annotations.Operation(summary = "批量打标签")
    public Map<String, Object> batchTag(@RequestBody BatchTagRequest req) {

        int count = quickToolsService.batchTagAssets(req.ids(), req.tags(), req.mode());
        return Map.of("count", count);
    }

    @PostMapping("/assets/batch-rename")
    @io.swagger.v3.oas.annotations.Operation(summary = "批量重命名")
    public Map<String, Object> batchRename(@RequestBody BatchRenameRequest req) {

        int count = quickToolsService.batchRenameAssets(req.renames());
        return Map.of("count", count);
    }

    @PostMapping("/video/convert")
    @io.swagger.v3.oas.annotations.Operation(summary = "视频格式转换")
    public AssetController.AssetDto convertVideo(@RequestBody ConvertRequest req) {

        return AssetController.AssetDto.from(
                quickToolsService.convertVideo(req.assetId(), req.format(), req.maxWidth()));
    }

    @PostMapping("/video/extract-audio")
    @io.swagger.v3.oas.annotations.Operation(summary = "从视频提取音频")
    public AssetController.AssetDto extractAudio(@RequestBody ExtractAudioRequest req) {

        return AssetController.AssetDto.from(
                quickToolsService.extractAudio(req.assetId(), req.format()));
    }

    @GetMapping("/episodes/{id}/shots.csv")
    @io.swagger.v3.oas.annotations.Operation(summary = "导出剧集分镜为 CSV")
    public ResponseEntity<byte[]> exportShotsCsv(
            @io.swagger.v3.oas.annotations.Parameter(description = "剧集 ID") @PathVariable Long id) {

        byte[] body = quickToolsService.exportShotCsv(id);
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.parseMediaType("text/csv;charset=UTF-8"));
        headers.set(HttpHeaders.CONTENT_DISPOSITION,
                "attachment; filename=\"shots-episode-" + id + ".csv\"");
        return new ResponseEntity<>(body, headers, org.springframework.http.HttpStatus.OK);
    }

    @GetMapping("/op-logs")
    @io.swagger.v3.oas.annotations.Operation(summary = "查询最近 50 条工具操作日志")
    public List<ToolOpLog> opLogs() {

        return toolOpLogRepository.findTop50ByOrderByCreatedAtDesc();
    }
}
