package com.dramafactory.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

/**
 * 资产实体：统一管理图片/音频/视频素材。
 * 既包括用户上传的素材，也包括 BYOK 生成的素材。
 */
@Entity
@Table(name = "assets")
public class Asset {

    /** 主键 */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 资产类型：图片/音频/视频 */
    @Enumerated(EnumType.STRING)
    @Column(name = "type", length = 16, nullable = false)
    private AssetType type;

    /** 资产来源：生成/上传 */
    @Enumerated(EnumType.STRING)
    @Column(name = "source", length = 16, nullable = false)
    private AssetSource source;

    /** 原始文件名 */
    @Column(name = "file_name", length = 255, nullable = false)
    private String fileName;

    /** 存储相对路径，如 assets/image/xxx.png */
    @Column(name = "file_path", length = 1000, nullable = false)
    private String filePath;

    /** MIME 类型 */
    @Column(name = "mime_type", length = 100)
    private String mimeType;

    /** 文件字节数 */
    @Column(name = "file_size")
    private Long fileSize;

    /** 逗号分隔的标签，可空 */
    @Column(name = "tags", length = 1000)
    private String tags;

    /** 关联的 Run id，可空 */
    @Column(name = "run_id")
    private Long runId;

    /** 复用关联的剧集 id，可空 */
    @Column(name = "episode_id")
    private Long episodeId;

    /** 复用关联的分镜 id，可空 */
    @Column(name = "shot_id")
    private Long shotId;

    /** 生成时的供应商名（BYOK），可空 */
    @Column(name = "provider", length = 100)
    private String provider;

    /** 生成时的提示词（BYOK），可空 */
    @Column(name = "prompt", length = 2000)
    private String prompt;

    /** 创建时间 */
    @Column(name = "created_at")
    private LocalDateTime createdAt;

    /** 更新时间 */
    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    /** 持久化前填充时间戳 */
    @PrePersist
    public void onCreate() {
        LocalDateTime now = LocalDateTime.now();
        this.createdAt = now;
        this.updatedAt = now;
    }

    /** 更新前刷新 updatedAt */
    @PreUpdate
    public void onUpdate() {
        this.updatedAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public AssetType getType() {
        return type;
    }

    public void setType(AssetType type) {
        this.type = type;
    }

    public AssetSource getSource() {
        return source;
    }

    public void setSource(AssetSource source) {
        this.source = source;
    }

    public String getFileName() {
        return fileName;
    }

    public void setFileName(String fileName) {
        this.fileName = fileName;
    }

    public String getFilePath() {
        return filePath;
    }

    public void setFilePath(String filePath) {
        this.filePath = filePath;
    }

    public String getMimeType() {
        return mimeType;
    }

    public void setMimeType(String mimeType) {
        this.mimeType = mimeType;
    }

    public Long getFileSize() {
        return fileSize;
    }

    public void setFileSize(Long fileSize) {
        this.fileSize = fileSize;
    }

    public String getTags() {
        return tags;
    }

    public void setTags(String tags) {
        this.tags = tags;
    }

    public Long getRunId() {
        return runId;
    }

    public void setRunId(Long runId) {
        this.runId = runId;
    }

    public Long getEpisodeId() {
        return episodeId;
    }

    public void setEpisodeId(Long episodeId) {
        this.episodeId = episodeId;
    }

    public Long getShotId() {
        return shotId;
    }

    public void setShotId(Long shotId) {
        this.shotId = shotId;
    }

    public String getProvider() {
        return provider;
    }

    public void setProvider(String provider) {
        this.provider = provider;
    }

    public String getPrompt() {
        return prompt;
    }

    public void setPrompt(String prompt) {
        this.prompt = prompt;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(LocalDateTime updatedAt) {
        this.updatedAt = updatedAt;
    }
}
