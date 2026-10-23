package com.dramafactory.service;

import com.dramafactory.dto.DeconstructionDtos;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.*;
import com.dramafactory.repository.*;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * 视频拆解业务服务——创建（上传/选素材）、后台流水线（ffprobe实测→场景切分→抽关键帧→确定性分析→报告）、查询、生成同款分镜与删除；
 * 视觉字段只经 DeconstructionVisionEnricher 在开关打开时填充，默认不填充。
 */
@Service
public class DeconstructionService {

    private static final Logger log = LoggerFactory.getLogger(DeconstructionService.class);
    private static final long MAX_UPLOAD_BYTES = 200L * 1024 * 1024;
    private static final Set<String> VIDEO_EXTS = Set.of(".mp4", ".mov", ".mkv", ".webm", ".m4v");
    private static final Pattern PTS_TIME = Pattern.compile("pts_time:([0-9]+(?:\\.[0-9]+)?)");

    private final VideoDeconstructionRepository deconstructionRepository;
    private final VideoDeconstructionShotRepository shotRowRepository;
    private final DramaProjectRepository projectRepository;
    private final AssetRepository assetRepository;
    private final EpisodeRepository episodeRepository;
    private final ShotRepository shotRepository;
    private final FfmpegService ffmpegService;
    private final DeconstructionAnalyzer analyzer;
    private final DeconstructionReportBuilder reportBuilder;
    private final DeconstructionVisionEnricher visionEnricher;
    private final SubtitleTranscriptService transcriptService;
    private final ObjectMapper objectMapper;
    private final String storageDir;
    private final double sceneThreshold;
    private final int maxShots;
    private final double minShotSec;
    private final double fallbackSegmentSec;
    private final boolean visionEnabled;

    private final ExecutorService executor = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "deconstruction-worker");
        t.setDaemon(true);
        return t;
    });

    public DeconstructionService(
            VideoDeconstructionRepository deconstructionRepository,
            VideoDeconstructionShotRepository shotRowRepository,
            DramaProjectRepository projectRepository,
            AssetRepository assetRepository,
            EpisodeRepository episodeRepository,
            ShotRepository shotRepository,
            FfmpegService ffmpegService,
            DeconstructionAnalyzer analyzer,
            DeconstructionReportBuilder reportBuilder,
            DeconstructionVisionEnricher visionEnricher,
            SubtitleTranscriptService transcriptService,
            ObjectMapper objectMapper,
            @Value("${drama.storage:./data/media}") String storageDir,
            @Value("${drama.deconstruction.scene-threshold:0.35}") double sceneThreshold,
            @Value("${drama.deconstruction.max-shots:120}") int maxShots,
            @Value("${drama.deconstruction.min-shot-sec:0.4}") double minShotSec,
            @Value("${drama.deconstruction.fallback-segment-sec:2.5}") double fallbackSegmentSec,
            @Value("${drama.deconstruction.vision-enabled:false}") boolean visionEnabled) {
        this.deconstructionRepository = deconstructionRepository;
        this.shotRowRepository = shotRowRepository;
        this.projectRepository = projectRepository;
        this.assetRepository = assetRepository;
        this.episodeRepository = episodeRepository;
        this.shotRepository = shotRepository;
        this.ffmpegService = ffmpegService;
        this.analyzer = analyzer;
        this.reportBuilder = reportBuilder;
        this.visionEnricher = visionEnricher;
        this.transcriptService = transcriptService;
        this.objectMapper = objectMapper;
        this.storageDir = storageDir;
        this.sceneThreshold = sceneThreshold;
        this.maxShots = maxShots;
        this.minShotSec = minShotSec;
        this.fallbackSegmentSec = fallbackSegmentSec;
        this.visionEnabled = visionEnabled;
    }

    @PreDestroy
    public void shutdown() {
        executor.shutdownNow();
    }

    /**
     * 从上传文件创建视频拆解任务
     * @param projectId 项目ID
     * @param file 上传的视频文件
     * @return 创建的VideoDe实体
     */
    @Transactional
    public VideoDeconstruction createFromUpload(Long projectId, MultipartFile file) {
        DramaProject project = requireProject(projectId);
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("上传文件不能为空");
        }
        if (file.getSize() > MAX_UPLOAD_BYTES) {
            throw new IllegalArgumentException("视频文件超过大小限制（最大200MB）");
        }
        String original = file.getOriginalFilename();
        if (original == null || original.isEmpty()) {
            throw new IllegalArgumentException("文件名为空");
        }
        String ext = original.substring(original.lastIndexOf('.')).toLowerCase();
        if (!VIDEO_EXTS.contains(ext)) {
            throw new IllegalArgumentException("不支持的视频格式：" + ext);
        }

        VideoDeconstruction row = new VideoDeconstruction();
        row.setProjectId(projectId);
        row.setSourceName(original);
        row.setSourcePath("");
        row.setStatus(DeconstructionStatus.PENDING);
        row = deconstructionRepository.save(row);

        String rel = "deconstruction/" + row.getId() + "/source" + ext;
        Path dest = storageRoot().resolve(rel);
        try {
            Files.createDirectories(dest.getParent());
            file.transferTo(dest);
            row.setSourcePath(rel);
            deconstructionRepository.save(row);
            submitProcess(row.getId());
            return row;
        } catch (IOException e) {
            throw new IllegalStateException("保存上传文件失败", e);
        }
    }

    /**
     * 从现有视频素材创建拆解任务
     * @param projectId 项目ID
     * @param assetId 视频素材ID
     * @return 创建的VideoDe实体
     */
    @Transactional
    public VideoDeconstruction createFromAsset(Long projectId, Long assetId) {
        DramaProject project = requireProject(projectId);
        Asset asset = assetRepository.findById(assetId).orElseThrow(
            () -> new ResourceNotFoundException("Asset", assetId));
        if (asset.getType() != AssetType.VIDEO) {
            throw new IllegalArgumentException("所选素材不是视频");
        }

        VideoDeconstruction row = new VideoDeconstruction();
        row.setProjectId(projectId);
        row.setAssetId(assetId);
        row.setSourceName(asset.getFileName());
        row.setSourcePath(asset.getFilePath());
        row.setStatus(DeconstructionStatus.PENDING);
        row = deconstructionRepository.save(row);
        submitProcess(row.getId());
        return row;
    }

    /**
     * 获取项目的所有拆解任务列表
     * @param projectId 项目ID
     * @return 按创建时间倒序的任务列表
     */
    @Transactional(readOnly = true)
    public List<VideoDeconstruction> listByProject(Long projectId) {
        requireProject(projectId);
        return deconstructionRepository.findByProjectIdOrderByCreatedAtDesc(projectId);
    }

    /**
     * 在项目内获取指定拆解任务
     * @param projectId 项目ID
     * @param id 任务ID
     * @return VideoDe实体
     */
    @Transactional(readOnly = true)
    public VideoDeconstruction getInProject(Long projectId, Long id) {
        VideoDeconstruction row = deconstructionRepository.findById(id)
            .orElseThrow(() -> new ResourceNotFoundException("VideoDeconstruction", id));
        if (!row.getProjectId().equals(projectId)) {
            throw new ResourceNotFoundException("VideoDeconstruction", id);
        }
        return row;
    }

    /**
     * 获取拆解任务的逐镜分镜数据
     * @param deconstructionId 任务ID
     * @return 按镜号排序的分镜列表
     */
    @Transactional(readOnly = true)
    public List<VideoDeconstructionShot> shotsOf(Long deconstructionId) {
        return shotRowRepository.findByDeconstructionIdOrderByShotNoAsc(deconstructionId);
    }

    /**
     * 删除项目内的拆解任务及其所有数据
     * @param projectId 项目ID
     * @param id 任务ID
     */
    @Transactional
    public void delete(Long projectId, Long id) {
        VideoDeconstruction row = getInProject(projectId, id);
        shotRowRepository.deleteByDeconstructionId(id);
        deconstructionRepository.delete(row);
        Path dir = storageRoot().resolve("deconstruction/" + id);
        try {
            Files.walk(dir)
                .sorted(Comparator.reverseOrder())
                .forEach(p -> {
                    try { Files.delete(p); }
                    catch (IOException e) { log.warn("删除文件失败: {}", p, e); }
                });
        } catch (IOException e) {
            log.warn("删除任务目录失败: {}", dir, e);
        }
    }

    /**
     * 根据完成的拆解结果生成同款分镜到指定剧集
     * @param projectId 项目ID
     * @param id 拆解任务ID
     * @param episodeId 目标剧集ID
     * @return 生成的分镜列表
     */
    @Transactional
    public List<Shot> generateShots(Long projectId, Long id, Long episodeId) {
        VideoDeconstruction row = getInProject(projectId, id);
        if (row.getStatus() != DeconstructionStatus.DONE) {
            throw new IllegalStateException("拆解尚未完成，当前状态：" + row.getStatus());
        }
        Episode episode = episodeRepository.findById(episodeId).orElseThrow(
            () -> new ResourceNotFoundException("Episode", episodeId));
        if (episode.getProject() == null || !episode.getProject().getId().equals(projectId)) {
            throw new ResourceNotFoundException("Episode", episodeId);
        }

        List<VideoDeconstructionShot> rows = shotsOf(id);
        if (rows.isEmpty()) {
            throw new IllegalStateException("拆解没有可用的分镜结果");
        }

        List<Shot> baseShots = shotRepository.findByEpisodeIdOrderByShotNoAsc(episodeId);
        int maxShotNo = baseShots.isEmpty() ? 0 : 
            baseShots.stream().mapToInt(Shot::getShotNo).max().orElse(0);
        
        List<Shot> result = new ArrayList<>();
        for (VideoDeconstructionShot shotRow : rows) {
            Shot shot = new Shot();
            shot.setEpisode(episode);
            shot.setShotNo(maxShotNo + shotRow.getShotNo());
            shot.setDurationSeconds(Math.max(1, (int) Math.round(shotRow.getDurationSec())));
            shot.setDescription("视频拆解反推 · 第" + shotRow.getShotNo() + "镜 " + 
                fmt(shotRow.getStartSec()) + "–" + fmt(shotRow.getEndSec()) + 
                "s · 结构角色：" + shotRow.getSegmentRole() + 
                " · 画面主体/景别/运镜待 AI 增强");
            shot.setVideoPrompt(shotRow.getPromptSeedance() != null ? 
                shotRow.getPromptSeedance() : shotRow.getPromptGeneric());
            shotRepository.save(shot);
            result.add(shot);
        }
        return result;
    }

    /**
     * 获取关键帧文件的本地路径
     * @param projectId 项目ID
     * @param id 任务ID
     * @param shotNo 镜号
     * @return 关键帧文件路径
     */
    public Path keyframeFile(Long projectId, Long id, int shotNo) {
        VideoDeconstruction row = getInProject(projectId, id);
        return shotsOf(id).stream()
            .filter(s -> s.getShotNo() == shotNo && s.getKeyframePath() != null)
            .findFirst()
            .map(s -> {
                Path p = storageRoot().resolve(s.getKeyframePath()).normalize();
                if (!p.startsWith(storageRoot()) || !Files.isRegularFile(p)) {
                    throw new ResourceNotFoundException("Keyframe", id);
                }
                return p;
            })
            .orElseThrow(() -> new ResourceNotFoundException("Keyframe", id));
    }

    /**
     * 将VideoDe实体转换为摘要DTO
     * @param d VideoDe实体
     * @return SummaryDTO
     */
    public DeconstructionDtos.SummaryDto toSummary(VideoDeconstruction d) {
        return new DeconstructionDtos.SummaryDto(
            d.getId(),
            d.getProjectId(),
            d.getAssetId(),
            d.getSourceName(),
            d.getStatus().name(),
            d.getErrorMessage(),
            d.getDurationSec(),
            d.getWidth(),
            d.getHeight(),
            d.getFps(),
            d.getBitRate(),
            d.getShotCount(),
            d.getAvgShotDurationSec(),
            d.getCutsPerMinute(),
            d.getRhythmClass(),
            d.getHookEndSec(),
            d.getTranscriptStatus(),
            d.getCreatedAt(),
            d.getUpdatedAt()
        );
    }

    /**
     * 将VideoDe实体及分镜列表转换为详情DTO
     * @param d VideoDe实体
     * @param rows 分镜列表
     * @return DetailDTO
     */
    public DeconstructionDtos.DetailDto toDetail(VideoDeconstruction d, List<VideoDeconstructionShot> rows) {
        List<DeconstructionDtos.ShotDto> shotDtos = rows.stream().map(r ->
            new DeconstructionDtos.ShotDto(
                r.getId(),
                r.getShotNo(),
                r.getStartSec(),
                r.getEndSec(),
                r.getDurationSec(),
                r.getKeyframePath() != null ? 
                    "/api/projects/" + d.getProjectId() + "/deconstructions/" + d.getId() + 
                    "/shots/" + r.getShotNo() + "/keyframe" : null,
                r.getSegmentRole(),
                r.getDurationClass(),
                r.getDescription(),
                r.getShotSizeLabel(),
                r.getCameraMoveLabel(),
                r.getPromptGeneric(),
                r.getPromptSeedance(),
                r.getTranscriptText()
            )
        ).collect(Collectors.toList());

        return new DeconstructionDtos.DetailDto(
            d.getId(),
            d.getProjectId(),
            d.getAssetId(),
            d.getSourceName(),
            d.getStatus().name(),
            d.getErrorMessage(),
            d.getDurationSec(),
            d.getWidth(),
            d.getHeight(),
            d.getFps(),
            d.getBitRate(),
            d.getShotCount(),
            d.getAvgShotDurationSec(),
            d.getCutsPerMinute(),
            d.getRhythmClass(),
            d.getHookEndSec(),
            d.getCreatedAt(),
            d.getUpdatedAt(),
            d.getResultJson(),
            d.getTranscriptStatus(),
            d.getTranscriptTrackInfo(),
            toTranscriptDtos(d.getTranscriptJson()),
            shotDtos
        );
    }

    private List<DeconstructionDtos.TranscriptSegmentDto> toTranscriptDtos(String json) {
        if (json == null || json.isBlank()) {
            return List.of();
        }
        try {
            List<DeconstructionDtos.TranscriptSegmentDto> out = new ArrayList<>();
            for (JsonNode n : objectMapper.readTree(json)) {
                out.add(new DeconstructionDtos.TranscriptSegmentDto(
                    n.path("startSec").asDouble(),
                    n.path("endSec").asDouble(),
                    n.path("text").asText("")));
            }
            return out;
        } catch (JsonProcessingException e) {
            log.warn("逐字稿 JSON 解析失败", e);
            return List.of();
        }
    }

    private void submitProcess(Long id) {
        // 必须等创建事务提交后再启动后台流水线，否则工作线程按 id 查不到尚未提交的行，
        // 任务会永远停在 PENDING（本类创建方法均为 @Transactional）。
        if (org.springframework.transaction.support.TransactionSynchronizationManager.isSynchronizationActive()) {
            org.springframework.transaction.support.TransactionSynchronizationManager.registerSynchronization(
                    new org.springframework.transaction.support.TransactionSynchronization() {
                        @Override
                        public void afterCommit() {
                            executor.submit(() -> process(id));
                        }
                    });
        } else {
            executor.submit(() -> process(id));
        }
    }

    private void process(Long id) {
        try {
            runPipeline(id);
        } catch (Exception e) {
            log.error("视频拆解失败 id={}", id, e);
            deconstructionRepository.findById(id).ifPresent(r -> {
                r.setStatus(DeconstructionStatus.FAILED);
                String m = e.getMessage();
                r.setErrorMessage(m == null ? e.getClass().getSimpleName() : 
                    (m.length() > 1900 ? m.substring(0, 1900) : m));
                deconstructionRepository.save(r);
            });
        }
    }

    private void runPipeline(Long id) throws Exception {
        VideoDeconstruction row = deconstructionRepository.findById(id)
            .orElseThrow(() -> new ResourceNotFoundException("VideoDeconstruction", id));
        row.setStatus(DeconstructionStatus.RUNNING);
        deconstructionRepository.save(row);

        Path src = storageRoot().resolve(row.getSourcePath()).normalize();
        if (!src.startsWith(storageRoot()) || !Files.isRegularFile(src)) {
            throw new IllegalStateException("源视频文件不存在：" + row.getSourcePath());
        }

        DeconstructionAnalyzer.VideoMeta meta = probe(src);
        List<Double> cuts = detectScenes(src);
        DeconstructionAnalyzer.Analysis analysis = analyzer.analyze(meta, cuts, 
            new DeconstructionAnalyzer.Config(minShotSec, maxShots, fallbackSegmentSec));

        Path framesDir = storageRoot().resolve("deconstruction/" + id + "/frames");
        Files.createDirectories(framesDir);
        List<String> keyframePaths = new ArrayList<>();
        Map<Integer, DeconstructionVisionEnricher.Enrichment> enrichments = new HashMap<>();

        for (DeconstructionAnalyzer.AnalyzedShot analyzedShot : analysis.shots()) {
            int shotNo = analyzedShot.segment().shotNo();
            double mid = (analyzedShot.segment().startSec() + analyzedShot.segment().endSec()) / 2;
            Path out = framesDir.resolve(String.format(Locale.ROOT, "shot-%03d.jpg", shotNo));
            try {
                String[] cmd = {ffmpegService.getFfmpeg(), "-hide_banner", "-loglevel", "error", 
                    "-ss", String.format(Locale.ROOT, "%.3f", mid), 
                    "-i", src.toString(), 
                    "-frames:v", "1", "-q:v", "3", "-y", out.toString()};
                ffmpegService.executeCapture(List.of(cmd), 120);
                if (Files.isRegularFile(out)) {
                    String rel = "deconstruction/" + id + "/frames/" + out.getFileName();
                    keyframePaths.add(rel);
                    if (visionEnabled) {
                        visionEnricher.enrich(out, shotNo, analyzedShot.segment().startSec(), 
                            analyzedShot.segment().endSec()).ifPresent(enrich -> 
                            enrichments.put(shotNo, enrich));
                    }
                } else {
                    keyframePaths.add(null);
                }
            } catch (Exception e) {
                log.warn("抽关键帧失败 shotNo={}", shotNo, e);
                keyframePaths.add(null);
            }
        }

        Path transcriptDir = framesDir.getParent().resolve("transcript");
        SubtitleTranscriptService.TranscriptResult transcript = transcriptService.extract(src, transcriptDir);
        log.info("逐字稿提取 id={} found={} track={} segments={}", id, transcript.found(),
            transcript.trackInfo(), transcript.segments().size());

        String report = reportBuilder.buildReport(row.getSourceName(), analysis, keyframePaths, transcript);
        shotRowRepository.deleteByDeconstructionId(id);

        List<VideoDeconstructionShot> shotRows = new ArrayList<>();
        for (DeconstructionAnalyzer.AnalyzedShot analyzedShot : analysis.shots()) {
            int shotNo = analyzedShot.segment().shotNo();
            VideoDeconstructionShot s = new VideoDeconstructionShot();
            s.setDeconstructionId(id);
            s.setShotNo(shotNo);
            s.setStartSec(analyzedShot.segment().startSec());
            s.setEndSec(analyzedShot.segment().endSec());
            s.setDurationSec(analyzedShot.segment().duration());
            s.setKeyframePath(keyframePaths.get(shotNo - 1));
            s.setSegmentRole(analyzedShot.role());
            s.setDurationClass(analyzedShot.durationClass());
            s.setPromptGeneric(analyzedShot.genericPrompt());
            s.setPromptSeedance(analyzedShot.seedancePrompt());
            
            DeconstructionVisionEnricher.Enrichment enrich = enrichments.get(shotNo);
            if (enrich != null) {
                s.setDescription(enrich.description());
                s.setShotSizeLabel(enrich.shotSizeLabel());
                s.setCameraMoveLabel(enrich.cameraMoveLabel());
            }
            s.setTranscriptText(transcriptTextFor(analyzedShot.segment().startSec(),
                analyzedShot.segment().endSec(), transcript.segments()));
            shotRows.add(s);
        }
        shotRowRepository.saveAll(shotRows);

        row.setDurationSec(meta.durationSec());
        row.setWidth(meta.width());
        row.setHeight(meta.height());
        row.setFps(meta.fps());
        row.setBitRate(meta.bitRate());
        row.setShotCount(analysis.shots().size());
        row.setAvgShotDurationSec(analysis.avgShotDurationSec());
        row.setCutsPerMinute(analysis.cutsPerMinute());
        row.setRhythmClass(analysis.rhythmClass());
        row.setHookEndSec(analysis.hookEndSec());
        row.setResultJson(buildResultJson(analysis));
        row.setTranscriptStatus(transcript.found() ? "EMBEDDED" : "NONE");
        row.setTranscriptTrackInfo(transcript.trackInfo());
        row.setTranscriptJson(transcriptJsonOf(transcript.segments()));
        row.setReportMd(report);
        row.setStatus(DeconstructionStatus.DONE);
        row.setErrorMessage(null);
        deconstructionRepository.save(row);
    }

    private static String transcriptTextFor(double startSec, double endSec,
            List<SubtitleTranscriptService.TranscriptSegment> segments) {
        String joined = segments.stream()
            .filter(sg -> sg.startSec() < endSec && sg.endSec() > startSec)
            .map(SubtitleTranscriptService.TranscriptSegment::text)
            .collect(Collectors.joining("\n"));
        return joined.isEmpty() ? null : joined;
    }

    private String transcriptJsonOf(List<SubtitleTranscriptService.TranscriptSegment> segments) {
        try {
            List<Map<String, Object>> list = segments.stream().map(sg -> {
                Map<String, Object> m = new LinkedHashMap<>();
                m.put("startSec", sg.startSec());
                m.put("endSec", sg.endSec());
                m.put("text", sg.text());
                return m;
            }).collect(Collectors.toList());
            return objectMapper.writeValueAsString(list);
        } catch (JsonProcessingException e) {
            log.warn("逐字稿 JSON 序列化失败", e);
            return null;
        }
    }

    private String buildResultJson(DeconstructionAnalyzer.Analysis a) {
        LinkedHashMap<String, Object> map = new LinkedHashMap<>();
        map.put("ratioLabel", a.ratioLabel());
        LinkedHashMap<String, Object> metrics = new LinkedHashMap<>();
        metrics.put("avgShotDurationSec", a.avgShotDurationSec());
        metrics.put("cutsPerMinute", a.cutsPerMinute());
        metrics.put("rhythmClass", a.rhythmClass());
        metrics.put("hookEndSec", a.hookEndSec());
        metrics.put("shotCount", a.shots().size());
        map.put("metrics", metrics);
        
        List<Map<String, Object>> structure = a.structure().stream().map(s -> {
            Map<String, Object> seg = new LinkedHashMap<>();
            seg.put("kind", s.kind());
            seg.put("startSec", s.startSec());
            seg.put("endSec", s.endSec());
            seg.put("shotNos", s.shotNos());
            seg.put("note", s.note());
            return seg;
        }).collect(Collectors.toList());
        map.put("structure", structure);
        map.put("formula", a.formula());
        map.put("scriptTemplate", a.scriptTemplate());
        
        try {
            return objectMapper.writeValueAsString(map);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("序列化分析结果失败", e);
        }
    }

    private DeconstructionAnalyzer.VideoMeta probe(Path src) throws Exception {
        String[] cmd = {ffmpegService.getFfprobe(), "-v", "error", 
            "-select_streams", "v:0", 
            "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate",
            "-show_entries", "format=duration,bit_rate",
            "-of", "json", src.toString()};
        String out = ffmpegService.executeCapture(List.of(cmd), 60);
        
        JsonNode root = objectMapper.readTree(out);
        JsonNode streams = root.get("streams");
        if (streams == null || streams.size() == 0) {
            throw new IllegalStateException("无法读取视频流信息");
        }
        JsonNode stream = streams.get(0);
        
        Integer width = stream.has("width") ? stream.get("width").asInt() : null;
        Integer height = stream.has("height") ? stream.get("height").asInt() : null;
        
        Double fps = null;
        String avgFrameRate = stream.get("avg_frame_rate").asText();
        String[] avgParts = avgFrameRate.split("/");
        if (avgParts.length == 2) {
            try {
                double num = Double.parseDouble(avgParts[0]);
                double den = Double.parseDouble(avgParts[1]);
                if (den != 0) {
                    fps = Math.round((num/den)*1000)/1000.0;
                }
            } catch (NumberFormatException ignored) {}
        }
        if (fps == null) {
            String rFrameRate = stream.get("r_frame_rate").asText();
            String[] rParts = rFrameRate.split("/");
            if (rParts.length == 2) {
                try {
                    double num = Double.parseDouble(rParts[0]);
                    double den = Double.parseDouble(rParts[1]);
                    if (den != 0) {
                        fps = Math.round((num/den)*1000)/1000.0;
                    }
                } catch (NumberFormatException ignored) {}
            }
        }
        
        JsonNode format = root.get("format");
        if (format == null || !format.has("duration")) {
            throw new IllegalStateException("无法读取视频时长");
        }
        double duration = format.get("duration").asDouble();
        
        Long bitRate = null;
        if (format.has("bit_rate")) {
            String bitRateStr = format.get("bit_rate").asText();
            if (!"N/A".equals(bitRateStr)) {
                try {
                    bitRate = Long.parseLong(bitRateStr);
                } catch (NumberFormatException ignored) {}
            }
        }
        
        return new DeconstructionAnalyzer.VideoMeta(duration, width, height, fps, bitRate);
    }

    private List<Double> detectScenes(Path src) {
        try {
            String thresholdStr = Double.toString(sceneThreshold);
            String[] cmd = {ffmpegService.getFfmpeg(), "-hide_banner", 
                "-i", src.toString(),
                "-filter:v", "select='gt(scene," + thresholdStr + ")',metadata=print",
                "-f", "null", "-"};
            String out = ffmpegService.executeCapture(List.of(cmd), 900);
            
            List<Double> cuts = new ArrayList<>();
            Matcher m = PTS_TIME.matcher(out);
            while (m.find()) {
                cuts.add(Double.parseDouble(m.group(1)));
            }
            return cuts;
        } catch (Exception e) {
            log.warn("场景检测失败，使用回退采样: {}", e.getMessage());
            return Collections.emptyList();
        }
    }

    private Path storageRoot() {
        return Paths.get(storageDir).toAbsolutePath().normalize();
    }

    private DramaProject requireProject(Long projectId) {
        return projectRepository.findById(projectId)
            .orElseThrow(() -> new ResourceNotFoundException("Project", projectId));
    }

    private static String fmt(double v) {
        return String.format(Locale.ROOT, "%.1f", v);
    }
}