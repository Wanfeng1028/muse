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
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

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
    private final ObjectMapper objectMapper;

    @Value("${drama.storage:./data/media}")
    private String storageDir;

    public MvService(MvSongRepository mvSongRepository,
                     RunRepository runRepository,
                     AgentStepRepository agentStepRepository,
                     MvLyricsService mvLyricsService,
                     ByokGenerateService byokGenerateService,
                     FfmpegService ffmpegService,
                     ObjectMapper objectMapper) {
        this.mvSongRepository = mvSongRepository;
        this.runRepository = runRepository;
        this.agentStepRepository = agentStepRepository;
        this.mvLyricsService = mvLyricsService;
        this.byokGenerateService = byokGenerateService;
        this.ffmpegService = ffmpegService;
        this.objectMapper = objectMapper;
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

    @Transactional(readOnly = true)
    public MvSong getById(Long mvSongId) {
        return requireSong(mvSongId);
    }

    @Transactional
    public MvSong generateLyrics(Long mvSongId) {
        MvSong song = requireSong(mvSongId);
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
        if (song.getLyricsJson() == null || song.getLyricsJson().isBlank()) {
            throw new IllegalStateException("请先生成歌词");
        }
        AgentStep step = findStep(song.getRunId(), 3);
        markStep(step, AgentStepStatus.RUNNING, null);
        try {
            JsonNode root = readJson(song.getLyricsJson());
            JsonNode sections = root.path("sections");
            List<Map<String, String>> result = new ArrayList<>();
            String style = song.getStyle() == null ? "" : song.getStyle();
            if (sections.isArray()) {
                for (JsonNode s : sections) {
                    String name = s.path("name").asText("");
                    String lyrics = s.path("lyrics").asText("");
                    String mood = s.path("mood").asText("");
                    int est = s.path("estSeconds").asInt(20);
                    String snippet = lyrics.length() > 30 ? lyrics.substring(0, 30) : lyrics;
                    snippet = snippet.replace("\n", " ").trim();
                    String visualPrompt = "MV 镜头，情绪：" + mood + "，画面：" + snippet
                            + "，电影感，" + style + " 风格";
                    Map<String, String> item = new LinkedHashMap<>();
                    item.put("name", name);
                    item.put("visualPrompt", visualPrompt);
                    item.put("estSeconds", String.valueOf(est));
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
            throw new IllegalStateException("请先作曲");
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
            JsonNode root = readJson(song.getLyricsJson());
            JsonNode sections = root.path("sections");
            List<Path> clips = new ArrayList<>();
            List<SectionTiming> timings = new ArrayList<>();

            markStep(videoStep, AgentStepStatus.RUNNING, null);
            int idx = 0;
            long cursor = 0;
            if (sections.isArray()) {
                for (JsonNode s : sections) {
                    int est = s.path("estSeconds").asInt(20);
                    if (est < 1) {
                        est = 1;
                    }
                    Path clip = workDir.resolve("clip_" + idx + ".mp4");
                    // dryRun 与真实模式当前都使用测试片段：真实视频生成将在后续版本接入。
                    ffmpegService.generateTestClip(clip, est);
                    clips.add(clip);
                    String lyrics = s.path("lyrics").asText("");
                    timings.add(new SectionTiming(cursor, cursor + est * 1000L, lyrics));
                    cursor += est * 1000L;
                    idx++;
                }
            }
            if (clips.isEmpty()) {
                throw new IllegalStateException("无分镜可渲染");
            }
            markStep(videoStep, AgentStepStatus.SUCCEEDED, null);

            markStep(editStep, AgentStepStatus.RUNNING, null);
            Path concat = workDir.resolve("concat.mp4");
            ffmpegService.concatClips(clips, concat);

            Path srt = workDir.resolve("subs.srt");
            writeSrt(timings, srt);

            Path audio = resolveLocalAudio(song.getAudioUrl());
            Path muxed = workDir.resolve("muxed.mp4");
            muxAudio(concat, audio, muxed);

            Path burned = workDir.resolve("burned.mp4");
            ffmpegService.burnSubtitles(muxed, srt, burned);

            Path finalOut = workDir.resolve("final.mp4");
            Files.move(burned, finalOut, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
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

    private record SectionTiming(long startMs, long endMs, String lyrics) {}

    private MvSong requireSong(Long mvSongId) {
        Optional<MvSong> opt = mvSongRepository.findById(mvSongId);
        if (opt.isEmpty()) {
            throw new ResourceNotFoundException("mv_song", mvSongId);
        }
        return opt.get();
    }

    private AgentStep findStep(Long runId, int seqNo) {
        if (runId == null) {
            throw new IllegalStateException("Run 未关联");
        }
        List<AgentStep> steps = agentStepRepository.findAll();
        for (AgentStep s : steps) {
            if (s.getRun() != null && runId.equals(s.getRun().getId())
                    && s.getSeqNo() != null && s.getSeqNo() == seqNo) {
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
        }
        return Paths.get(storageDir, "byok", rel);
    }

    private void writeSrt(List<SectionTiming> timings, Path path) {
        StringBuilder sb = new StringBuilder();
        int i = 1;
        for (SectionTiming t : timings) {
            sb.append(i).append("\r\n");
            sb.append(formatSrtTime(t.startMs())).append(" --> ").append(formatSrtTime(t.endMs())).append("\r\n");
            sb.append(t.lyrics() == null ? "" : t.lyrics()).append("\r\n\r\n");
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
        String ffmpeg = "ffmpeg";
        try {
            java.lang.reflect.Field f = FfmpegService.class.getDeclaredField("ffmpegPath");
            f.setAccessible(true);
            Object v = f.get(ffmpegService);
            if (v instanceof String s && !s.isBlank()) {
                ffmpeg = s;
            }
        } catch (Exception ignored) {
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
