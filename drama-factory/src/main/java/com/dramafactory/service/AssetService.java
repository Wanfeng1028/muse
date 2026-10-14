package com.dramafactory.service;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetSource;
import com.dramafactory.model.AssetType;
import com.dramafactory.repository.AssetRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

/**
 * 资产库业务服务：负责上传、查询、打标、删除、复用、登记生成物等。
 * 所有文件读写均做路径穿越防护。
 */
@Service
public class AssetService {

    /** 上传文件大小上限：50MB */
    private static final long MAX_UPLOAD_BYTES = 50L * 1024 * 1024;

    /** 资产存储相对根目录前缀 */
    private static final String ASSET_PREFIX = "assets/";

    private final AssetRepository assetRepository;

    private final String storageDir;

    public AssetService(AssetRepository assetRepository,
                        @Value("${drama.storage:./data/media}") String storageDir) {
        this.assetRepository = assetRepository;
        this.storageDir = storageDir;
    }

    /**
     * 上传素材。
     *
     * @param file  上传的文件，不能为空
     * @param tags  逗号分隔的标签，可空
     * @param runId 关联的 Run id，可空
     * @return 持久化后的 Asset
     */
    @Transactional
    public Asset upload(MultipartFile file, String tags, Long runId) {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("上传文件不能为空");
        }
        long size = file.getSize();
        if (size > MAX_UPLOAD_BYTES) {
            throw new IllegalArgumentException("上传文件超过大小限制（最大 50MB）");
        }
        String mimeType = file.getContentType();
        AssetType type = resolveType(mimeType);
        if (type == null) {
            throw new IllegalArgumentException("不支持的文件类型：" + mimeType);
        }

        String originalName = file.getOriginalFilename();
        if (originalName == null || originalName.isBlank()) {
            originalName = "file";
        }
        String ext = extractExtension(originalName);
        String storedName = UUID.randomUUID().toString().replace("-", "") + ext;

        String relativePath = ASSET_PREFIX + type.name().toLowerCase() + "/" + storedName;
        Path target = resolveSafePath(relativePath);

        try {
            Files.createDirectories(target.getParent());
            try (InputStream in = file.getInputStream()) {
                Files.copy(in, target, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException e) {
            throw new IllegalStateException("保存上传文件失败：" + e.getMessage(), e);
        }

        Asset asset = new Asset();
        asset.setType(type);
        asset.setSource(AssetSource.UPLOADED);
        asset.setFileName(originalName);
        asset.setFilePath(relativePath);
        asset.setMimeType(mimeType);
        asset.setFileSize(size);
        asset.setTags(normalizeTags(tags));
        asset.setRunId(runId);

        return assetRepository.save(asset);
    }

    /**
     * 组合条件查询资产列表。
     */
    @Transactional(readOnly = true)
    public List<Asset> list(AssetType type, AssetSource source, String keyword) {
        String kw = (keyword == null || keyword.isBlank()) ? null : keyword.trim();
        return assetRepository.search(type, source, kw);
    }

    /**
     * 更新资产标签（去重、逗号分隔）。
     */
    @Transactional
    public Asset tag(Long id, String tags) {
        Asset asset = assetRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Asset", id));
        asset.setTags(normalizeTags(tags));
        return assetRepository.save(asset);
    }

    /**
     * 删除资产：先删磁盘文件（忽略文件不存在），再删数据库记录。
     */
    @Transactional
    public void delete(Long id) {
        Asset asset = assetRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Asset", id));

        String filePath = asset.getFilePath();
        if (filePath == null || !filePath.startsWith(ASSET_PREFIX)) {
            throw new IllegalArgumentException("非法的资产文件路径，拒绝删除：" + filePath);
        }
        Path target = resolveSafePath(filePath);
        try {
            Files.deleteIfExists(target);
        } catch (IOException e) {
            // 文件删除失败不阻断记录删除
        }
        assetRepository.delete(asset);
    }

    /**
     * 将资产复用到指定剧集/分镜。
     */
    @Transactional
    public Asset reuse(Long id, Long episodeId, Long shotId) {
        Asset asset = assetRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Asset", id));
        asset.setEpisodeId(episodeId);
        asset.setShotId(shotId);
        return assetRepository.save(asset);
    }

    /**
     * 登记 BYOK 生成的资产。
     *
     * @param filePath 存储相对路径，必须位于 assets/ 下
     * @param type     资产类型
     * @param mimeType MIME 类型
     * @param fileSize 字节数
     * @param provider 供应商名
     * @param prompt   提示词
     * @param runId    关联 Run id，可空
     * @return 持久化后的 Asset
     */
    @Transactional
    public Asset registerGenerated(String filePath, AssetType type, String mimeType,
                                   long fileSize, String provider, String prompt, Long runId) {
        if (filePath == null || filePath.isBlank()) {
            throw new IllegalArgumentException("生成资产的 filePath 不能为空");
        }
        String relative = filePath.startsWith("/") ? filePath.substring(1) : filePath;
        if (!relative.startsWith(ASSET_PREFIX)) {
            // BYOK 生成路径通常为 byok/...，统一归档到 assets/ 下
            relative = ASSET_PREFIX + relative;
        }

        Asset asset = new Asset();
        asset.setType(type);
        asset.setSource(AssetSource.GENERATED);
        asset.setFileName(lastSegment(relative));
        asset.setFilePath(relative);
        asset.setMimeType(mimeType);
        asset.setFileSize(fileSize);
        asset.setProvider(provider);
        asset.setPrompt(prompt);
        asset.setRunId(runId);

        return assetRepository.save(asset);
    }

    /**
     * 根据 MIME 类型解析资产类型；无法识别返回 null。
     */
    private AssetType resolveType(String mimeType) {
        if (mimeType == null || mimeType.isBlank()) {
            return null;
        }
        String m = mimeType.toLowerCase();
        if (m.startsWith("image/")) {
            return AssetType.IMAGE;
        }
        if (m.startsWith("audio/")) {
            return AssetType.AUDIO;
        }
        if (m.startsWith("video/")) {
            return AssetType.VIDEO;
        }
        return null;
    }

    /**
     * 将相对路径解析为 storageDir 下的安全绝对路径。
     * 使用 normalize + startsWith 校验，防止路径穿越。
     */
    private Path resolveSafePath(String relativePath) {
        Path base = Paths.get(storageDir).toAbsolutePath().normalize();
        Path resolved = base.resolve(relativePath).normalize();
        if (!resolved.startsWith(base)) {
            throw new IllegalArgumentException("检测到非法路径穿越：" + relativePath);
        }
        return resolved;
    }

    /** 规范化标签：去空、去重、逗号拼接 */
    private String normalizeTags(String tags) {
        if (tags == null || tags.isBlank()) {
            return null;
        }
        Set<String> set = new LinkedHashSet<>();
        for (String t : tags.split(",")) {
            String v = t.trim();
            if (!v.isEmpty()) {
                set.add(v);
            }
        }
        return set.isEmpty() ? null : String.join(",", set);
    }

    /** 提取扩展名（含点），无扩展名返回空串 */
    private String extractExtension(String fileName) {
        int idx = fileName.lastIndexOf('.');
        if (idx < 0 || idx == fileName.length() - 1) {
            return "";
        }
        return fileName.substring(idx);
    }

    /** 取路径最后一段 */
    private String lastSegment(String path) {
        int idx = path.lastIndexOf('/');
        return idx < 0 ? path : path.substring(idx + 1);
    }
}
