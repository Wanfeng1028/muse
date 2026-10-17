// 文件：src/test/java/com/dramafactory/service/EpisodeServiceV229Test.java

package com.dramafactory.service;

import com.dramafactory.dto.Records.EpisodeRequest;
import com.dramafactory.dto.Records.EpisodeResponse;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class EpisodeServiceV229Test {

    @Mock
    private EpisodeRepository episodeRepository;

    @Mock
    private DramaProjectRepository projectRepository;

    @Mock
    private SceneRepository sceneRepository;

    @InjectMocks
    private EpisodeService episodeService;

    private EpisodeRequest requestWithStatus;
    private EpisodeRequest requestWithoutStatus;

    @BeforeEach
    void setUp() {
        requestWithStatus = new EpisodeRequest(1, "标题", "大纲", EpisodeStatus.DRAFT, 120);
        requestWithoutStatus = new EpisodeRequest(1, "标题", "大纲", null, 120);
    }

    @Test
    @DisplayName("create：project 不存在时抛出 ResourceNotFoundException(Project)")
    void create_projectNotExists_throws() {
        when(projectRepository.existsById(99L)).thenReturn(false);

        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> episodeService.create(99L, requestWithStatus));

        assertNotNull(ex);
        verify(episodeRepository, never()).save(any());
    }

    @Test
    @DisplayName("create：status 为 null 时默认落为 DRAFT")
    void create_statusNull_defaultsToDraft() {
        when(projectRepository.existsById(1L)).thenReturn(true);
        DramaProject project = new DramaProject();
        project.setId(1L);
        when(projectRepository.getReferenceById(1L)).thenReturn(project);
        when(episodeRepository.save(any(Episode.class))).thenAnswer(inv -> inv.getArgument(0));
        when(sceneRepository.countByEpisodeId(any())).thenReturn(0L);

        EpisodeResponse response = episodeService.create(1L, requestWithoutStatus);

        assertNotNull(response);
        assertEquals(EpisodeStatus.DRAFT, response.status());
        assertEquals(1, response.episodeNo());
        assertEquals("标题", response.title());
        assertEquals("大纲", response.outline());
        assertEquals(120, response.durationSec());
        assertEquals(1L, response.projectId());
    }

    @Test
    @DisplayName("listByProject：project 不存在时抛出 ResourceNotFoundException(Project)")
    void listByProject_projectNotExists_throws() {
        when(projectRepository.existsById(99L)).thenReturn(false);

        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> episodeService.listByProject(99L));

        assertNotNull(ex);
        verify(episodeRepository, never()).findByProjectIdOrderByEpisodeNoAsc(anyLong());
    }

    @Test
    @DisplayName("listByProject：正常返回映射后的列表")
    void listByProject_returnsMappedList() {
        when(projectRepository.existsById(1L)).thenReturn(true);
        Episode e1 = new Episode();
        e1.setEpisodeNo(1);
        e1.setTitle("t1");
        e1.setOutline("o1");
        e1.setStatus(EpisodeStatus.DRAFT);
        e1.setDurationSec(100);
        Episode e2 = new Episode();
        e2.setEpisodeNo(2);
        e2.setTitle("t2");
        e2.setOutline("o2");
        e2.setStatus(EpisodeStatus.DRAFT);
        e2.setDurationSec(200);
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(1L)).thenReturn(Arrays.asList(e1, e2));
        when(sceneRepository.countByEpisodeId(any())).thenReturn(0L);

        List<EpisodeResponse> result = episodeService.listByProject(1L);

        assertNotNull(result);
        assertEquals(2, result.size());
        assertEquals("t1", result.get(0).title());
        assertEquals(1, result.get(0).episodeNo());
        assertEquals("t2", result.get(1).title());
        assertEquals(2, result.get(1).episodeNo());
        verify(episodeRepository, times(1)).findByProjectIdOrderByEpisodeNoAsc(1L);
    }

    @Test
    @DisplayName("update：id 不存在时抛出 ResourceNotFoundException(Episode)")
    void update_idNotExists_throws() {
        when(episodeRepository.findById(99L)).thenReturn(Optional.empty());

        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> episodeService.update(99L, requestWithStatus));

        assertNotNull(ex);
        verify(episodeRepository, never()).save(any());
    }

    @Test
    @DisplayName("update：status 为 null 时保持原 status")
    void update_statusNull_keepsOriginalStatus() {
        Episode existing = new Episode();
        existing.setEpisodeNo(5);
        existing.setTitle("old");
        existing.setOutline("oldOutline");
        existing.setStatus(EpisodeStatus.DRAFT);
        existing.setDurationSec(50);
        when(episodeRepository.findById(7L)).thenReturn(Optional.of(existing));
        when(episodeRepository.save(any(Episode.class))).thenAnswer(inv -> inv.getArgument(0));
        when(sceneRepository.countByEpisodeId(any())).thenReturn(0L);

        EpisodeResponse response = episodeService.update(7L, requestWithoutStatus);

        assertNotNull(response);
        assertEquals(EpisodeStatus.DRAFT, response.status());
        assertEquals(1, response.episodeNo());
        assertEquals("标题", response.title());
        assertEquals("大纲", response.outline());
        assertEquals(120, response.durationSec());
    }

    @Test
    @DisplayName("toResponse：episode.getProject() 为 null 时 projectId 为 null")
    void toResponse_projectNull_projectIdIsNull() {
        when(projectRepository.existsById(1L)).thenReturn(true);
        DramaProject project = new DramaProject();
        project.setId(1L);
        when(projectRepository.getReferenceById(1L)).thenReturn(project);
        Episode saved = new Episode();
        saved.setEpisodeNo(1);
        saved.setTitle("t");
        saved.setOutline("o");
        saved.setStatus(EpisodeStatus.DRAFT);
        saved.setDurationSec(60);
        saved.setCreatedAt(LocalDateTime.of(2026, 1, 1, 0, 0));
        saved.setUpdatedAt(LocalDateTime.of(2026, 1, 2, 0, 0));
        when(episodeRepository.save(any(Episode.class))).thenAnswer(inv -> {
            Episode arg = inv.getArgument(0);
            arg.setProject(null);
            arg.setCreatedAt(LocalDateTime.of(2026, 1, 1, 0, 0));
            arg.setUpdatedAt(LocalDateTime.of(2026, 1, 2, 0, 0));
            return arg;
        });
        when(sceneRepository.countByEpisodeId(any())).thenReturn(3L);

        EpisodeResponse response = episodeService.create(1L, requestWithStatus);

        assertNotNull(response);
        assertNull(response.projectId());
        assertEquals(3L, response.sceneCount());
        assertEquals(EpisodeStatus.DRAFT, response.status());
        assertEquals("标题", response.title());
    }
}