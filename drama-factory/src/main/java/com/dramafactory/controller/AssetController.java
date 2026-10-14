package com.dramafactory.controller;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetSource;
import com.dramafactory.model.AssetType;
import com.dramafactory.service.AssetService;
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
    public AssetDto upload(@RequestParam("file") MultipartFile file,
                           @RequestParam(value = "tags", required = false) String tags,
                           @RequestParam(value = "runId", required = false) Long runId) {
        return AssetDto.from(assetService.upload(file, tags, runId));
    }

    /** 查询资产列表 */
    @GetMapping("/")
    public List<AssetDto> list(@RequestParam(value = "type", required = false) AssetType type,
                               @RequestParam(value = "source", required = false) AssetSource source,
                               @RequestParam(value = "keyword", required = false) String keyword) {
        return assetService.list(type, source, keyword).stream()
                .map(AssetDto::from)
                .toList();
    }

    /** 更新标签 */
    @PutMapping("/{id}/tags")
    public AssetDto updateTags(@PathVariable("id") Long id,
                               @RequestBody TagRequest body) {
        return AssetDto.from(assetService.tag(id, body == null ? null : body.tags()));
    }

    /** 复用资产到剧集/分镜 */
    @PostMapping("/{id}/reuse")
    public AssetDto reuse(@PathVariable("id") Long id,
                          @RequestBody ReuseRequest body) {
        Long episodeId = body == null ? null : body.episodeId();
        Long shotId = body == null ? null : body.shotId();
        return AssetDto.from(assetService.reuse(id, episodeId, shotId));
    }

    /** 删除资产 */
    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable("id") Long id) {
        assetService.delete(id);
    }

    /** 下载/预览资产文件 */
    @GetMapping("/{id}/file")
    public ResponseEntity<Resource> file(@PathVariable("id") Long id) {
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
