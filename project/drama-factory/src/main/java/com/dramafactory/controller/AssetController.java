package com.dramafactory.controller;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetSource;
import com.dramafactory.model.AssetType;
import com.dramafactory.service.AssetService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Value;

import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;

/**
 * 资产库 REST 接口。
 */
@RestController
@RequestMapping("/api/assets")
@Tag(name = "资产库", description = "素材上传、查询、打标签、复用与下载接口")
public class AssetController {


    private final AssetService assetService;

    private final String storageDir;

    public AssetController(AssetService assetService,
                           @Value("${drama.storage:./data/media}") String storageDir) {
        this.assetService = assetService;
        this.storageDir = storageDir;
    }

    /** 上传素材 */
    @PostMapping("/upload")
    @Operation(summary = "上传素材")
    public AssetDto upload(
            @Parameter(description = "上传的文件") @RequestParam("file") MultipartFile file,
            @Parameter(description = "标签") @RequestParam(value = "tags", required = false) String tags,
            @Parameter(description = "关联的运行 ID") @RequestParam(value = "runId", required = false) Long runId) {

        return AssetDto.from(assetService.upload(file, tags, runId));
    }

    /** 查询资产列表 */
    @GetMapping("/")
    @Operation(summary = "查询资产列表")
    public List<AssetDto> list(
            @Parameter(description = "资产类型") @RequestParam(value = "type", required = false) AssetType type,
            @Parameter(description = "资产来源") @RequestParam(value = "source", required = false) AssetSource source,
            @Parameter(description = "关键字") @RequestParam(value = "keyword", required = false) String keyword) {

        return assetService.list(type, source, keyword).stream()
                .map(AssetDto::from)
                .toList();
    }

    /** 更新标签 */
    @PutMapping("/{id}/tags")
    @Operation(summary = "更新资产标签")
    public AssetDto updateTags(
            @Parameter(description = "资产 ID") @PathVariable("id") Long id,
            @RequestBody TagRequest body) {

        return AssetDto.from(assetService.tag(id, body == null ? null : body.tags()));
    }

    /** 复用资产到剧集/分镜 */
    @PostMapping("/{id}/reuse")
    @Operation(summary = "复用资产到剧集或分镜")
    public AssetDto reuse(
            @Parameter(description = "资产 ID") @PathVariable("id") Long id,
            @RequestBody ReuseRequest body) {

        Long episodeId = body == null ? null : body.episodeId();
        Long shotId = body == null ? null : body.shotId();
        return AssetDto.from(assetService.reuse(id, episodeId, shotId));
    }

    /** 删除资产 */
    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @Operation(summary = "删除资产")
    public void delete(@Parameter(description = "资产 ID") @PathVariable("id") Long id) {

        assetService.delete(id);
    }

    /** 下载/预览资产文件 */
    @GetMapping("/{id}/file")
    @Operation(summary = "下载或预览资产文件")
    public ResponseEntity<Resource> file(@Parameter(description = "资产 ID") @PathVariable("id") Long id) {

        Asset asset = assetService.list(null, null, null).stream()
                .filter(a -> a.getId() != null && a.getId().equals(id))
                .findFirst()
                .orElseThrow(() -> new ResourceNotFoundException("Asset", id));

        String filePath = asset.getFilePath();
        if (filePath == null || !filePath.startsWith("assets/")) {
            throw new IllegalArgumentException("非法的资产文件路径");
        }
        Path base = Paths.get(storageDir).toAbsolutePath().normalize();
        Path resolved = base.resolve(filePath).normalize();
        if (!resolved.startsWith(base) || !Files.exists(resolved)) {
            throw new ResourceNotFoundException("Asset file", id);
        }

        MediaType mediaType = MediaType.APPLICATION_OCTET_STREAM;
        if (asset.getMimeType() != null) {
            try {
                mediaType = MediaType.parseMediaType(asset.getMimeType());
            } catch (Exception ignored) {
                // 保持默认
            }
        }

        Resource resource = new FileSystemResource(resolved);
        return ResponseEntity.ok()
                .contentType(mediaType)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "inline; filename=\"" + asset.getFileName() + "\"")
                .body(resource);
    }

    /** 标签更新请求体 */
    public record TagRequest(String tags) {
    }

    /** 复用请求体 */
    public record ReuseRequest(Long episodeId, Long shotId) {
    }

    /** 资产 DTO */
    public record AssetDto(
            Long id,
            AssetType type,
            AssetSource source,
            String fileName,
            String filePath,
            String mimeType,
            Long fileSize,
            String tags,
            Long runId,
            Long episodeId,
            Long shotId,
            String provider,
            java.time.LocalDateTime createdAt) {

        public static AssetDto from(Asset a) {
            return new AssetDto(
                    a.getId(),
                    a.getType(),
                    a.getSource(),
                    a.getFileName(),
                    a.getFilePath(),
                    a.getMimeType(),
                    a.getFileSize(),
                    a.getTags(),
                    a.getRunId(),
                    a.getEpisodeId(),
                    a.getShotId(),
                    a.getProvider(),
                    a.getCreatedAt());
        }
    }
}
