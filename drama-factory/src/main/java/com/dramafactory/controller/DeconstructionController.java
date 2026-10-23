package com.dramafactory.controller;

import com.dramafactory.dto.DeconstructionDtos;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoDeconstruction;
import com.dramafactory.model.VideoDeconstructionShot;
import com.dramafactory.service.DeconstructionService;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;

@RestController
@RequestMapping("/api/projects/{projectId}/deconstructions")
@Tag(name = "视频拆解", description = "视频拆解：上传/选素材发起拆解、查看结构与逐镜反推提示词、导出报告、生成同款分镜")
public class DeconstructionController {

    private final DeconstructionService service;

    /**
     * 视频拆解控制器，支持通过上传视频或选择素材创建拆解任务，管理拆解流程。
     * 链接导入为后续项，本控制器只支持上传与已有素材。
     */
    public DeconstructionController(DeconstructionService service) {
        this.service = service;
    }

    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(summary = "上传文件创建拆解任务")
    public ResponseEntity<DeconstructionDtos.SummaryDto> upload(
            @PathVariable Long projectId,
            @RequestParam("file") MultipartFile file) {
        VideoDeconstruction deconstruction = service.createFromUpload(projectId, file);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.toSummary(deconstruction));
    }

    @PostMapping
    @Operation(summary = "通过素材创建拆解任务")
    public ResponseEntity<DeconstructionDtos.SummaryDto> createFromAsset(
            @PathVariable Long projectId,
            @Valid @RequestBody DeconstructionDtos.CreateFromAssetRequest request) {
        VideoDeconstruction deconstruction = service.createFromAsset(projectId, request.assetId());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.toSummary(deconstruction));
    }

    @GetMapping
    @Operation(summary = "获取项目下所有拆解任务列表")
    public List<DeconstructionDtos.SummaryDto> list(@PathVariable Long projectId) {
        return service.listByProject(projectId).stream()
                .map(service::toSummary)
                .toList();
    }

    @GetMapping("/{id}")
    @Operation(summary = "获取拆解任务详情（含镜头列表）")
    public DeconstructionDtos.DetailDto detail(
            @PathVariable Long projectId,
            @PathVariable Long id) {
        VideoDeconstruction deconstruction = service.getInProject(projectId, id);
        List<VideoDeconstructionShot> shots = service.shotsOf(id);
        return service.toDetail(deconstruction, shots);
    }

    @GetMapping(value = "/{id}/report", produces = "text/markdown;charset=UTF-8")
    @Operation(summary = "下载拆解报告（Markdown格式）")
    public ResponseEntity<String> report(
            @PathVariable Long projectId,
            @PathVariable Long id) {
        VideoDeconstruction deconstruction = service.getInProject(projectId, id);
        if (deconstruction.getReportMd() == null) {
            throw new IllegalStateException("报告尚未生成，当前状态：" + deconstruction.getStatus());
        }

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(new MediaType("text", "markdown", StandardCharsets.UTF_8));
        headers.setContentDispositionFormData(
                "attachment", 
                "deconstruction-report-" + id + ".md"
        );

        return new ResponseEntity<>(deconstruction.getReportMd(), headers, HttpStatus.OK);
    }

    @GetMapping("/{id}/shots/{shotNo}/keyframe")
    @Operation(summary = "获取镜头关键帧图片")
    public ResponseEntity<Resource> keyframe(
            @PathVariable Long projectId,
            @PathVariable Long id,
            @PathVariable int shotNo) {
        Path keyframePath = service.keyframeFile(projectId, id, shotNo);
        return ResponseEntity.ok()
                .contentType(MediaType.IMAGE_JPEG)
                .body(new FileSystemResource(keyframePath));
    }

    @PostMapping("/{id}/generate-shots")
    @Operation(summary = "根据拆解生成镜头")
    public ResponseEntity<DeconstructionDtos.GenerateShotsResponse> generateShots(
            @PathVariable Long projectId,
            @PathVariable Long id,
            @Valid @RequestBody DeconstructionDtos.GenerateShotsRequest request) {
        List<Shot> shots = service.generateShots(projectId, id, request.episodeId());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new DeconstructionDtos.GenerateShotsResponse(
                        id,
                        request.episodeId(),
                        shots.size(),
                        shots.stream().map(Shot::getId).toList()
                ));
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "删除拆解任务")
    public ResponseEntity<Void> delete(
            @PathVariable Long projectId,
            @PathVariable Long id) {
        service.delete(projectId, id);
        return ResponseEntity.noContent().build();
    }
}
