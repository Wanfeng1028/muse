package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
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
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.atLeast;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class FinalCutServiceTest {

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

        service = new FinalCutService(
                finalCutRepository,
                episodeRepository,
                shotRepository,
                videoTaskRepository,
                subtitleService,
                ffmpegService,
                episodeStatusFlowService,
                tempDir.toString(),
                dramaMetrics,
                3,
                2000L);

        when(finalCutRepository.save(any())).thenAnswer(inv -> inv.getArgument(0));
    }

    private Episode episode() {
        Episode e = new Episode();
        e.setId(7L);
        e.setEpisodeNo(3);
        return e;
    }

    private Shot shot(Long id, int shotNo, Episode e) {
        Shot s = new Shot();
        s.setId(id);
        s.setShotNo(shotNo);
        s.setEpisode(e);
        s.setDurationSeconds(5);
        return s;
    }

    private VideoTask task(Long id, Shot s, VideoTaskStatus status, String localPath) {
        VideoTask t = new VideoTask();
        t.setId(id);
        t.setShot(s);
        t.setStatus(status);
        t.setLocalPath(localPath);
        return t;
    }

    private FinalCut finalCut(Long id, Episode e, String title, FinalCutStatus status) {
        FinalCut fc = new FinalCut();
        fc.setId(id);
        fc.setEpisode(e);
        fc.setTitle(title);
        fc.setStatus(status);
        return fc;
    }

    // ---------- T1 ----------
    @Test
    void buildFinalCut_episodeNotFound() {
        when(episodeRepository.findById(9L)).thenReturn(Optional.empty());

        assertThrows(ResourceNotFoundException.class, () -> service.buildFinalCut(9L));

        verify(dramaMetrics).recordFinalCutBuild(anyLong(), eq(false));
    }

    // ---------- T2 ----------
    @Test
    void buildFinalCut_noShots() {
        Episode e = episode();
        when(episodeRepository.findById(7L)).thenReturn(Optional.of(e));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(7L)).thenReturn(List.of());

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> service.buildFinalCut(7L));
        assertTrue(ex.getMessage().contains("该剧集没有分镜"));

        ArgumentCaptor<FinalCut> cap = ArgumentCaptor.forClass(FinalCut.class);
        verify(finalCutRepository, atLeast(2)).save(cap.capture());
        FinalCut last = cap.getAllValues().get(cap.getAllValues().size() - 1);
        assertEquals(FinalCutStatus.FAILED, last.getStatus());
        assertNotNull(last.getErrorMessage());
        assertTrue(last.getErrorMessage().contains("没有分镜"));

        verify(dramaMetrics).recordFinalCutBuild(anyLong(), eq(false));
    }

    // ---------- T3 ----------
    @Test
    void buildFinalCut_shotWithoutDoneVideo_processing() {
        Episode e = episode();
        Shot s1 = shot(11L, 1, e);
        when(episodeRepository.findById(7L)).thenReturn(Optional.of(e));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(7L)).thenReturn(List.of(s1));
        VideoTask t = task(21L, s1, VideoTaskStatus.PROCESSING, null);
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(11L)).thenReturn(Optional.of(t));

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> service.buildFinalCut(7L));
        assertTrue(ex.getMessage().contains("分镜 1 尚无已完成的视频"));
    }

    @Test
    void buildFinalCut_shotWithoutDoneVideo_doneButNullPath() {
        Episode e = episode();
        Shot s1 = shot(11L, 1, e);
        when(episodeRepository.findById(7L)).thenReturn(Optional.of(e));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(7L)).thenReturn(List.of(s1));
        VideoTask t = task(21L, s1, VideoTaskStatus.DONE, null);
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(11L)).thenReturn(Optional.of(t));

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> service.buildFinalCut(7L));
        assertTrue(ex.getMessage().contains("分镜 1 尚无已完成的视频"));
    }

    @Test
    void buildFinalCut_shotWithoutDoneVideo_doneButMissingFile() {
        Episode e = episode();
        Shot s1 = shot(11L, 1, e);
        when(episodeRepository.findById(7L)).thenReturn(Optional.of(e));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(7L)).thenReturn(List.of(s1));
        VideoTask t = task(21L, s1, VideoTaskStatus.DONE,
                tempDir.resolve("nope-" + System.nanoTime() + ".mp4").toString());
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(11L)).thenReturn(Optional.of(t));

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> service.buildFinalCut(7L));
        assertTrue(ex.getMessage().contains("分镜 1 尚无已完成的视频"));
    }

    // ---------- T4 ----------
    @Test
    void buildFinalCut_success() throws Exception {
        Episode e = episode();
        Shot s1 = shot(11L, 1, e);
        Shot s2 = shot(12L, 2, e);
        when(episodeRepository.findById(7L)).thenReturn(Optional.of(e));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(7L)).thenReturn(List.of(s1, s2));

        Path f1 = tempDir.resolve("clip1-" + System.nanoTime() + ".mp4");
        Path f2 = tempDir.resolve("clip2-" + System.nanoTime() + ".mp4");
        Files.createFile(f1);
        Files.createFile(f2);

        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(11L))
                .thenReturn(Optional.of(task(21L, s1, VideoTaskStatus.DONE, f1.toString())));
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(12L))
                .thenReturn(Optional.of(task(22L, s2, VideoTaskStatus.DONE, f2.toString())));

        doNothing().when(ffmpegService).concatClips(any(), any());
        doNothing().when(ffmpegService).burnSubtitles(any(), any(), any());
        when(ffmpegService.probeDurationSeconds(any())).thenReturn(12.5);
        when(subtitleService.buildSrt(eq(7L), any())).thenReturn(tempDir.resolve("x.srt"));

        Records.FinalCutResponse resp = service.buildFinalCut(7L);

        assertEquals("第3集成片", resp.title());
        assertEquals(FinalCutStatus.READY, resp.status());
        assertEquals(12.5, resp.durationSeconds());
        assertNotNull(resp.fileName());
        assertTrue(resp.fileName().endsWith(".mp4"));
        assertNotNull(resp.filePath());
        assertTrue(resp.filePath().startsWith(tempDir.resolve("finals").toString()));

        verify(dramaMetrics).recordFinalCutBuild(anyLong(), eq(true));
        verifyNoInteractions(episodeStatusFlowService);
    }

    // ---------- T5 ----------
    @Test
    void buildFinalCut_concatFails() throws Exception {
        Episode e = episode();
        Shot s1 = shot(11L, 1, e);
        when(episodeRepository.findById(7L)).thenReturn(Optional.of(e));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(7L)).thenReturn(List.of(s1));

        Path f1 = tempDir.resolve("clip-" + System.nanoTime() + ".mp4");
        Files.createFile(f1);
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(11L))
                .thenReturn(Optional.of(task(21L, s1, VideoTaskStatus.DONE, f1.toString())));

        doThrow(new FfmpegService.FfmpegException("炸了"))
                .when(ffmpegService).concatClips(any(), any());

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.buildFinalCut(7L));
        assertTrue(ex.getMessage().contains("炸了"));

        ArgumentCaptor<FinalCut> cap = ArgumentCaptor.forClass(FinalCut.class);
        verify(finalCutRepository, atLeast(2)).save(cap.capture());
        FinalCut last = cap.getAllValues().get(cap.getAllValues().size() - 1);
        assertEquals(FinalCutStatus.FAILED, last.getStatus());
        assertNotNull(last.getErrorMessage());
        assertTrue(last.getErrorMessage().contains("炸了"));

        verify(dramaMetrics).recordFinalCutBuild(anyLong(), eq(false));
    }

    // ---------- T6 ----------
    @Test
    void qc_approve() {
        Episode e = episode();
        FinalCut fc = finalCut(31L, e, "x", FinalCutStatus.READY);
        when(finalCutRepository.findById(31L)).thenReturn(Optional.of(fc));

        Records.FinalCutResponse resp = service.qc(31L, new Records.QcRequest(" approved ", "good"));

        assertEquals("APPROVED", resp.qcStatus());
        verify(episodeStatusFlowService).markQcApproved(7L);
        assertEquals("good", fc.getQcNote());
        assertNotNull(fc.getQcAt());
    }

    // ---------- T7 ----------
    @Test
    void qc_reject() {
        Episode e = episode();
        FinalCut fc = finalCut(31L, e, "x", FinalCutStatus.READY);
        when(finalCutRepository.findById(31L)).thenReturn(Optional.of(fc));

        Records.FinalCutResponse resp = service.qc(31L, new Records.QcRequest("REJECTED", "太暗"));

        assertEquals("REJECTED", resp.qcStatus());
        verify(episodeStatusFlowService).markQcRejected(7L, "太暗");
    }

    // ---------- T8 ----------
    @Test
    void qc_notReady() {
        Episode e = episode();
        FinalCut fc = finalCut(31L, e, "x", FinalCutStatus.BUILDING);
        when(finalCutRepository.findById(31L)).thenReturn(Optional.of(fc));

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> service.qc(31L, new Records.QcRequest("APPROVED", "ok")));
        assertTrue(ex.getMessage().contains("成片尚未完成"));
    }

    // ---------- T9 ----------
    @Test
    void qc_badVerdict_maybe() {
        Episode e = episode();
        FinalCut fc = finalCut(31L, e, "x", FinalCutStatus.READY);
        when(finalCutRepository.findById(31L)).thenReturn(Optional.of(fc));

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.qc(31L, new Records.QcRequest("MAYBE", "hmm")));
        assertTrue(ex.getMessage().contains("verdict 只能是"));
    }

    @Test
    void qc_badVerdict_null() {
        Episode e = episode();
        FinalCut fc = finalCut(31L, e, "x", FinalCutStatus.READY);
        when(finalCutRepository.findById(31L)).thenReturn(Optional.of(fc));

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.qc(31L, new Records.QcRequest(null, null)));
        assertTrue(ex.getMessage().contains("verdict 只能是"));
    }

    // ---------- T10 ----------
    @Test
    void qc_notFound() {
        when(finalCutRepository.findById(99L)).thenReturn(Optional.empty());

        assertThrows(ResourceNotFoundException.class,
                () -> service.qc(99L, new Records.QcRequest("APPROVED", "ok")));
    }

    // ---------- T11 ----------
    @Test
    void get_notFound() {
        when(finalCutRepository.findById(99L)).thenReturn(Optional.empty());

        assertThrows(ResourceNotFoundException.class, () -> service.get(99L));
    }

    // ---------- T12 ----------
    @Test
    void get_mappingNulls() {
        Episode e = episode();
        FinalCut fc = new FinalCut();
        fc.setId(31L);
        fc.setEpisode(e);
        fc.setTitle("x");
        when(finalCutRepository.findById(31L)).thenReturn(Optional.of(fc));

        Records.FinalCutResponse resp = service.get(31L);

        assertNull(resp.fileName());
        assertNull(resp.statusLabel());
        assertNull(resp.status());
    }

    // ---------- T13 ----------
    @Test
    void listByEpisode() {
        Episode e = episode();
        FinalCut a = finalCut(31L, e, "a", FinalCutStatus.READY);
        FinalCut b = finalCut(32L, e, "b", FinalCutStatus.READY);
        when(finalCutRepository.findByEpisodeIdOrderByIdDesc(7L)).thenReturn(List.of(a, b));

        List<Records.FinalCutResponse> list = service.listByEpisode(7L);
        assertEquals(2, list.size());
    }

    @Test
    void listByEpisode_empty() {
        when(finalCutRepository.findByEpisodeIdOrderByIdDesc(7L)).thenReturn(List.of());

        List<Records.FinalCutResponse> list = service.listByEpisode(7L);
        assertTrue(list.isEmpty());
    }

    // ---------- T14 ----------
    @Test
    void toResponse_fileName() {
        Episode e = episode();
        FinalCut fc = finalCut(31L, e, "x", FinalCutStatus.READY);
        fc.setFilePath("/a/b/c.mp4");
        when(finalCutRepository.findById(31L)).thenReturn(Optional.of(fc));

        Records.FinalCutResponse resp = service.get(31L);
        assertEquals("c.mp4", resp.fileName());
    }

    @Test
    void toResponse_fileName_emptyPath() {
        Episode e = episode();
        FinalCut fc = finalCut(31L, e, "x", FinalCutStatus.READY);
        fc.setFilePath("");
        when(finalCutRepository.findById(31L)).thenReturn(Optional.of(fc));

        Records.FinalCutResponse resp = service.get(31L);
        assertNull(resp.fileName());
    }

    // ---------- T15 ----------
    @Test
    void buildFinalCut_storageBlocked_wrapsCheckedException() throws Exception {
        Episode e = episode();
        Shot s1 = shot(11L, 1, e);
        when(episodeRepository.findById(7L)).thenReturn(Optional.of(e));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(7L)).thenReturn(List.of(s1));

        Path clip = tempDir.resolve("clip.mp4");
        Files.createFile(clip);
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(11L))
                .thenReturn(Optional.of(task(21L, s1, VideoTaskStatus.DONE, clip.toString())));

        // finals 被普通文件占住 → Files.createDirectories 抛 FileAlreadyExistsException（checked 异常）
        Files.createFile(tempDir.resolve("finals"));

        RuntimeException ex = assertThrows(RuntimeException.class, () -> service.buildFinalCut(7L));
        // 走 e instanceof RuntimeException ? re : new RuntimeException(e) 的 false 分支
        assertNotNull(ex.getCause());

        ArgumentCaptor<FinalCut> cap = ArgumentCaptor.forClass(FinalCut.class);
        verify(finalCutRepository, atLeast(2)).save(cap.capture());
        FinalCut last = cap.getAllValues().get(cap.getAllValues().size() - 1);
        assertEquals(FinalCutStatus.FAILED, last.getStatus());
        verify(dramaMetrics).recordFinalCutBuild(anyLong(), eq(false));
    }
}


