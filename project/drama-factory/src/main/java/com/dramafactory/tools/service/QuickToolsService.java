package com.dramafactory.tools.service;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetType;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.repository.AssetRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.service.AssetService;
import com.dramafactory.service.FfmpegService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

@Service
public class QuickToolsService {

    private static final DateTimeFormatter CSV_TIME_FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");

    private final AssetRepository assetRepository;
    private final AssetService assetService;
    private final FfmpegService ffmpegService;
    private final ShotRepository shotRepository;
    private final EpisodeRepository episodeRepository;
    private final ToolOpLogService toolOpLogService;
    private final String storageDir;

    public QuickToolsService(AssetRepository assetRepository,
                             AssetService assetService,
                             FfmpegService ffmpegService,
                             ShotRepository shotRepository,
                             EpisodeRepository episodeRepository,
                             ToolOpLogService toolOpLogService,
                             @Value("${drama.storage:./data/media}") String storageDir) {
        this.assetRepository = assetRepository;
        this.assetService = assetService;
        this.ffmpegService = ffmpegService;
        this.shotRepository = shotRepository;
        this.episodeRepository = episodeRepository;
        this.toolOpLogService = toolOpLogService;
        this.storageDir = storageDir;
    }

    /**
     * 批量给资产打标签。
     */
    public int batchTagAssets(List<Long> ids, String tags, String mode) {
        if (ids == null || ids.isEmpty()) {
            throw new IllegalArgumentException("ids 不能为空");
        }
        String normalizedMode = mode == null ? "merge" : mode;
        if (!"merge".equals(normalizedMode) && !"replace".equals(normalizedMode)) {
            throw new IllegalArgumentException("mode 只能为 merge 或 replace");
        }
        String normalizedTags = normalizeTags(tags);
        if ("merge".equals(normalizedMode) && normalizedTags.isEmpty()) {
            throw new IllegalArgumentException("tags 不能为空");
        }
        String params = "ids=" + ids.size() + ",mode=" + normalizedMode;
        try {
            List<Asset> assets = assetRepository.findAllById(ids);
            Set<Long> found = new HashSet<>();
            for (Asset a : assets) {
                found.add(a.getId());
            }
            for (Long id : ids) {
                if (!found.contains(id)) {
                    throw new ResourceNotFoundException("Asset", id);
                }
            }
            for (Asset a : assets) {
                if ("replace".equals(normalizedMode)) {
                    a.setTags(normalizedTags.isEmpty() ? null : normalizedTags);
                } else {
                    LinkedHashSet<String> merged = new LinkedHashSet<>();
                    for (String t : splitTags(a.getTags())) {
                        merged.add(t);
                    }
                    for (String t : splitTags(normalizedTags)) {
                        merged.add(t);
                    }
                    a.setTags(String.join(",", merged));
                }
            }
            assetRepository.saveAll(assets);
            toolOpLogService.log("batchTagAssets", "batch-tag", params, "count=" + assets.size(), true);
            return assets.size();
        } catch (RuntimeException e) {
            toolOpLogService.log("batchTagAssets", "batch-tag", params, e.getMessage(), false);
            throw e;
        }
    }

    /**
     * 批量重命名资产。
     */
    public int batchRenameAssets(Map<Long, String> renames) {
        if (renames == null || renames.isEmpty()) {
            throw new IllegalArgumentException("renames 不能为空");
        }
        for (Map.Entry<Long, String> e : renames.entrySet()) {
            String name = e.getValue();
            if (name == null || name.trim().isEmpty()) {
                throw new IllegalArgumentException("新文件名不能为空");
            }
            int len = name.trim().length();
            if (len < 1 || len > 200) {
                throw new IllegalArgumentException("新文件名长度必须在 1~200 之间");
            }
        }
        String params = "count=" + renames.size();
        try {
            List<Asset> toSave = new ArrayList<>();
            for (Map.Entry<Long, String> e : renames.entrySet()) {
                Asset asset = assetRepository.findById(e.getKey())
                        .orElseThrow(() -> new ResourceNotFoundException("Asset", e.getKey()));
                asset.setFileName(e.getValue().trim());
                toSave.add(asset);
            }
            assetRepository.saveAll(toSave);
            toolOpLogService.log("batchRenameAssets", "batch-rename", params, "count=" + toSave.size(), true);
            return toSave.size();
        } catch (RuntimeException e) {
            toolOpLogService.log("batchRenameAssets", "batch-rename", params, e.getMessage(), false);
            throw e;
        }
    }

    /**
     * 转换视频格式 / 压缩分辨率。
     */
    public Asset convertVideo(Long assetId, String format, Integer maxWidth) {
        String normalizedFormat = format == null ? "mp4" : format;
        if (!"mp4".equals(normalizedFormat) && !"webm".equals(normalizedFormat)) {
            throw new IllegalArgumentException("format 只能为 mp4 或 webm");
        }
        if (maxWidth != null && (maxWidth < 144 || maxWidth > 3840)) {
            throw new IllegalArgumentException("maxWidth 必须在 144~3840 之间");
        }
        String params = "assetId=" + assetId + ",format=" + normalizedFormat + ",maxWidth=" + maxWidth;
        try {
            Asset asset = assetRepository.findById(assetId)
                    .orElseThrow(() -> new ResourceNotFoundException("Asset", assetId));
            if (asset.getType() != AssetType.VIDEO) {
                throw new IllegalArgumentException("只有视频资产可以转换");
            }
            Path in = resolveStoragePath(asset.getFilePath());
            Path outDir = Paths.get(storageDir).resolve("assets").resolve("tools");
            try {
                Files.createDirectories(outDir);
            } catch (IOException e) {
                throw new RuntimeException("无法创建输出目录: " + outDir, e);
            }
            String ext = "webm".equals(normalizedFormat) ? ".webm" : ".mp4";
            String fileName = UUID.randomUUID().toString().replace("-", "") + ext;
            Path out = outDir.resolve(fileName).normalize();
            if (!out.startsWith(Paths.get(storageDir).toAbsolutePath().normalize())
                    && !out.startsWith(Paths.get(storageDir).normalize())) {
                throw new IllegalArgumentException("输出路径非法");
            }
            ffmpegService.convertVideo(in, out, normalizedFormat, maxWidth);
            long size;
            try {
                size = Files.size(out);
            } catch (IOException e) {
                throw new RuntimeException("读取输出文件大小失败: " + out, e);
            }
            String mimeType = "webm".equals(normalizedFormat) ? "video/webm" : "video/mp4";
            Asset created = assetService.registerGenerated(
                    "assets/tools/" + fileName,
                    AssetType.VIDEO,
                    mimeType,
                    size,
                    "quick-tools",
                    null,
                    null);
            toolOpLogService.log("convertVideo", "video-convert", params, "assetId=" + created.getId(), true);
            return created;
        } catch (RuntimeException e) {
            toolOpLogService.log("convertVideo", "video-convert", params, e.getMessage(), false);
            throw e;
        }
    }

    /**
     * 从视频提取音频。
     */
    public Asset extractAudio(Long assetId, String format) {
        String normalizedFormat = format == null ? "mp3" : format;
        if (!"mp3".equals(normalizedFormat) && !"wav".equals(normalizedFormat)) {
            throw new IllegalArgumentException("format 只能为 mp3 或 wav");
        }
        String params = "assetId=" + assetId + ",format=" + normalizedFormat;
        try {
            Asset asset = assetRepository.findById(assetId)
                    .orElseThrow(() -> new ResourceNotFoundException("Asset", assetId));
            if (asset.getType() != AssetType.VIDEO) {
                throw new IllegalArgumentException("只有视频资产可以转换");
            }
            Path in = resolveStoragePath(asset.getFilePath());
            Path outDir = Paths.get(storageDir).resolve("assets").resolve("tools");
            try {
                Files.createDirectories(outDir);
            } catch (IOException e) {
                throw new RuntimeException("无法创建输出目录: " + outDir, e);
            }
            String ext = "wav".equals(normalizedFormat) ? ".wav" : ".mp3";
            String fileName = UUID.randomUUID().toString().replace("-", "") + ext;
            Path out = outDir.resolve(fileName).normalize();
            if (!out.startsWith(Paths.get(storageDir).normalize())) {
                throw new IllegalArgumentException("输出路径非法");
            }
            ffmpegService.extractAudio(in, out, normalizedFormat);
            long size;
            try {
                size = Files.size(out);
            } catch (IOException e) {
                throw new RuntimeException("读取输出文件大小失败: " + out, e);
            }
            String mimeType = "wav".equals(normalizedFormat) ? "audio/wav" : "audio/mpeg";
            Asset created = assetService.registerGenerated(
                    "assets/tools/" + fileName,
                    AssetType.AUDIO,
                    mimeType,
                    size,
                    "quick-tools",
                    null,
                    null);
            toolOpLogService.log("extractAudio", "video-extract-audio", params, "assetId=" + created.getId(), true);
            return created;
        } catch (RuntimeException e) {
            toolOpLogService.log("extractAudio", "video-extract-audio", params, e.getMessage(), false);
            throw e;
        }
    }

    /**
     * 导出某剧集的分镜 CSV（UTF-8 带 BOM）。
     */
    public byte[] exportShotCsv(Long episodeId) {
        String params = "episodeId=" + episodeId;
        try {
            Episode episode = episodeRepository.findById(episodeId)
                    .orElseThrow(() -> new ResourceNotFoundException("Episode", episodeId));
            List<Shot> shots = shotRepository.findByEpisodeIdOrderByShotNoAsc(episodeId);

            StringBuilder sb = new StringBuilder();
            sb.append('\uFEFF');
            sb.append(csvRow("镜号", "景别", "运镜", "画面描述", "台词", "时长(秒)", "创建时间"));
            for (Shot s : shots) {
                String shotNo = s.getShotNo() == null ? "" : String.valueOf(s.getShotNo());
                String shotSize = s.getShotSize() == null ? "" : s.getShotSize().name();
                String cameraMove = s.getCameraMove() == null ? "" : s.getCameraMove().name();
                String description = s.getDescription() == null ? "" : s.getDescription();
                String dialogue = s.getDialogue() == null ? "" : s.getDialogue();
                String duration = s.getDurationSeconds() == null ? "" : String.valueOf(s.getDurationSeconds());
                String createdAt = s.getCreatedAt() == null ? "" : s.getCreatedAt().format(CSV_TIME_FMT);
                sb.append(csvRow(shotNo, shotSize, cameraMove, description, dialogue, duration, createdAt));
            }
            byte[] bytes = sb.toString().getBytes(StandardCharsets.UTF_8);
            toolOpLogService.log("exportShotCsv", "episode-shots-csv", params, "rows=" + shots.size(), true);
            return bytes;
        } catch (RuntimeException e) {
            toolOpLogService.log("exportShotCsv", "episode-shots-csv", params, e.getMessage(), false);
            throw e;
        }
    }

    private Path resolveStoragePath(String filePath) {
        if (filePath == null || !filePath.startsWith("assets/")) {
            throw new IllegalArgumentException("资产路径非法");
        }
        Path base = Paths.get(storageDir).toAbsolutePath().normalize();
        Path resolved = base.resolve(filePath).normalize();
        if (!resolved.startsWith(base)) {
            throw new IllegalArgumentException("资产路径越界");
        }
        return resolved;
    }

    private static String normalizeTags(String tags) {
        if (tags == null) {
            return "";
        }
        LinkedHashSet<String> set = new LinkedHashSet<>();
        for (String t : tags.split(",")) {
            String v = t.trim();
            if (!v.isEmpty()) {
                set.add(v);
            }
        }
        return String.join(",", set);
    }

    private static List<String> splitTags(String tags) {
        List<String> list = new ArrayList<>();
        if (tags == null) {
            return list;
        }
        for (String t : tags.split(",")) {
            String v = t.trim();
            if (!v.isEmpty()) {
                list.add(v);
            }
        }
        return list;
    }

    private static String csvRow(String... cells) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < cells.length; i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append(csvEscape(cells[i]));
        }
        sb.append("\r\n");
        return sb.toString();
    }

    private static String csvEscape(String value) {
        if (value == null) {
            return "";
        }
        boolean needQuote = value.contains(",") || value.contains("\"")
                || value.contains("\n") || value.contains("\r");
        if (!needQuote) {
            return value;
        }
        return "\"" + value.replace("\"", "\"\"") + "\"";
    }
}
