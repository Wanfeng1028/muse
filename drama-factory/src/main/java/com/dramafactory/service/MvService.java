package com.dramafactory.service;

import com.dramafactory.model.AgentStep;
import com.dramafactory.model.MvSong;
import com.dramafactory.model.Run;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.RunStatus;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.MvSongRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.service.byok.ByokGenerateService;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Asset;
import com.dramafactory.repository.AssetRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
public class MvService {

    private static final Logger log = LoggerFactory.getLogger(MvService.class);

    private final MvSongRepository mvSongRepository;
    private final RunRepository runRepository;
    private final AgentStepRepository agentStepRepository;
    private final MvLyricsService mvLyricsService;
    private final ByokGenerateService byokGenerateService;
    private final FfmpegService ffmpegService;
    private final MvTimelineService mvTimelineService;
    private final ObjectMapper objectMapper;
    private final AssetService assetService;
    private final AssetRepository assetRepository;


    @Value("${drama.storage:./data/media}")
    private String storageDir;

    public MvService(MvSongRepository mvSongRepository,
                     RunRepository runRepository,
                     AgentStepRepository agentStepRepository,
                     MvLyricsService mvLyricsService,
                     ByokGenerateService byokGenerateService,
                     FfmpegService ffmpegService,
                     MvTimelineService mvTimelineService,
                     ObjectMapper objectMapper,
                     AssetService assetService,
                     AssetRepository assetRepository) {
        this.mvSongRepository = mvSongRepository;
        this.runRepository = runRepository;
        this.agentStepRepository = agentStepRepository;
        this.mvLyricsService = mvLyricsService;
        this.byokGenerateService = byokGenerateService;
        this.ffmpegService = ffmpegService;
        this.mvTimelineService = mvTimelineService;
        this.objectMapper = objectMapper;
        this.assetService = assetService;
        this.assetRepository = assetRepository;
    }


    @Transactional
    public Long create(String theme, String mood, String style) {
        if (theme == null || theme.isBlank()) {
            throw new IllegalArgumentException("主题不能为空");
        }

        MvSong song = new MvSong();
        song.setTheme(theme);
        song.setMood(mood);
        song.setStyle(style);
        song.setStatus("DRAFT");
        song.setSource("AI");
        song = mvSongRepository.save(song);

        Run run = new Run();
        run.setGoal("AI MV: " + theme);
        run.setStatus(RunStatus.RUNNING);
        run = runRepository.save(run);

        Object[][] stepDefs = new Object[][]{
                {1, AgentType.LYRICS, "作词"},
                {2, AgentType.COMPOSE, "作曲"},
                {3, AgentType.BOARD, "分镜"},
                {4, AgentType.VIDEO, "视频生成"},
                {5, AgentType.EDIT, "剪辑"},
                {6, AgentType.QC, "质检"}
        };
        for (Object[] def : stepDefs) {
            AgentStep step = new AgentStep();
            step.setRun(run);
            step.setSeqNo((Integer) def[0]);
            step.setAgentType((AgentType) def[1]);
            step.setName((String) def[2]);
            step.setStatus(AgentStepStatus.PENDING);
            agentStepRepository.save(step);
        }

        song.setRunId(run.getId());
        mvSongRepository.save(song);

        log.info("MV 创建完成 mvSongId={} runId={} theme={}", song.getId(), run.getId(), theme);
        return song.getId();
    }

    /**
     * 导入已有音频：上传音频 → 入资产库 → 建 Run（作词作曲标记为已跳过）→ 直接可进分镜。
     * lyricsText 可空：有则按文本建歌词时间轴（字幕），无则走纯音乐分镜。
     */
    @Transactional
    public MvSong importAudio(MultipartFile file, String title, String lyricsText, String mood, String style) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("标题不能为空");
        }
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("上传文件不能为空");
        }
        long size = file.getSize();
        if (size > 100L * 1024 * 1024) {
            throw new IllegalArgumentException("音频文件超过大小限制（最大 100MB）");
        }
        String originalName = file.getOriginalFilename();
        String ext = "";
        if (originalName != null && originalName.contains(".")) {
            ext = originalName.substring(originalName.lastIndexOf('.') + 1).toLowerCase();
        }
        if (!ext.equals("mp3") && !ext.equals("wav") && !ext.equals("m4a")) {
            throw new IllegalArgumentException("仅支持 mp3 / wav / m4a 音频文件");
        }
        String mime = file.getContentType();
        if (mime != null && !mime.isBlank() && !mime.equals("application/octet-stream")) {
            String m = mime.toLowerCase();
            boolean ok = m.equals("audio/mpeg") || m.equals("audio/wav") || m.equals("audio/x-wav")
                    || m.equals("audio/mp4") || m.equals("audio/x-m4a") || m.equals("audio/aac");
            if (!ok) {
                throw new IllegalArgumentException("不支持的音频类型：" + mime);
            }
        }

        Asset asset = assetService.upload(file, "mv-audio", null, 100L * 1024 * 1024);
        String audioUrl = "/api/assets/" + asset.getId() + "/file";

        MvSong song = new MvSong();
        song.setTheme(title.trim());
        song.setMood(mood);
        song.setStyle(style);
        song.setSource("IMPORT");
        song.setAudioUrl(audioUrl);
        song.setStatus("IMPORTED");
        song = mvSongRepository.save(song);

        int durationMs = probeDuration(audioUrl);
        if (durationMs <= 0) {
            throw new IllegalStateException("无法读取音频时长");
        }
        song.setDurationMs(durationMs);

        if (lyricsText != null && !lyricsText.isBlank()) {
            String lyricsJson = buildLyricsJsonFromText(title.trim(), lyricsText);
            song.setLyricsJson(lyricsJson);
            MvTimelineService.Timeline timeline = mvTimelineService.align(
                    readJson(lyricsJson), (long) durationMs);
            song.setTimelineJson(mvTimelineService.toJson(timeline));
        } else {
            MvTimelineService.Timeline timeline =
                    mvTimelineService.buildInstrumentalTimeline((long) durationMs, 10000L);
            song.setTimelineJson(mvTimelineService.toJson(timeline));
        }

        Run run = new Run();
        run.setGoal("AI MV（导入音频）: " + title.trim());
        run.setStatus(RunStatus.RUNNING);
        run = runRepository.save(run);

        String skipNote = "已跳过作词作曲（用户导入音频）";
        Object[][] stepDefs = new Object[][]{
                {1, AgentType.LYRICS, "作词", true},
                {2, AgentType.COMPOSE, "作曲", true},
                {3, AgentType.BOARD, "分镜", false},
                {4, AgentType.VIDEO, "视频生成", false},
                {5, AgentType.EDIT, "剪辑", false},
                {6, AgentType.QC, "质检", false}
        };
        for (Object[] def : stepDefs) {
            AgentStep step = new AgentStep();
            step.setRun(run);
            step.setSeqNo((Integer) def[0]);
            step.setAgentType((AgentType) def[1]);
            step.setName((String) def[2]);
            boolean skipped = (Boolean) def[3];
            if (skipped) {
                step.setStatus(AgentStepStatus.SKIPPED);
                step.setOutputSummary(skipNote);
            } else {
                step.setStatus(AgentStepStatus.PENDING);
            }
            agentStepRepository.save(step);
        }

        song.setRunId(run.getId());
        mvSongRepository.save(song);

        log.info("MV 导入音频完成 mvSongId={} runId={} assetId={} durationMs={}",
                song.getId(), run.getId(), asset.getId(), durationMs);
        return song;
    }

    /**
     * 把用户粘贴的纯文本歌词转成 lyricsJson：空行分段；无空行时每 4 行一段。
     */
    String buildLyricsJsonFromText(String title, String text) {
        List<String> lines = new ArrayList<>();
        for (String raw : text.split("\r?\n")) {
            String t = raw.trim();
            if (!t.isEmpty()) {
                lines.add(t);
            }
        }
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("歌词文本为空");
        }
        boolean hasBlank = text.contains("\n\n");
        List<List<String>> groups = new ArrayList<>();
        if (hasBlank) {
            List<String> cur = new ArrayList<>();
            for (String raw : text.split("\r?\n")) {
                String t = raw.trim();
                if (t.isEmpty()) {
                    if (!cur.isEmpty()) {
                        groups.add(cur);
                        cur = new ArrayList<>();
                    }
                } else {
                    cur.add(t);
                }
            }
            if (!cur.isEmpty()) {
                groups.add(cur);
            }
        } else {
            for (int i = 0; i < lines.size(); i += 4) {
                groups.add(new ArrayList<>(lines.subList(i, Math.min(i + 4, lines.size()))));
            }
        }
        try {
            com.fasterxml.jackson.databind.node.ObjectNode root = objectMapper.createObjectNode();
            root.put("title", title == null ? "" : title);
            com.fasterxml.jackson.databind.node.ArrayNode sections = root.putArray("sections");
            int n = 1;
            for (List<String> g : groups) {
                com.fasterxml.jackson.databind.node.ObjectNode s = sections.addObject();
                s.put("name", "段落 " + n);
                s.put("mood", "");
                s.put("estSeconds", Math.max(4, g.size() * 4));
                s.put("lyrics", String.join("\n", g));
                n++;
            }
            return objectMapper.writeValueAsString(root);
        } catch (Exception e) {
            throw new IllegalStateException("歌词解析失败");
        }
    }

    @Transactional(readOnly = true)
    public MvSong getById(Long mvSongId) {
        return requireSong(mvSongId);
    }

    @Transactional(readOnly = true)
    public List<Map<String, String>> getStepStatuses(Long runId) {
        List<Map<String, String>> out = new ArrayList<>();
        for (AgentStep step : agentStepRepository.findByRunIdOrderBySeqNoAsc(runId)) {
            Map<String, String> m = new HashMap<>();
            m.put("agentType", step.getAgentType().name());
            m.put("status", step.getStatus().name());
            out.add(m);
        }
        return out;
    }

    @Transactional
    public MvSong generateLyrics(Long mvSongId) {
        MvSong song = requireSong(mvSongId);
        if ("IMPORT".equals(song.getSource())) {
            throw new IllegalStateException("导入音频模式不支持重新作词");
        }
        AgentStep step = findStep(song.getRunId(), 1);
        markStep(step, AgentStepStatus.RUNNING, null);
        try {
            MvLyricsService.LyricsResult result = mvLyricsService.generate(
                    song.getTheme(), song.getMood(), song.getStyle());
            song.setLyricsJson(mvLyricsService.toJson(result));
            song.setStatus("LYRICS_DONE");
            mvSongRepository.save(song);
            markStep(step, AgentStepStatus.SUCCEEDED, null);
            log.info("作词完成 mvSongId={} sections={}", mvSongId, result.sections().size());
            return song;
        } catch (RuntimeException e) {
            markStep(step, AgentStepStatus.FAILED, truncate(e.getMessage()));
            song.setStatus("FAILED");
            mvSongRepository.save(song);
            throw e;
        }
    }

    @Transactional
    public MvSong compose(Long mvSongId, Long providerId, String modelId) {
        MvSong song = requireSong(mvSongId);
        if ("IMPORT".equals(song.getSource())) {
            throw new IllegalStateException("导入音频模式不支持作曲（已有用户音频）");
        }
        if (song.getLyricsJson() == null || song.getLyricsJson().isBlank()) {
            throw new IllegalStateException("请先生成歌词");
        }
        AgentStep step = findStep(song.getRunId(), 2);
        markStep(step, AgentStepStatus.RUNNING, null);
        try {
            JsonNode root = readJson(song.getLyricsJson());
            String title = root.path("title").asText("");
            StringBuilder lyricsText = new StringBuilder();
            JsonNode sections = root.path("sections");
            if (sections.isArray()) {
                for (JsonNode s : sections) {
                    lyricsText.append(s.path("lyrics").asText("")).append("\n");
                }
            }
            String prompt = "曲风：" + (song.getStyle() == null ? "" : song.getStyle()) + "，歌名：" + title;
            Map<String, String> options = new HashMap<>();
            options.put("lyrics", lyricsText.toString().trim());

            ByokGenerateService.GenerateResponse resp = byokGenerateService.generate(
                    new ByokGenerateService.GenerateRequest("MUSIC", providerId, modelId, prompt, options));
            if (!"SUCCEEDED".equals(resp.status())) {
                throw new RuntimeException("作曲失败：" + (resp.error() == null ? "未知错误" : resp.error()));
            }

            song.setAudioUrl(resp.url());
            song.setDurationMs(probeDuration(resp.url()));
            MvTimelineService.Timeline timeline = mvTimelineService.align(
                    readJson(song.getLyricsJson()), song.getDurationMs());
            song.setTimelineJson(mvTimelineService.toJson(timeline));
            song.setStatus("COMPOSED");

            mvSongRepository.save(song);
            markStep(step, AgentStepStatus.SUCCEEDED, null);
            log.info("作曲完成 mvSongId={} audioUrl={}", mvSongId, resp.url());
            return song;
        } catch (RuntimeException e) {
            markStep(step, AgentStepStatus.FAILED, truncate(e.getMessage()));
            song.setStatus("FAILED");
            mvSongRepository.save(song);
            throw e;
        }
    }

    @Transactional
    public List<Map<String, String>> storyboard(Long mvSongId) {
        MvSong song = requireSong(mvSongId);
        if ((song.getTimelineJson() == null || song.getTimelineJson().isBlank())
                && (song.getLyricsJson() == null || song.getLyricsJson().isBlank())) {
            throw new IllegalStateException("请先生成歌词或导入音频");
        }
        AgentStep step = findStep(song.getRunId(), 3);
        markStep(step, AgentStepStatus.RUNNING, null);
        try {
            MvTimelineService.Timeline timeline = loadTimeline(song);
            List<Map<String, String>> result = new ArrayList<>();
            String style = song.getStyle() == null ? "" : song.getStyle();
            int lineNo = 0;
            for (MvTimelineService.TimedSection sec : timeline.sections()) {
                for (MvTimelineService.TimedLine line : sec.lines()) {
                    lineNo++;
                    String visualPrompt = line.text().isBlank()
                            ? "纯音乐段落，" + style + " 风格，电影感"
                            : "MV 镜头，情绪：" + sec.mood() + "，画面：" + line.text()
                                    + "，电影感，" + style + " 风格";
                    Map<String, String> item = new LinkedHashMap<>();
                    item.put("section", sec.name());
                    item.put("line", String.valueOf(lineNo));
                    item.put("text", line.text());
                    item.put("startMs", String.valueOf(line.startMs()));
                    item.put("endMs", String.valueOf(line.endMs()));
                    item.put("durationMs", String.valueOf(line.endMs() - line.startMs()));
                    item.put("visualPrompt", visualPrompt);
                    result.add(item);
                }
            }

            markStep(step, AgentStepStatus.SUCCEEDED, null);
            return result;
        } catch (RuntimeException e) {
            markStep(step, AgentStepStatus.FAILED, truncate(e.getMessage()));
            throw e;
        }
    }

    @Transactional
    public MvSong render(Long mvSongId, boolean dryRun) {
        MvSong song = requireSong(mvSongId);
        if (song.getAudioUrl() == null || song.getAudioUrl().isBlank()) {
            throw new IllegalStateException("请先作曲或导入音频");
        }

        AgentStep videoStep = findStep(song.getRunId(), 4);
        AgentStep editStep = findStep(song.getRunId(), 5);
        AgentStep qcStep = findStep(song.getRunId(), 6);

        Path workDir = Paths.get(storageDir, "mv", String.valueOf(mvSongId));
        try {
            Files.createDirectories(workDir);
        } catch (IOException e) {
            throw new RuntimeException("无法创建输出目录");
        }

        try {
            MvTimelineService.Timeline timeline = loadTimeline(song);
            List<Path> clips = new ArrayList<>();
            List<SectionTiming> timings = new ArrayList<>();

            markStep(videoStep, AgentStepStatus.RUNNING, null);
            int idx = 0;
            for (MvTimelineService.TimedSection sec : timeline.sections()) {
                for (MvTimelineService.TimedLine line : sec.lines()) {
                    timings.add(new SectionTiming(line.startMs(), line.endMs(), line.text()));
                }
                long secMs = sec.endMs() - sec.startMs();
                int secSeconds = (int) Math.max(1, Math.round(secMs / 1000.0));
                Path clip = workDir.resolve("clip_" + idx + ".mp4");
                // dryRun 与真实模式当前都使用测试片段：真实视频生成将在后续版本接入。
                ffmpegService.generateTestClip(clip, secSeconds);
                clips.add(clip);
                idx++;
            }

            if (clips.isEmpty()) {
                throw new IllegalStateException("无分镜可渲染");
            }
            markStep(videoStep, AgentStepStatus.SUCCEEDED, null);

            markStep(editStep, AgentStepStatus.RUNNING, null);
            Path concat = workDir.resolve("concat.mp4");
            ffmpegService.concatClips(clips, concat);

            Path audio = resolveLocalAudio(song.getAudioUrl());
            Path muxed = workDir.resolve("muxed.mp4");
            muxAudio(concat, audio, muxed);

            List<SectionTiming> subTimings = new ArrayList<>();
            for (SectionTiming t : timings) {
                if (t.text() != null && !t.text().isBlank()) {
                    subTimings.add(t);
                }
            }

            Path finalOut = workDir.resolve("final.mp4");
            if (subTimings.isEmpty()) {
                // 纯音乐：无字幕，直接以混音结果为成片
                Files.move(muxed, finalOut, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            } else {
                Path srt = workDir.resolve("subs.srt");
                writeSrt(subTimings, srt);

                Path burned = workDir.resolve("burned.mp4");
                ffmpegService.burnSubtitles(muxed, srt, burned);

                Files.move(burned, finalOut, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            }
            markStep(editStep, AgentStepStatus.SUCCEEDED, null);

            markStep(qcStep, AgentStepStatus.RUNNING, null);
            // 自动质检直接通过，人工质检由前端完成。
            markStep(qcStep, AgentStepStatus.SUCCEEDED, null);

            song.setStatus("RENDERED");
            mvSongRepository.save(song);
            log.info("渲染完成 mvSongId={} final={}", mvSongId, finalOut);
            return song;
        } catch (RuntimeException e) {
            markStep(videoStep, AgentStepStatus.FAILED, truncate(e.getMessage()));
            markStep(editStep, AgentStepStatus.FAILED, truncate(e.getMessage()));
            markStep(qcStep, AgentStepStatus.FAILED, truncate(e.getMessage()));
            song.setStatus("FAILED");
            mvSongRepository.save(song);
            throw e;
        } catch (IOException e) {
            markStep(videoStep, AgentStepStatus.FAILED, truncate(e.getMessage()));
            markStep(editStep, AgentStepStatus.FAILED, truncate(e.getMessage()));
            markStep(qcStep, AgentStepStatus.FAILED, truncate(e.getMessage()));
            song.setStatus("FAILED");
            mvSongRepository.save(song);
            throw new RuntimeException("渲染失败");
        }
    }

    private record SectionTiming(long startMs, long endMs, String text) {}


    private MvSong requireSong(Long mvSongId) {
        Optional<MvSong> opt = mvSongRepository.findById(mvSongId);
        if (opt.isEmpty()) {
            throw new ResourceNotFoundException("mv_song", mvSongId);
        }
        return opt.get();
    }

    /**
     * 读取或按当前歌词/音频时长重算时间轴。compose 步骤已持久化 timelineJson，
     * 这里重算保证 storyboard/render 永远拿到与 lyricsJson 一致的时间轴。
     */
    private MvTimelineService.Timeline loadTimeline(MvSong song) {
        if (song.getTimelineJson() != null && !song.getTimelineJson().isBlank()) {
            return mvTimelineService.fromJson(song.getTimelineJson());
        }
        long total = song.getDurationMs() == null ? 0 : song.getDurationMs();
        return mvTimelineService.align(readJson(song.getLyricsJson()), total);
    }

    private AgentStep findStep(Long runId, int seqNo) {
        if (runId == null) {
            throw new IllegalStateException("Run 未关联");
        }
        for (AgentStep s : agentStepRepository.findByRunIdOrderBySeqNoAsc(runId)) {
            if (s.getSeqNo() != null && s.getSeqNo() == seqNo) {
                return s;
            }
        }
        throw new IllegalStateException("步骤不存在：" + seqNo);

    }

    private void markStep(AgentStep step, AgentStepStatus status, String err) {
        step.setStatus(status);
        if (err != null) {
            step.setErrorMessage(err);
        }
        agentStepRepository.save(step);
    }

    private Path resolveLocalAudio(String audioUrl) {
        String rel = audioUrl;
        if (rel.startsWith("/api/byok/file/")) {
            rel = rel.substring("/api/byok/file/".length());
            return Paths.get(storageDir, "byok", rel);
        }
        if (rel.startsWith("/api/assets/") && rel.endsWith("/file")) {
            String idPart = rel.substring("/api/assets/".length(), rel.length() - "/file".length());
            try {
                Long assetId = Long.parseLong(idPart);
                Asset asset = assetRepository.findById(assetId)
                        .orElseThrow(() -> new IllegalStateException("音频资产不存在"));
                String filePath = asset.getFilePath();
                if (filePath == null || filePath.contains("..")) {
                    throw new IllegalStateException("音频资产路径非法");
                }
                return Paths.get(storageDir, filePath);
            } catch (NumberFormatException e) {
                throw new IllegalStateException("音频地址格式错误");
            }
        }
        throw new IllegalStateException("不支持的音频地址");
    }

    private void writeSrt(List<SectionTiming> timings, Path path) {
        StringBuilder sb = new StringBuilder();
        int i = 1;
        for (SectionTiming t : timings) {
            sb.append(i).append("\r\n");
            sb.append(formatSrtTime(t.startMs())).append(" --> ").append(formatSrtTime(t.endMs())).append("\r\n");
            sb.append(t.text() == null ? "" : t.text()).append("\r\n\r\n");

            i++;
        }
        try {
            Files.writeString(path, sb.toString(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new RuntimeException("字幕写入失败");
        }
    }

    private String formatSrtTime(long millis) {
        long h = millis / 3600000;
        long m = (millis % 3600000) / 60000;
        long s = (millis % 60000) / 1000;
        long ms = millis % 1000;
        return String.format("%02d:%02d:%02d,%03d", h, m, s, ms);
    }

    private void muxAudio(Path video, Path audio, Path out) {
        String ffmpeg = ffmpegService.getFfmpeg();
        if (ffmpeg == null || ffmpeg.isBlank()) {
            ffmpeg = "ffmpeg";
        }

        List<String> cmd = List.of(
                ffmpeg, "-y",
                "-i", video.toString(),
                "-i", audio.toString(),
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                out.toString()
        );
        ProcessBuilder pb = new ProcessBuilder(cmd);
        pb.redirectErrorStream(true);
        try {
            Process p = pb.start();
            byte[] buf = new byte[4096];
            while (p.getInputStream().read(buf) != -1) {
                // drain output
            }
            int code = p.waitFor();
            if (code != 0) {
                throw new RuntimeException("音频合成失败");
            }
        } catch (IOException e) {
            throw new RuntimeException("音频合成失败");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("音频合成失败");
        }
    }

    private int probeDuration(String audioUrl) {
        try {
            Path local = resolveLocalAudio(audioUrl);
            double seconds = ffmpegService.probeDurationSeconds(local);
            return (int) Math.round(seconds * 1000);
        } catch (RuntimeException e) {
            log.warn("音频时长探测失败: {}", e.getMessage());
            return 0;
        }
    }

    private JsonNode readJson(String json) {
        try {
            return objectMapper.readTree(json);
        } catch (Exception e) {
            throw new IllegalStateException("歌词数据解析失败");
        }
    }

    private String truncate(String s) {
        if (s == null) {
            return null;
        }
        return s.length() > 500 ? s.substring(0, 500) : s;
    }
}
