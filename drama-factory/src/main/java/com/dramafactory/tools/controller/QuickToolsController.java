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
    public Map<String, Object> batchTag(@RequestBody BatchTagRequest req) {
        int count = quickToolsService.batchTagAssets(req.ids(), req.tags(), req.mode());
        return Map.of("count", count);
    }

    @PostMapping("/assets/batch-rename")
    public Map<String, Object> batchRename(@RequestBody BatchRenameRequest req) {
        int count = quickToolsService.batchRenameAssets(req.renames());
        return Map.of("count", count);
    }

    @PostMapping("/video/convert")
    public AssetController.AssetDto convertVideo(@RequestBody ConvertRequest req) {
        return AssetController.AssetDto.from(
                quickToolsService.convertVideo(req.assetId(), req.format(), req.maxWidth()));
    }

    @PostMapping("/video/extract-audio")
    public AssetController.AssetDto extractAudio(@RequestBody ExtractAudioRequest req) {
        return AssetController.AssetDto.from(
                quickToolsService.extractAudio(req.assetId(), req.format()));
    }

    @GetMapping("/episodes/{id}/shots.csv")
    public ResponseEntity<byte[]> exportShotsCsv(@PathVariable Long id) {
        byte[] body = quickToolsService.exportShotCsv(id);
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.parseMediaType("text/csv;charset=UTF-8"));
        headers.set(HttpHeaders.CONTENT_DISPOSITION,
                "attachment; filename=\"shots-episode-" + id + ".csv\"");
        return new ResponseEntity<>(body, headers, org.springframework.http.HttpStatus.OK);
    }

    @GetMapping("/op-logs")
    public List<ToolOpLog> opLogs() {
        return toolOpLogRepository.findTop50ByOrderByCreatedAtDesc();
    }
}
