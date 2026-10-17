package com.dramafactory;

import com.dramafactory.controller.EpisodeController;
import com.dramafactory.dto.Records;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * EpisodeController 深度测试：直接注入控制器 bean，覆盖真实 API 行为。
 * 不再自造状态机/配置类；以真实 service + repository 为准。
 */
@SpringBootTest
@ActiveProfiles("test")
class EpisodeControllerDeepTest {

    @Autowired
    private EpisodeController controller;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private DramaProjectRepository projectRepository;

    @Autowired
    private SceneRepository sceneRepository;

    private Long projectId;

    @BeforeEach
    void setUp() {
        // 清空所有相关表，保证每个用例独立
        sceneRepository.deleteAll();
        episodeRepository.deleteAll();
        projectRepository.deleteAll();

        DramaProject project = new DramaProject();
        project.setTitle("深度测试项目");
        project = projectRepository.save(project);
        projectId = project.getId();
        assertNotNull(projectId, "预置项目 ID 不能为 null");
    }

    @Test
    void createReturns201AndBodyFieldsCorrectWithProjectIdBackfilled() {
        // given
        Records.EpisodeRequest request = new Records.EpisodeRequest(
                1, "第一集", "大纲内容", EpisodeStatus.DRAFT, 120);

        // when
        ResponseEntity<Records.EpisodeResponse> response = controller.create(projectId, request);

        // then
        assertAll(
                () -> assertEquals(HttpStatus.CREATED, response.getStatusCode(), "create 应返回 201"),
                () -> assertNotNull(response.getBody(), "响应体不能为 null"),
                () -> assertNotNull(response.getBody().id(), "剧集 ID 应被回填"),
                () -> assertEquals(projectId, response.getBody().projectId(), "projectId 应被回填"),
                () -> assertEquals(1, response.getBody().episodeNo(), "episodeNo 应匹配"),
                () -> assertEquals("第一集", response.getBody().title(), "title 应匹配"),
                () -> assertEquals("大纲内容", response.getBody().outline(), "outline 应匹配"),
                () -> assertEquals(EpisodeStatus.DRAFT, response.getBody().status(), "status 应匹配"),
                () -> assertEquals(120, response.getBody().durationSec(), "durationSec 应匹配")
        );
    }

    @Test
    void listByProjectReturnsEpisodesOrderedByEpisodeNoAscending() {
        // given：乱序创建三集
        controller.create(projectId, new Records.EpisodeRequest(3, "第三集", "o3", EpisodeStatus.DRAFT, 100));
        controller.create(projectId, new Records.EpisodeRequest(1, "第一集", "o1", EpisodeStatus.DRAFT, 100));
        controller.create(projectId, new Records.EpisodeRequest(2, "第二集", "o2", EpisodeStatus.DRAFT, 100));

        // when
        List<Records.EpisodeResponse> result = controller.listByProject(projectId);

        // then
        assertAll(
                () -> assertEquals(3, result.size(), "应返回 3 集"),
                () -> assertEquals(1, result.get(0).episodeNo(), "第 0 项集号应为 1"),
                () -> assertEquals(2, result.get(1).episodeNo(), "第 1 项集号应为 2"),
                () -> assertEquals(3, result.get(2).episodeNo(), "第 2 项集号应为 3")
        );
    }

    @Test
    void getReturnsPersistedEpisode() {
        // given
        Long id = controller.create(projectId,
                new Records.EpisodeRequest(1, "取回测试", "outline", EpisodeStatus.DRAFT, 90))
                .getBody().id();

        // when
        Records.EpisodeResponse found = controller.get(id);

        // then
        assertAll(
                () -> assertNotNull(found, "get 应返回非 null"),
                () -> assertEquals(id, found.id(), "id 应一致"),
                () -> assertEquals(projectId, found.projectId(), "projectId 应一致"),
                () -> assertEquals("取回测试", found.title(), "title 应一致")
        );
    }

    @Test
    void updateChangesTitleAndStatus() {
        // given
        Long id = controller.create(projectId,
                new Records.EpisodeRequest(1, "旧标题", "旧大纲", EpisodeStatus.DRAFT, 100))
                .getBody().id();

        Records.EpisodeRequest updateReq = new Records.EpisodeRequest(
                1, "新标题", "新大纲", EpisodeStatus.REVIEWED, 150);

        // when
        Records.EpisodeResponse updated = controller.update(id, updateReq);

        // then
        assertAll(
                () -> assertEquals(id, updated.id(), "id 不变"),
                () -> assertEquals("新标题", updated.title(), "标题应更新"),
                () -> assertEquals("新大纲", updated.outline(), "大纲应更新"),
                () -> assertEquals(EpisodeStatus.REVIEWED, updated.status(), "状态应更新"),
                () -> assertEquals(150, updated.durationSec(), "时长应更新")
        );

        // 再次从控制器读取，验证持久化
        Records.EpisodeResponse reloaded = controller.get(id);
        assertEquals("新标题", reloaded.title(), "重新读取标题应为新值");
        assertEquals(EpisodeStatus.REVIEWED, reloaded.status(), "重新读取状态应为新值");
    }

    @Test
    void deleteThenGetThrowsResourceNotFoundException() {
        // given
        Long id = controller.create(projectId,
                new Records.EpisodeRequest(1, "待删除", "o", EpisodeStatus.DRAFT, 100))
                .getBody().id();

        // when
        ResponseEntity<Void> deleteResp = controller.delete(id);

        // then
        assertAll(
                () -> assertEquals(HttpStatus.NO_CONTENT, deleteResp.getStatusCode(), "delete 应返回 204"),
                () -> assertThrows(ResourceNotFoundException.class, () -> controller.get(id),
                        "删除后再 get 应抛 ResourceNotFoundException")
        );
    }

    @Test
    void getUnknownIdThrowsResourceNotFoundException() {
        // given
        Long unknownId = 999_999L;

        // when / then
        assertThrows(ResourceNotFoundException.class, () -> controller.get(unknownId),
                "未知剧集 ID 应抛 ResourceNotFoundException，而不是返回 null");
    }

    @Test
    void createWithNonExistentProjectIdThrowsResourceNotFoundException() {
        // given
        Long badProjectId = 888_888L;
        Records.EpisodeRequest request = new Records.EpisodeRequest(
                1, "坏项目", "o", EpisodeStatus.DRAFT, 100);

        // when / then
        assertThrows(ResourceNotFoundException.class,
                () -> controller.create(badProjectId, request),
                "projectId 不存在时应抛 ResourceNotFoundException");
    }

    @Test
    void listByProjectWithNonExistentProjectThrowsResourceNotFoundException() {
        // given
        Long badProjectId = 777_777L;

        // when / then
        assertThrows(ResourceNotFoundException.class,
                () -> controller.listByProject(badProjectId),
                "不存在的 project 应抛 ResourceNotFoundException");
    }

    @Test
    void createWithNullStatusDefaultsToDraft() {
        // given：status 传 null
        Records.EpisodeRequest request = new Records.EpisodeRequest(
                1, "默认状态", "o", null, 100);

        // when
        ResponseEntity<Records.EpisodeResponse> response = controller.create(projectId, request);

        // then
        assertAll(
                () -> assertEquals(HttpStatus.CREATED, response.getStatusCode(), "应返回 201"),
                () -> assertNotNull(response.getBody(), "响应体不能为 null"),
                () -> assertEquals(EpisodeStatus.DRAFT, response.getBody().status(),
                        "status 为 null 时应默认为 DRAFT")
        );
    }

    @Test
    void createPersistsEpisodeRowInRepository() {
        // given
        Records.EpisodeRequest request = new Records.EpisodeRequest(
                5, "持久化校验", "o", EpisodeStatus.DRAFT, 100);

        // when
        Long id = controller.create(projectId, request).getBody().id();

        // then：仓库层面确认持久化
        Episode stored = episodeRepository.findById(id)
                .orElseThrow(() -> new AssertionError("剧集未持久化"));
        assertAll(
                () -> assertEquals("持久化校验", stored.getTitle(), "标题应持久化"),
                () -> assertEquals(5, stored.getEpisodeNo(), "集号应持久化"),
                () -> assertNotNull(stored.getProject(), "关联项目不应为 null"),
                () -> assertEquals(projectId, stored.getProject().getId(), "关联项目 ID 应一致")
        );
    }

    @Test
    void updateUnknownIdThrowsResourceNotFoundException() {
        // given
        Long unknownId = 666_666L;
        Records.EpisodeRequest request = new Records.EpisodeRequest(
                1, "更新未知", "o", EpisodeStatus.DRAFT, 100);

        // when / then
        assertThrows(ResourceNotFoundException.class,
                () -> controller.update(unknownId, request),
                "更新不存在的剧集应抛 ResourceNotFoundException");
    }

    @Test
    void deleteUnknownIdThrowsResourceNotFoundException() {
        // given
        Long unknownId = 555_555L;

        // when / then
        assertThrows(ResourceNotFoundException.class,
                () -> controller.delete(unknownId),
                "删除不存在的剧集应抛 ResourceNotFoundException");
    }

    @Test
    void listByProjectReturnsEmptyListWhenProjectHasNoEpisodes() {
        // given：预置项目但未创建任何剧集
        // when
        List<Records.EpisodeResponse> result = controller.listByProject(projectId);

        // then
        assertAll(
                () -> assertNotNull(result, "返回列表不能为 null"),
                () -> assertTrue(result.isEmpty(), "无剧集时应返回空列表")
        );
    }

    @Test
    void generateScriptForUnknownEpisodeThrowsControlledException() {
        // given：不存在的剧集 ID，避免触发真实 LLM 调用
        Long unknownId = 444_444L;

        // when / then：无论底层抛 ResourceNotFoundException 还是受控业务异常，
        // 都必须是非受检/受控异常类型，且不允许真实调用 LLM 成功返回。
        assertThrows(RuntimeException.class,
                () -> controller.generateScript(unknownId, "ai", null),
                "对未知剧集调用 generateScript 应抛出受控异常，而不应真实调用 LLM");
    }
}
