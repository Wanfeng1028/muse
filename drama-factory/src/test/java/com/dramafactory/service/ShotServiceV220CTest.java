package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Collections;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * ShotService 分支覆盖测试（v2.20 第 C 批）。
 *
 * 覆盖目标：
 * - delete：existsById false 抛异常臂 / true 走删除臂
 * - reorder：shotIds null 直接返回臂 / shotIds empty 直接返回臂 /
 *   findAllById 数量不等抛臂 / shot.getEpisode()==null 抛臂 /
 *   episodeId 不匹配抛臂 / shotMap.get 返回 null 抛臂 / 成功重排臂
 * - toResponse：shot.getEpisode()==null 走 null 臂（经 get 触达）
 */
@ExtendWith(MockitoExtension.class)
class ShotServiceV220CTest {

    @Mock
    private ShotRepository shotRepository;

    @Mock
    private EpisodeRepository episodeRepository;

    @InjectMocks
    private ShotService shotService;

    // ------------------------------------------------------------------
    // delete：existsById 返回 false -> 抛 ResourceNotFoundException 臂
    // ------------------------------------------------------------------
    @Test
    void delete_existsByIdFalse_throwsResourceNotFoundExceptionArm() {
        when(shotRepository.existsById(7L)).thenReturn(false);

        assertThrows(ResourceNotFoundException.class, () -> shotService.delete(7L));
        verify(shotRepository, never()).deleteById(anyLong());
    }

    // ------------------------------------------------------------------
    // delete：existsById 返回 true -> 走删除臂
    // ------------------------------------------------------------------
    @Test
    void delete_existsByIdTrue_delegatesToDeleteByIdArm() {
        when(shotRepository.existsById(8L)).thenReturn(true);

        shotService.delete(8L);

        verify(shotRepository).deleteById(8L);
    }

    // ------------------------------------------------------------------
    // reorder：shotIds 为 null -> 直接返回臂
    // ------------------------------------------------------------------
    @Test
    void reorder_shotIdsNull_returnsImmediatelyArm() {
        shotService.reorder(1L, null);

        verify(shotRepository, never()).findAllById(any());
        verify(shotRepository, never()).saveAll(any());
    }

    // ------------------------------------------------------------------
    // reorder：shotIds 为空 -> 直接返回臂
    // ------------------------------------------------------------------
    @Test
    void reorder_shotIdsEmpty_returnsImmediatelyArm() {
        shotService.reorder(1L, Collections.emptyList());

        verify(shotRepository, never()).findAllById(any());
        verify(shotRepository, never()).saveAll(any());
    }

    // ------------------------------------------------------------------
    // reorder：findAllById 返回数量与入参不一致 -> 抛 IllegalArgumentException 臂
    // ------------------------------------------------------------------
    @Test
    void reorder_findAllByIdSizeMismatch_throwsIllegalArgumentArm() {
        List<Long> ids = List.of(1L, 2L);
        when(shotRepository.findAllById(ids)).thenReturn(List.of(new Shot()));

        assertThrows(IllegalArgumentException.class, () -> shotService.reorder(1L, ids));
        verify(shotRepository, never()).saveAll(any());
    }

    // ------------------------------------------------------------------
    // reorder：shot.getEpisode() == null -> 抛 IllegalArgumentException 臂
    // ------------------------------------------------------------------
    @Test
    void reorder_shotEpisodeNull_throwsIllegalArgumentArm() {
        List<Long> ids = List.of(1L);
        Shot shot = new Shot();
        shot.setId(1L);
        shot.setEpisode(null);
        when(shotRepository.findAllById(ids)).thenReturn(List.of(shot));

        assertThrows(IllegalArgumentException.class, () -> shotService.reorder(1L, ids));
        verify(shotRepository, never()).saveAll(any());
    }

    // ------------------------------------------------------------------
    // reorder：episodeId 与 shot.getEpisode().getId() 不匹配 -> 抛 IllegalArgumentException 臂
    // ------------------------------------------------------------------
    @Test
    void reorder_episodeIdMismatch_throwsIllegalArgumentArm() {
        List<Long> ids = List.of(1L);
        Episode episode = new Episode();
        episode.setId(99L);
        Shot shot = new Shot();
        shot.setId(1L);
        shot.setEpisode(episode);
        when(shotRepository.findAllById(ids)).thenReturn(List.of(shot));

        assertThrows(IllegalArgumentException.class, () -> shotService.reorder(1L, ids));
        verify(shotRepository, never()).saveAll(any());
    }

    // ------------------------------------------------------------------
    // reorder：shotMap.get 返回 null -> 抛 IllegalArgumentException 臂
    // 构造方式：findAllById 返回两个 Shot，id 为 2L 和 3L（数量与入参一致），
    // 但 shotIds 含 1L（映射中不存在），且所有 shot 都归属正确 episode。
    // 这样能通过前两个校验，在 shotMap.get(1L) 处命中 null 分支。
    // ------------------------------------------------------------------
    @Test
    void reorder_shotMapGetNull_throwsIllegalArgumentArm() {
        List<Long> ids = List.of(1L, 2L);
        Episode episode = new Episode();
        episode.setId(1L);

        Shot shot2 = new Shot();
        shot2.setId(2L);
        shot2.setEpisode(episode);

        Shot shot3 = new Shot();
        shot3.setId(3L);
        shot3.setEpisode(episode);

        // 返回数量与入参一致（2），且 episode 匹配，但 id 集合为 {2,3}，不含 1
        when(shotRepository.findAllById(ids)).thenReturn(List.of(shot2, shot3));

        assertThrows(IllegalArgumentException.class, () -> shotService.reorder(1L, ids));
        verify(shotRepository, never()).saveAll(any());
    }

    // ------------------------------------------------------------------
    // reorder：成功重排臂（shotNo 按列表顺序 1..n，并 saveAll）
    // ------------------------------------------------------------------
    @Test
    void reorder_success_assignsSequentialShotNoAndSavesArm() {
        List<Long> ids = List.of(3L, 1L, 2L);
        Episode episode = new Episode();
        episode.setId(1L);

        Shot shot1 = new Shot();
        shot1.setId(1L);
        shot1.setEpisode(episode);
        Shot shot2 = new Shot();
        shot2.setId(2L);
        shot2.setEpisode(episode);
        Shot shot3 = new Shot();
        shot3.setId(3L);
        shot3.setEpisode(episode);

        // 返回顺序与内部映射无关，reorder 会按 shotIds 顺序赋值
        when(shotRepository.findAllById(ids)).thenReturn(List.of(shot1, shot2, shot3));

        shotService.reorder(1L, ids);

        // 按列表顺序：3L -> 1, 1L -> 2, 2L -> 3
        assertEquals(1, shot3.getShotNo());
        assertEquals(2, shot1.getShotNo());
        assertEquals(3, shot2.getShotNo());
        verify(shotRepository).saveAll(any());
    }

    // ------------------------------------------------------------------
    // toResponse：shot.getEpisode() == null 走 null 臂（经 get 触达）
    // ------------------------------------------------------------------
    @Test
    void get_shotEpisodeNull_returnsResponseWithNullEpisodeIdArm() {
        Shot shot = new Shot();
        shot.setId(5L);
        shot.setEpisode(null);
        shot.setShotNo(1);
        shot.setShotSize(ShotSize.TE_XIE);
        shot.setCameraMove(CameraMove.GU_DING);
        when(shotRepository.findById(5L)).thenReturn(Optional.of(shot));

        Records.ShotResponse response = shotService.get(5L);

        assertEquals(5L, response.id());
        assertNull(response.episodeId());
        assertEquals(ShotSize.TE_XIE, response.shotSize());
        assertEquals(CameraMove.GU_DING, response.cameraMove());
    }

    // ------------------------------------------------------------------
    // toResponse：shotSize / cameraMove 为 null 走 label 为 null 臂（经 get 触达）
    // ------------------------------------------------------------------
    @Test
    void get_shotSizeAndCameraMoveNull_returnsNullLabelsArm() {
        Shot shot = new Shot();
        shot.setId(6L);
        shot.setEpisode(null);
        shot.setShotNo(2);
        shot.setShotSize(null);
        shot.setCameraMove(null);
        when(shotRepository.findById(6L)).thenReturn(Optional.of(shot));

        Records.ShotResponse response = shotService.get(6L);

        assertNull(response.shotSize());
        assertNull(response.shotSizeLabel());
        assertNull(response.cameraMove());
        assertNull(response.cameraMoveLabel());
    }
}
