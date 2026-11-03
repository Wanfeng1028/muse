package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.Episode;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.FinalCutStatus;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * v2.32 flaky-6 根因歼灭——成片构建 ffmpeg 有界重试在未知运行时异常、
 * 中断异常与永久性异常三类逃逸路径下的 mock 级验证。
 */
class FfmpegRetryEscapeV232Test {

    @TempDir
    Path tempDir;

    private FinalCutRepository finalCutRepository;
    private EpisodeRepository episodeRepository;
    private ShotRepository shotRepository;
    private VideoTaskRepository videoTaskRepository;
    private SubtitleService subtitleService;
    private FfmpegService ffmpegService;
    private EpisodeStatusFlowService episodeStatusFlowService;
    private DramaMetrics dramaMetrics;
    private FinalCutService service;

    @BeforeEach
    void setUp() {
        finalCutRepository = mock(FinalCutRepository.class);
        episodeRepository = mock(EpisodeRepository.class);
        shotRepository = mock(ShotRepository.class);
        videoTaskRepository = mock(VideoTaskRepository.class);
        subtitleService = mock(SubtitleService.class);
        ffmpegService = mock(FfmpegService.class);
        episodeStatusFlowService = mock(EpisodeStatusFlowService.class);
        dramaMetrics = mock(DramaMetrics.class);
        service = new FinalCutService(finalCutRepository, episodeRepository, shotRepository,
                videoTaskRepository, subtitleService, ffmpegService, episodeStatusFlowService,
                tempDir.toString(), dramaMetrics, 3, 2000L);
        when(finalCutRepository.save(any())).thenAnswer(inv -> inv.getArgument(0));
    }

    private Episode episode() {
        Episode e = new Episode();
        e.setId(7L);
        e.setEpisodeNo(3);
        return e;
    }

    private Shot shot(Episode e) {
        Shot s = new Shot();
        s.setId(11L);
        s.setShotNo(1);
        s.setEpisode(e);
        s.setDurationSeconds(5);
        return s;
    }

    private VideoTask doneTask(Shot s, Path clip) {
        VideoTask t = new VideoTask();
        t.setId(21L);
        t.setShot(s);
        t.setStatus(VideoTaskStatus.DONE);
        t.setLocalPath(clip.toString());
        return t;
    }

    private void stubHappyRepos(Episode e, Shot s, VideoTask t) throws Exception {
        when(episodeRepository.findById(7L)).thenReturn(Optional.of(e));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(7L)).thenReturn(List.of(s));
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(11L)).thenReturn(Optional.of(t));
        when(subtitleService.buildSrt(eq(7L), any())).thenReturn(tempDir.resolve("t.srt"));
        when(ffmpegService.probeDurationSeconds(any())).thenReturn(4.0);
    }

    @Test
    @Timeout(value = 30, unit = TimeUnit.SECONDS)
    void unknownRuntimeException_isRetriedAsTransient() throws Exception {
        Episode e = episode();
        Shot s = shot(e);
        Path clip = tempDir.resolve("clip.mp4");
        Files.createFile(clip);
        VideoTask t = doneTask(s, clip);
        stubHappyRepos(e, s, t);

        doThrow(new IllegalStateException("boom"))
                .when(ffmpegService).concatClips(anyList(), any(Path.class));

        FfmpegService.FfmpegException thrown = assertThrows(FfmpegService.FfmpegException.class,
                () -> service.buildFinalCut(7L));
        assertEquals(true, thrown.isTransient());

        verify(ffmpegService, times(3)).concatClips(anyList(), any(Path.class));
        verify(dramaMetrics, times(3)).recordFfmpegRetry(eq("concat"), eq(true), eq(false));
    }

    @Test
    @Timeout(value = 30, unit = TimeUnit.SECONDS)
    void ffmpegInterruptedException_propagatesWithoutRetry() throws Exception {
        Episode e = episode();
        Shot s = shot(e);
        Path clip = tempDir.resolve("clip.mp4");
        Files.createFile(clip);
        VideoTask t = doneTask(s, clip);
        stubHappyRepos(e, s, t);

        doThrow(new FfmpegService.FfmpegInterruptedException("interrupted by test", new InterruptedException("test")))
                .when(ffmpegService).concatClips(anyList(), any(Path.class));

        assertThrows(FfmpegService.FfmpegInterruptedException.class,
                () -> service.buildFinalCut(7L));

        verify(ffmpegService, times(1)).concatClips(anyList(), any(Path.class));
        verify(dramaMetrics, never()).recordFfmpegRetry(anyString(), anyBoolean(), anyBoolean());
    }

    @Test
    @Timeout(value = 30, unit = TimeUnit.SECONDS)
    void permanentFfmpegException_failsFast() throws Exception {
        Episode e = episode();
        Shot s = shot(e);
        Path clip = tempDir.resolve("clip.mp4");
        Files.createFile(clip);
        VideoTask t = doneTask(s, clip);
        stubHappyRepos(e, s, t);

        doThrow(new FfmpegService.FfmpegException("permanent failure", false))
                .when(ffmpegService).concatClips(anyList(), any(Path.class));

        FfmpegService.FfmpegException thrown2 = assertThrows(FfmpegService.FfmpegException.class,
                () -> service.buildFinalCut(7L));
        assertEquals(false, thrown2.isTransient());

        verify(ffmpegService, times(1)).concatClips(anyList(), any(Path.class));
    }
}
