package com.dramafactory.service;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.ShotReadinessService.ReadinessCheck;
import com.dramafactory.service.ShotReadinessService.ShotReadinessReport;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ShotReadinessServiceTest {

    private final ShotRepository shotRepository = mock(ShotRepository.class);
    private final VideoTaskRepository videoTaskRepository = mock(VideoTaskRepository.class);
    private final ShotReadinessService service = new ShotReadinessService(shotRepository, videoTaskRepository);

    private Shot shot(Long id, Long episodeId) {
        Episode episode = new Episode();
        episode.setId(episodeId);
        Shot shot = new Shot();
        shot.setId(id);
        shot.setEpisode(episode);
        shot.setShotNo(1);
        shot.setDescription("主角走进雨夜的巷子");
        shot.setVideoPrompt("rainy alley, man walking, cinematic");
        shot.setDurationSeconds(5);
        shot.setShotSize(ShotSize.JIN_JING);
        shot.setCameraMove(CameraMove.TUI);
        shot.setGenerateAudio(false);
        return shot;
    }

    private Map<String, ReadinessCheck> byKey(ShotReadinessReport report) {
        return report.checks().stream().collect(Collectors.toMap(ReadinessCheck::key, c -> c));
    }

    @Test
    void readyShot_reportsReadyAndUsesVideoPrompt() {
        Shot shot = shot(7L, 3L);
        when(videoTaskRepository.findFirstByShotIdAndStatusInOrderByIdAsc(7L, List.of(VideoTaskStatus.PENDING, VideoTaskStatus.PROCESSING)))
                .thenReturn(Optional.empty());

        ShotReadinessReport report = service.assess(shot);

        assertThat(report.ready()).isTrue();
        assertThat(report.shotId()).isEqualTo(7L);
        assertThat(report.promptPreview()).isEqualTo("rainy alley, man walking, cinematic");
        assertThat(report.promptPreviewDerived()).isFalse();
        assertThat(byKey(report).get("activeTask").ok()).isTrue();
    }

    @Test
    void missingVideoPrompt_blocksReadyAndDerivesPreview() {
        Shot shot = shot(7L, 3L);
        shot.setVideoPrompt(null);
        when(videoTaskRepository.findFirstByShotIdAndStatusInOrderByIdAsc(7L, List.of(VideoTaskStatus.PENDING, VideoTaskStatus.PROCESSING)))
                .thenReturn(Optional.empty());

        ShotReadinessReport report = service.assess(shot);

        assertThat(report.ready()).isFalse();
        assertThat(byKey(report).get("videoPrompt").ok()).isFalse();
        assertThat(byKey(report).get("videoPrompt").level()).isEqualTo("BLOCKING");
        assertThat(report.promptPreviewDerived()).isTrue();
        assertThat(report.promptPreview()).contains("主角走进雨夜的巷子");
    }

    @Test
    void audioWithoutDialogue_blocksReady() {
        Shot shot = shot(7L, 3L);
        shot.setGenerateAudio(true);
        shot.setDialogue(null);
        when(videoTaskRepository.findFirstByShotIdAndStatusInOrderByIdAsc(7L, List.of(VideoTaskStatus.PENDING, VideoTaskStatus.PROCESSING)))
                .thenReturn(Optional.empty());

        ShotReadinessReport report = service.assess(shot);

        assertThat(report.ready()).isFalse();
        assertThat(byKey(report).get("dialogueAudio").ok()).isFalse();
    }

    @Test
    void missingShotSizeAndCameraMove_areWarningsNotBlockers() {
        Shot shot = shot(7L, 3L);
        shot.setShotSize(null);
        shot.setCameraMove(null);
        when(videoTaskRepository.findFirstByShotIdAndStatusInOrderByIdAsc(7L, List.of(VideoTaskStatus.PENDING, VideoTaskStatus.PROCESSING)))
                .thenReturn(Optional.empty());

        ShotReadinessReport report = service.assess(shot);

        assertThat(report.ready()).isTrue();
        assertThat(byKey(report).get("shotSize").level()).isEqualTo("WARNING");
        assertThat(byKey(report).get("shotSize").ok()).isFalse();
        assertThat(byKey(report).get("cameraMove").ok()).isFalse();
    }

    @Test
    void activeTask_isInfoOnlyAndDoesNotBlockReady() {
        Shot shot = shot(7L, 3L);
        VideoTask task = new VideoTask();
        task.setStatus(VideoTaskStatus.PROCESSING);
        when(videoTaskRepository.findFirstByShotIdAndStatusInOrderByIdAsc(7L, List.of(VideoTaskStatus.PENDING, VideoTaskStatus.PROCESSING)))
                .thenReturn(Optional.of(task));

        ShotReadinessReport report = service.assess(shot);

        assertThat(report.ready()).isTrue();
        assertThat(byKey(report).get("activeTask").level()).isEqualTo("INFO");
        assertThat(byKey(report).get("activeTask").ok()).isFalse();
        assertThat(byKey(report).get("activeTask").message()).contains("PROCESSING");
    }

    @Test
    void emptyDescriptionAndPrompt_yieldsEmptyDerivedPreview() {
        Shot shot = shot(7L, 3L);
        shot.setDescription("  ");
        shot.setVideoPrompt("");
        when(videoTaskRepository.findFirstByShotIdAndStatusInOrderByIdAsc(7L, List.of(VideoTaskStatus.PENDING, VideoTaskStatus.PROCESSING)))
                .thenReturn(Optional.empty());

        ShotReadinessReport report = service.assess(shot);

        assertThat(report.ready()).isFalse();
        assertThat(report.promptPreview()).isEqualTo("");
        assertThat(report.promptPreviewDerived()).isTrue();
    }

    @Test
    void getForShot_wrongEpisode_throwsNotFound() {
        Shot shot = shot(7L, 3L);
        when(shotRepository.findById(7L)).thenReturn(Optional.of(shot));

        assertThatThrownBy(() -> service.getForShot(999L, 7L))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    @Test
    void getForShot_missingShot_throwsNotFound() {
        when(shotRepository.findById(7L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.getForShot(3L, 7L))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    @Test
    void assessEpisode_returnsReportsInOrder() {
        Shot first = shot(7L, 3L);
        first.setShotNo(1);
        Shot second = shot(8L, 3L);
        second.setShotNo(2);
        second.setVideoPrompt(null);
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(3L)).thenReturn(List.of(first, second));
        when(videoTaskRepository.findFirstByShotIdAndStatusInOrderByIdAsc(7L, List.of(VideoTaskStatus.PENDING, VideoTaskStatus.PROCESSING)))
                .thenReturn(Optional.empty());
        when(videoTaskRepository.findFirstByShotIdAndStatusInOrderByIdAsc(8L, List.of(VideoTaskStatus.PENDING, VideoTaskStatus.PROCESSING)))
                .thenReturn(Optional.empty());

        List<ShotReadinessReport> reports = service.assessEpisode(3L);

        assertThat(reports).hasSize(2);
        assertThat(reports.get(0).shotId()).isEqualTo(7L);
        assertThat(reports.get(0).ready()).isTrue();
        assertThat(reports.get(1).shotId()).isEqualTo(8L);
        assertThat(reports.get(1).ready()).isFalse();
    }
}
