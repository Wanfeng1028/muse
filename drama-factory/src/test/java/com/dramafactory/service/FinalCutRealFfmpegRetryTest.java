package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.Episode;
import com.dramafactory.model.FinalCutStatus;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.video.VideoProvider;
import com.dramafactory.service.video.VideoProviderRouter;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.Mockito;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * v2.29 flaky 根因歼灭——真实 ffmpeg 回归测试。
 *
 * <p>本测试用 {@link Mockito#spy(Object)} 包裹真实的 {@link FfmpegService}，注入一次瞬时失败
 * （模拟 flaky 模式 A：final-cuts 偶发 500 的抖动），随后回落到真实 ffmpeg 调用，断言成片
 * 构建经重试后最终达到 {@link FinalCutStatus#READY}，并验证成片文件在磁盘上真实存在。
 *
 * <p>证据链：一次抖动 → 重试 → 成功，全程由真实 ffmpeg 参与，非纯 mock 演练。
 *
 * <p>依赖：本机 ffmpeg / ffprobe 可用（真实调用）。
 */
class FinalCutRealFfmpegRetryTest {

    @TempDir
    Path tempDir;

    private FfmpegService realFfmpeg;
    private FfmpegService spyFfmpeg;
    private FinalCutRepository finalCutRepository;
    private EpisodeRepository episodeRepository;
    private ShotRepository shotRepository;
    private VideoTaskRepository videoTaskRepository;
    private SubtitleService subtitleService;
    private EpisodeStatusFlowService episodeStatusFlowService;
    private DramaMetrics dramaMetrics;
    private FinalCutService service;

    @BeforeEach
    void setUp() {
        realFfmpeg = new FfmpegService("ffmpeg", "ffprobe");
        spyFfmpeg = Mockito.spy(realFfmpeg);
        finalCutRepository = mock(FinalCutRepository.class);
        episodeRepository = mock(EpisodeRepository.class);
        shotRepository = mock(ShotRepository.class);
        videoTaskRepository = mock(VideoTaskRepository.class);
        subtitleService = mock(SubtitleService.class);
        episodeStatusFlowService = mock(EpisodeStatusFlowService.class);
        dramaMetrics = mock(DramaMetrics.class);
        service = new FinalCutService(finalCutRepository, episodeRepository, shotRepository,
                videoTaskRepository, subtitleService, spyFfmpeg, episodeStatusFlowService,
                tempDir.toString(), dramaMetrics, 3, 2000L);
        when(finalCutRepository.save(any())).thenAnswer(inv -> inv.getArgument(0));
    }

    @Test
    @Timeout(value = 180, unit = TimeUnit.SECONDS)
    void transientConcatFailureRecoveredByRetry() throws Exception {
        Episode episode = new Episode();
        episode.setId(7L);
        episode.setEpisodeNo(3);
        when(episodeRepository.findById(7L)).thenReturn(Optional.of(episode));

        Shot shot = new Shot();
        shot.setId(11L);
        shot.setShotNo(1);
        shot.setEpisode(episode);
        shot.setDurationSeconds(5);
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(7L)).thenReturn(List.of(shot));

        Path clip = tempDir.resolve("clip.mp4");
        realFfmpeg.generateTestClip(clip, 2);

        VideoTask task = new VideoTask();
        task.setId(21L);
        task.setShot(shot);
        task.setStatus(VideoTaskStatus.DONE);
        task.setLocalPath(clip.toString());
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(11L)).thenReturn(Optional.of(task));

        when(subtitleService.buildSrt(eq(7L), anyList())).thenAnswer(inv -> {
            Path srt = tempDir.resolve("subs.srt");
            String content = "1\n"
                    + "00:00:00,000 --> 00:00:01,000\n"
                    + "你好\n"
                    + "\n";
            Files.writeString(srt, content, StandardCharsets.UTF_8);
            return srt;
        });

        doThrow(new FfmpegService.FfmpegException("命令超时(600s): ffmpeg", true))
                .doCallRealMethod()
                .when(spyFfmpeg).concatClips(anyList(), any(Path.class));

        Records.FinalCutResponse resp = service.buildFinalCut(7L);

        assertEquals(FinalCutStatus.READY, resp.status());
        verify(spyFfmpeg, times(2)).concatClips(anyList(), any(Path.class));
        assertTrue(resp.filePath() != null && Files.exists(Paths.get(resp.filePath())),
                "成片文件应真实存在");
        verify(dramaMetrics, times(1)).recordFfmpegRetry(eq("concat"), eq(true), eq(false));
        verify(dramaMetrics, times(1)).recordFfmpegRetry(eq("concat"), eq(true), eq(true));
    }
}
