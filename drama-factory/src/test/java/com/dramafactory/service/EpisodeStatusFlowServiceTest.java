package com.dramafactory.service;

import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

/**
 * Unit tests for {@link EpisodeStatusFlowService}. No Spring context is started.
 */
class EpisodeStatusFlowServiceTest {

    private EpisodeRepository episodeRepository;
    private ShotRepository shotRepository;
    private VideoTaskRepository videoTaskRepository;
    private EpisodeStatusFlowService service;

    @BeforeEach
    void setUp() {
        episodeRepository = mock(EpisodeRepository.class);
        shotRepository = mock(ShotRepository.class);
        videoTaskRepository = mock(VideoTaskRepository.class);
        service = new EpisodeStatusFlowService(episodeRepository, shotRepository, videoTaskRepository);
    }

    private Episode episode(Long id, EpisodeStatus status) {
        Episode episode = new Episode();
        episode.setId(id);
        episode.setStatus(status);
        return episode;
    }

    private Shot shot(Long id) {
        Shot shot = new Shot();
        shot.setId(id);
        return shot;
    }

    private VideoTask task(VideoTaskStatus status) {
        VideoTask videoTask = new VideoTask();
        videoTask.setStatus(status);
        return videoTask;
    }

    @Test
    void refreshAfterTaskDone_noShots_doesNotAdvanceOrSave() {
        Episode episode = episode(1L, EpisodeStatus.SCRIPTED);
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(1L)).thenReturn(List.of());

        service.refreshAfterTaskDone(1L);

        assertEquals(EpisodeStatus.SCRIPTED, episode.getStatus());
        verify(episodeRepository, never()).save(any());
    }

    @Test
    void refreshAfterTaskDone_pendingTask_doesNotAdvanceOrSave() {
        Episode episode = episode(1L, EpisodeStatus.SCRIPTED);
        Shot shot = shot(10L);
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(1L)).thenReturn(List.of(shot));
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(10L))
                .thenReturn(Optional.of(task(VideoTaskStatus.PROCESSING)));

        service.refreshAfterTaskDone(1L);

        assertEquals(EpisodeStatus.SCRIPTED, episode.getStatus());
        verify(episodeRepository, never()).save(any());
    }

    @Test
    void refreshAfterTaskDone_allDoneAndDraft_advancesToGenerated() {
        Episode episode = episode(1L, EpisodeStatus.DRAFT);
        Shot shotA = shot(10L);
        Shot shotB = shot(11L);
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(1L)).thenReturn(List.of(shotA, shotB));
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(10L))
                .thenReturn(Optional.of(task(VideoTaskStatus.DONE)));
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(11L))
                .thenReturn(Optional.of(task(VideoTaskStatus.DONE)));
        when(episodeRepository.save(any(Episode.class))).thenAnswer(inv -> inv.getArgument(0));

        service.refreshAfterTaskDone(1L);

        assertEquals(EpisodeStatus.GENERATED, episode.getStatus());
        verify(episodeRepository).save(episode);
    }

    @Test
    void refreshAfterTaskDone_allDoneAndScripted_advancesToGenerated() {
        Episode episode = episode(1L, EpisodeStatus.SCRIPTED);
        Shot shot = shot(10L);
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(1L)).thenReturn(List.of(shot));
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(10L))
                .thenReturn(Optional.of(task(VideoTaskStatus.DONE)));
        when(episodeRepository.save(any(Episode.class))).thenAnswer(inv -> inv.getArgument(0));

        service.refreshAfterTaskDone(1L);

        assertEquals(EpisodeStatus.GENERATED, episode.getStatus());
        verify(episodeRepository).save(episode);
    }

    @Test
    void refreshAfterTaskDone_alreadyGenerated_doesNotSave() {
        Episode episode = episode(1L, EpisodeStatus.GENERATED);
        Shot shot = shot(10L);
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(1L)).thenReturn(List.of(shot));
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(10L))
                .thenReturn(Optional.of(task(VideoTaskStatus.DONE)));

        service.refreshAfterTaskDone(1L);

        assertEquals(EpisodeStatus.GENERATED, episode.getStatus());
        verify(episodeRepository, never()).save(any());
    }

    @Test
    void markQcApproved_setsReviewedAndSaves() {
        Episode episode = episode(1L, EpisodeStatus.GENERATED);
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));
        when(episodeRepository.save(any(Episode.class))).thenAnswer(inv -> inv.getArgument(0));

        service.markQcApproved(1L);

        assertEquals(EpisodeStatus.REVIEWED, episode.getStatus());
        verify(episodeRepository).save(episode);
    }

    @Test
    void markQcRejected_setsScriptedAndSaves() {
        Episode episode = episode(1L, EpisodeStatus.GENERATED);
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));
        when(episodeRepository.save(any(Episode.class))).thenAnswer(inv -> inv.getArgument(0));

        service.markQcRejected(1L, "画质不达标");

        assertEquals(EpisodeStatus.SCRIPTED, episode.getStatus());
        verify(episodeRepository).save(episode);
    }
}
