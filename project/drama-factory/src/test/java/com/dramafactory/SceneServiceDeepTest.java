package com.dramafactory;

import com.dramafactory.dto.Records.SceneRequest;
import com.dramafactory.dto.Records.SceneResponse;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import com.dramafactory.service.SceneService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.DramaCharacterRepository;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@Transactional
class SceneServiceDeepTest {

    @Autowired
    private SceneService sceneService;

    @Autowired
    private DramaProjectRepository projectRepository;

    @Autowired
    private VideoTaskRepository videoTaskRepository;

    @Autowired
    private ShotRepository shotRepository;

    @Autowired
    private DramaCharacterRepository characterRepository;

    @Autowired
    private SceneRepository sceneRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    private Episode savedEpisode;

    @BeforeEach
    void setUp() {
        videoTaskRepository.deleteAll();
        shotRepository.deleteAll();
        sceneRepository.deleteAll();
        characterRepository.deleteAll();
        episodeRepository.deleteAll();
        projectRepository.deleteAll();
        DramaProject p = new DramaProject();
        p.setTitle("测试项目");
        DramaProject savedProject = projectRepository.save(p);
        Episode episode = new Episode();
        episode.setTitle("测试剧集");
        episode.setProject(savedProject);
        episode.setEpisodeNo(1);
        savedEpisode = episodeRepository.save(episode);
    }

    private SceneRequest sampleRequest(int sceneNo) {
        return new SceneRequest(
                sceneNo,
                "咖啡馆",
                "夜晚",
                "主角在角落里等一个人",
                "你终于来了",
                "cinematic wide shot, night cafe"
        );
    }

    @Test
    void create_persistsSceneAndReturnsResponse() {
        // given: 一个已存在的剧集和一个合法的场景请求
        SceneRequest request = sampleRequest(1);

        // when: 调用 create 创建场景
        SceneResponse response = sceneService.create(savedEpisode.getId(), request);

        // then: 返回体字段与请求一致，且数据库里确实落了一条记录
        assertNotNull(response.id());
        assertEquals(savedEpisode.getId(), response.episodeId());
        assertEquals(1, response.sceneNo());
        assertEquals("咖啡馆", response.location());
        assertEquals("夜晚", response.timeOfDay());
        assertEquals("你终于来了", response.dialogue());
        assertEquals(1L, sceneRepository.count());
    }

    @Test
    void create_withMissingEpisode_throwsResourceNotFound() {
        // given: 一个不存在的剧集 id
        Long missingEpisodeId = 999999L;
        SceneRequest request = sampleRequest(1);

        // when: 用不存在的剧集 id 创建场景
        ResourceNotFoundException ex = assertThrows(
                ResourceNotFoundException.class,
                () -> sceneService.create(missingEpisodeId, request)
        );

        // then: 抛出 ResourceNotFoundException，且数据库没有写入任何场景
        assertEquals("Episode", ex.getResource());
        assertEquals(missingEpisodeId, ex.getId());
        assertEquals(0L, sceneRepository.count());
    }

    @Test
    void create_isIdempotentWhenCalledTwiceWithSamePayload() {
        // given: 同一份请求被提交两次（模拟客户端重试）
        SceneRequest request = sampleRequest(2);

        // when: 连续两次调用 create
        SceneResponse first = sceneService.create(savedEpisode.getId(), request);
        SceneResponse second = sceneService.create(savedEpisode.getId(), request);

        // then: 两次生成的记录各自独立、内容一致，总数为 2，id 不相同
        assertNotNull(first.id());
        assertNotNull(second.id());
        assertEquals(first.sceneNo(), second.sceneNo());
        assertEquals(first.location(), second.location());
        assertEquals(first.dialogue(), second.dialogue());
        assertEquals(2L, sceneRepository.count());
    }

    @Test
    void listByEpisode_returnsScenesOrderedBySceneNoAsc() {
        // given: 同一剧集下乱序插入三个场景
        sceneService.create(savedEpisode.getId(), sampleRequest(3));
        sceneService.create(savedEpisode.getId(), sampleRequest(1));
        sceneService.create(savedEpisode.getId(), sampleRequest(2));

        // when: 查询该剧集下的场景列表
        List<SceneResponse> list = sceneService.listByEpisode(savedEpisode.getId());

        // then: 数量为 3，且严格按 sceneNo 升序
        assertEquals(3, list.size());
        assertEquals(1, list.get(0).sceneNo());
        assertEquals(2, list.get(1).sceneNo());
        assertEquals(3, list.get(2).sceneNo());
    }

    @Test
    void listByEpisode_withNoScenes_returnsEmptyList() {
        // given: 该剧集下没有任何场景

        // when: 查询该剧集下的场景列表
        List<SceneResponse> list = sceneService.listByEpisode(savedEpisode.getId());

        // then: 返回空列表，数据库场景总数为 0
        assertNotNull(list);
        assertTrue(list.isEmpty());
        assertEquals(0L, sceneRepository.count());
    }

    @Test
    void update_overwritesAllMutableFields() {
        // given: 已存在一个场景，准备一份全新的请求体
        SceneResponse created = sceneService.create(savedEpisode.getId(), sampleRequest(1));
        SceneRequest updated = new SceneRequest(
                5,
                "火车站",
                "清晨",
                "两人告别",
                "保重",
                "wide shot, train station, dawn"
        );

        // when: 调用 update
        SceneResponse response = sceneService.update(created.id(), updated);

        // then: id 保持不变，其他字段全部被覆盖
        assertEquals(created.id(), response.id());
        assertEquals(savedEpisode.getId(), response.episodeId());
        assertEquals(5, response.sceneNo());
        assertEquals("火车站", response.location());
        assertEquals("清晨", response.timeOfDay());
        assertEquals("两人告别", response.description());
        assertEquals("保重", response.dialogue());
        assertEquals("wide shot, train station, dawn", response.prompt());
    }

    @Test
    void update_isIdempotentWhenCalledTwiceWithSamePayload() {
        // given: 一个已存在的场景和一份固定的更新请求
        SceneResponse created = sceneService.create(savedEpisode.getId(), sampleRequest(1));
        SceneRequest updated = sampleRequest(7);

        // when: 用同一份请求连续调用两次 update
        SceneResponse first = sceneService.update(created.id(), updated);
        SceneResponse second = sceneService.update(created.id(), updated);

        // then: 两次返回内容完全一致，数据库仍只有一条记录
        assertEquals(first.id(), second.id());
        assertEquals(first.sceneNo(), second.sceneNo());
        assertEquals(first.location(), second.location());
        assertEquals(first.dialogue(), second.dialogue());
        assertEquals(1L, sceneRepository.count());
    }

    @Test
    void update_withMissingScene_throwsResourceNotFound() {
        // given: 一个不存在的场景 id
        Long missingSceneId = 888888L;
        SceneRequest request = sampleRequest(1);

        // when: 用不存在的 id 调用 update
        ResourceNotFoundException ex = assertThrows(
                ResourceNotFoundException.class,
                () -> sceneService.update(missingSceneId, request)
        );

        // then: 抛出 ResourceNotFoundException，且数据库无新增记录
        assertEquals("Scene", ex.getResource());
        assertEquals(missingSceneId, ex.getId());
        assertEquals(0L, sceneRepository.count());
    }

    @Test
    void delete_removesSceneAndSubsequentReadIsEmpty() {
        // given: 已存在一个场景
        SceneResponse created = sceneService.create(savedEpisode.getId(), sampleRequest(1));

        // when: 调用 delete 删除该场景
        sceneService.delete(created.id());

        // then: 记录被删除，listByEpisode 返回空列表
        assertEquals(0L, sceneRepository.count());
        assertTrue(sceneService.listByEpisode(savedEpisode.getId()).isEmpty());
    }

    @Test
    void delete_isIdempotentWhenCalledTwice() {
        // given: 已存在一个场景，第一次删除会成功
        SceneResponse created = sceneService.create(savedEpisode.getId(), sampleRequest(1));
        sceneService.delete(created.id());

        // when: 再次删除同一个 id
        ResourceNotFoundException ex = assertThrows(
                ResourceNotFoundException.class,
                () -> sceneService.delete(created.id())
        );

        // then: 第二次抛出 ResourceNotFoundException，数据库仍为空
        assertEquals("Scene", ex.getResource());
        assertEquals(created.id(), ex.getId());
        assertEquals(0L, sceneRepository.count());
    }

    @Test
    void create_isolatesScenesAcrossEpisodes() {
        // given: 第二个剧集
        DramaProject otherProject = new DramaProject();
        otherProject.setTitle("另一个项目");
        otherProject = projectRepository.save(otherProject);
        Episode otherEpisode = new Episode();
        otherEpisode.setTitle("另一个剧集");
        otherEpisode.setProject(otherProject);
        otherEpisode.setEpisodeNo(2);
        Episode savedOther = episodeRepository.save(otherEpisode);
        sceneService.create(savedEpisode.getId(), sampleRequest(1));
        sceneService.create(savedEpisode.getId(), sampleRequest(2));
        sceneService.create(savedOther.getId(), sampleRequest(1));

        // when: 分别查询两个剧集下的场景
        List<SceneResponse> firstList = sceneService.listByEpisode(savedEpisode.getId());
        List<SceneResponse> secondList = sceneService.listByEpisode(savedOther.getId());

        // then: 两个剧集各自返回自己的场景，互不串台
        assertEquals(2, firstList.size());
        assertEquals(1, secondList.size());
        assertEquals(savedEpisode.getId(), firstList.get(0).episodeId());
        assertEquals(savedOther.getId(), secondList.get(0).episodeId());
        assertEquals(3L, sceneRepository.count());
    }

    @Test
    void create_withEmptyOptionalFields_persistsNulls() {
        // given: 一份只填必填字段、其余为 null 的请求
        SceneRequest sparse = new SceneRequest(1, "空旷街道", null, null, null, null);

        // when: 创建场景
        SceneResponse response = sceneService.create(savedEpisode.getId(), sparse);

        // then: 必填字段落库，可选字段保持 null
        assertNotNull(response.id());
        assertEquals("空旷街道", response.location());
        assertEquals(null, response.timeOfDay());
        assertEquals(null, response.description());
        assertEquals(null, response.dialogue());
        assertEquals(null, response.prompt());
    }

    @Test
    void create_withVeryLargePayload_storesFullContent() {
        // given: 一份超大的 dialogue 与 prompt（各 100000 字符）
        String bigDialogue = "对".repeat(1800);
        String bigPrompt = "p".repeat(1800);
        SceneRequest request = new SceneRequest(
                1,
                "大厅",
                "白天",
                "长篇独白",
                bigDialogue,
                bigPrompt
        );

        // when: 创建场景
        SceneResponse response = sceneService.create(savedEpisode.getId(), request);

        // then: 返回的字段长度与输入一致，且数据库里能读回完整内容
        assertNotNull(response.id());
        assertEquals(1800, response.dialogue().length());
        assertEquals(1800, response.prompt().length());
        SceneResponse reloaded = sceneService.listByEpisode(savedEpisode.getId()).get(0);
        assertEquals(bigDialogue, reloaded.dialogue());
        assertEquals(bigPrompt, reloaded.prompt());
    }

    @Test
    void create_withNegativeSceneNo_storesAsIs() {
        // given: 一份 sceneNo 为负数的请求（当前实现不做业务校验）
        SceneRequest request = sampleRequest(-3);

        // when: 创建场景
        SceneResponse response = sceneService.create(savedEpisode.getId(), request);

        // then: 返回值与输入一致，数据库里也存的是 -3
        assertEquals(-3, response.sceneNo());
        SceneResponse reloaded = sceneService.listByEpisode(savedEpisode.getId()).get(0);
        assertEquals(-3, reloaded.sceneNo());
    }

    @Test
    void update_withInvalidIdAndExistingData_doesNotAffectExistingScene() {
        // given: 已存在一个场景，同时准备一个不存在的 id
        SceneResponse created = sceneService.create(savedEpisode.getId(), sampleRequest(1));
        Long missingSceneId = 777777L;

        // when: 用不存在的 id 调用 update
        assertThrows(
                ResourceNotFoundException.class,
                () -> sceneService.update(missingSceneId, sampleRequest(9))
        );

        // then: 原有场景不受影响，字段保持原值
        List<SceneResponse> list = sceneService.listByEpisode(savedEpisode.getId());
        assertEquals(1, list.size());
        assertEquals(created.id(), list.get(0).id());
        assertEquals(1, list.get(0).sceneNo());
        assertEquals("咖啡馆", list.get(0).location());
    }

    @Test
    void delete_withMissingScene_throwsResourceNotFound() {
        // given: 一个不存在的场景 id
        Long missingSceneId = 666666L;

        // when: 调用 delete
        ResourceNotFoundException ex = assertThrows(
                ResourceNotFoundException.class,
                () -> sceneService.delete(missingSceneId)
        );

        // then: 抛出 ResourceNotFoundException，数据库无变化
        assertEquals("Scene", ex.getResource());
        assertEquals(missingSceneId, ex.getId());
        assertEquals(0L, sceneRepository.count());
    }

    @Test
    void createThenUpdateThenList_reflectsLatestState() {
        // given: 先创建一个场景，再准备一份更新请求
        SceneResponse created = sceneService.create(savedEpisode.getId(), sampleRequest(1));
        SceneRequest updated = new SceneRequest(
                1,
                "天台",
                "黄昏",
                "两人并肩看落日",
                "以后怎么办",
                "rooftop, sunset, two people"
        );

        // when: 更新后再查询列表
        sceneService.update(created.id(), updated);
        List<SceneResponse> list = sceneService.listByEpisode(savedEpisode.getId());

        // then: 列表里返回的是更新后的内容，数量仍为 1
        assertEquals(1, list.size());
        assertEquals(created.id(), list.get(0).id());
        assertEquals("天台", list.get(0).location());
        assertEquals("黄昏", list.get(0).timeOfDay());
        assertEquals("以后怎么办", list.get(0).dialogue());
    }
}