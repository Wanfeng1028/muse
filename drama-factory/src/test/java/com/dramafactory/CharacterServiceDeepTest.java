package com.dramafactory;

import com.dramafactory.dto.Records.CharacterRequest;
import com.dramafactory.dto.Records.CharacterResponse;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.CharacterRole;
import com.dramafactory.model.DramaCharacter;
import com.dramafactory.model.DramaProject;
import com.dramafactory.repository.DramaCharacterRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.service.CharacterService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.SpyBean;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.springframework.dao.DataIntegrityViolationException;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

@SpringBootTest
@ActiveProfiles("test")
class CharacterServiceDeepTest {

    @Autowired
    private CharacterService characterService;

    @Autowired
    private DramaProjectRepository projectRepository;

    @Autowired
    private DramaCharacterRepository characterRepository;

    @SpyBean
    private DramaCharacterRepository spyCharacterRepository;

    private DramaProject project;

    @BeforeEach
    void setUp() {
        characterRepository.deleteAll();
        projectRepository.deleteAll();
        project = new DramaProject();
        project.setTitle("测试项目A");
        project.setSynopsis("用于角色服务的深度测试");
        project = projectRepository.save(project);
    }

    @Test
    void createThenList_shouldReturnPersistedCharacterInIdAscOrder() {
        // given
        CharacterRequest first = new CharacterRequest("张三", CharacterRole.LEAD, "主角", "勇敢,聪明");
        CharacterRequest second = new CharacterRequest("李四", CharacterRole.SUPPORTING, "配角", "搞笑");

        // when
        CharacterResponse createdFirst = characterService.create(project.getId(), first);
        CharacterResponse createdSecond = characterService.create(project.getId(), second);
        List<CharacterResponse> listed = characterService.listByProject(project.getId());

        // then
        assertThat(listed).hasSize(2);
        assertThat(listed.get(0).id()).isEqualTo(createdFirst.id());
        assertThat(listed.get(1).id()).isEqualTo(createdSecond.id());
        assertThat(listed.get(0).name()).isEqualTo("张三");
        assertThat(listed.get(1).role()).isEqualTo(CharacterRole.SUPPORTING);
    }

    @Test
    void create_shouldThrowResourceNotFound_whenProjectMissing() {
        // given
        Long missingProjectId = project.getId() + 9999L;
        CharacterRequest request = new CharacterRequest("王五", CharacterRole.LEAD, "desc", "traits");

        // when / then
        assertThatThrownBy(() -> characterService.create(missingProjectId, request))
                .isInstanceOf(ResourceNotFoundException.class)
                .hasMessageContaining("Project");
        assertThat(characterRepository.count()).isZero();
    }

    @Test
    void update_shouldOverwriteFields_andKeepId() {
        // given
        CharacterResponse created = characterService.create(
                project.getId(),
                new CharacterRequest("原名", CharacterRole.SUPPORTING, "旧描述", "旧标签"));
        CharacterRequest updateReq = new CharacterRequest("新名", CharacterRole.LEAD, "新描述", "新标签");

        // when
        CharacterResponse updated = characterService.update(created.id(), updateReq);

        // then
        assertThat(updated.id()).isEqualTo(created.id());
        assertThat(updated.name()).isEqualTo("新名");
        assertThat(updated.role()).isEqualTo(CharacterRole.LEAD);
        assertThat(updated.description()).isEqualTo("新描述");
        assertThat(updated.traits()).isEqualTo("新标签");
        assertThat(updated.projectId()).isEqualTo(project.getId());
    }

    @Test
    void update_shouldKeepRole_whenRoleIsNull() {
        // given
        CharacterResponse created = characterService.create(
                project.getId(),
                new CharacterRequest("保留角色", CharacterRole.LEAD, "desc", "traits"));
        CharacterRequest updateReq = new CharacterRequest("只改名", null, "desc2", "traits2");

        // when
        CharacterResponse updated = characterService.update(created.id(), updateReq);

        // then
        assertThat(updated.role()).isEqualTo(CharacterRole.LEAD);
        assertThat(updated.name()).isEqualTo("只改名");
        assertThat(updated.description()).isEqualTo("desc2");
    }

    @Test
    void delete_shouldBeIdempotentForSecondCall_throwsNotFound() {
        // given
        CharacterResponse created = characterService.create(
                project.getId(),
                new CharacterRequest("待删", CharacterRole.SUPPORTING, "d", "t"));

        // when
        characterService.delete(created.id());

        // then
        assertThat(characterRepository.existsById(created.id())).isFalse();
        assertThatThrownBy(() -> characterService.delete(created.id()))
                .isInstanceOf(ResourceNotFoundException.class)
                .hasMessageContaining("Character");
    }

    @Test
    void listByProject_shouldThrow_whenProjectMissing() {
        // given
        Long missingProjectId = project.getId() + 12345L;

        // when / then
        assertThatThrownBy(() -> characterService.listByProject(missingProjectId))
                .isInstanceOf(ResourceNotFoundException.class)
                .hasMessageContaining("Project");
        assertThat(characterRepository.findByProjectIdOrderByIdAsc(missingProjectId)).isEmpty();
    }

    @Test
    void listByProject_shouldReturnEmpty_whenNoCharacters() {
        // given
        // 项目已存在但没有任何角色

        // when
        List<CharacterResponse> listed = characterService.listByProject(project.getId());

        // then
        assertThat(listed).isNotNull();
        assertThat(listed).isEmpty();
    }

    @Test
    void create_shouldDefaultToSupporting_whenRoleIsNull() {
        // given
        CharacterRequest request = new CharacterRequest("默认角色", null, "desc", "traits");

        // when
        CharacterResponse created = characterService.create(project.getId(), request);

        // then
        assertThat(created.role()).isEqualTo(CharacterRole.SUPPORTING);
        assertThat(created.name()).isEqualTo("默认角色");
        assertThat(created.projectId()).isEqualTo(project.getId());
    }

    @Test
    void create_shouldRollbackAndPropagateError_whenRepositorySaveFails() {
        // given
        CharacterRequest request = new CharacterRequest("触发失败", CharacterRole.LEAD, "d", "t");
        long before = characterRepository.count();
        doThrow(new DataIntegrityViolationException("模拟保存失败"))
                .when(spyCharacterRepository).save(any(DramaCharacter.class));

        // when / then
        assertThatThrownBy(() -> characterService.create(project.getId(), request))
                .isInstanceOf(DataIntegrityViolationException.class)
                .hasMessageContaining("模拟保存失败");
        assertThat(characterRepository.count()).isEqualTo(before);
        verify(spyCharacterRepository, times(1)).save(any(DramaCharacter.class));
    }

    @Test
    void update_shouldThrowAndNotChange_whenRepositorySaveFails() {
        // given
        CharacterResponse created = characterService.create(
                project.getId(),
                new CharacterRequest("原值", CharacterRole.SUPPORTING, "原描述", "原标签"));
        CharacterRequest updateReq = new CharacterRequest("新值", CharacterRole.LEAD, "新描述", "新标签");
        doThrow(new DataAccessException("模拟更新失败") {})
                .when(spyCharacterRepository).save(any(DramaCharacter.class));

        // when / then
        assertThatThrownBy(() -> characterService.update(created.id(), updateReq))
                .isInstanceOf(DataAccessException.class)
                .hasMessageContaining("模拟更新失败");
        DramaCharacter reloaded = characterRepository.findById(created.id()).orElseThrow();
        assertThat(reloaded.getName()).isEqualTo("原值");
        assertThat(reloaded.getRole()).isEqualTo(CharacterRole.SUPPORTING);
    }

    @Test
    void concurrentCreate_onSameProject_shouldPersistAllWithoutDataCorruption() throws Exception {
        // given
        int threads = 2;
        int perThread = 5;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch startGate = new CountDownLatch(1);
        CountDownLatch doneGate = new CountDownLatch(threads);
        AtomicInteger successCount = new AtomicInteger();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        // when
        for (int t = 0; t < threads; t++) {
            final int threadIndex = t;
            pool.submit(() -> {
                try {
                    startGate.await();
                    for (int i = 0; i < perThread; i++) {
                        CharacterRequest req = new CharacterRequest(
                                "并发-" + threadIndex + "-" + i,
                                CharacterRole.SUPPORTING,
                                "desc",
                                "traits");
                        characterService.create(project.getId(), req);
                        successCount.incrementAndGet();
                    }
                } catch (Throwable ex) {
                    failure.compareAndSet(null, ex);
                } finally {
                    doneGate.countDown();
                }
            });
        }
        startGate.countDown();
        boolean finished = doneGate.await(30, TimeUnit.SECONDS);
        pool.shutdownNow();

        // then
        assertThat(finished).isTrue();
        assertThat(failure.get()).isNull();
        assertThat(successCount.get()).isEqualTo(threads * perThread);
        List<CharacterResponse> listed = characterService.listByProject(project.getId());
        assertThat(listed).hasSize(threads * perThread);
        assertThat(listed.stream().map(CharacterResponse::id).distinct().count())
                .isEqualTo(threads * perThread);
    }

    @Test
    void create_shouldHandleLargePayload_withoutTruncation() {
        // given
        String desc1000 = "描".repeat(1000);
        String traits255 = "t".repeat(255);

        // when
        CharacterResponse created = characterService.create(project.getId(),
                new CharacterRequest("边界内", CharacterRole.LEAD, desc1000, traits255));

        // then
        assertThat(created.description()).isEqualTo(desc1000);
        assertThat(created.traits()).isEqualTo(traits255);
        DramaCharacter reloaded = characterRepository.findById(created.id()).orElseThrow();
        assertThat(reloaded.getDescription()).isEqualTo(desc1000);
        assertThat(reloaded.getTraits()).isEqualTo(traits255);

        // given
        String over1000 = "描".repeat(1001);
        String over255 = "t".repeat(256);

        // when / then
        assertThatThrownBy(() -> characterService.create(project.getId(),
                new CharacterRequest("描述越界", CharacterRole.LEAD, over1000, "ok")))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThatThrownBy(() -> characterService.create(project.getId(),
                new CharacterRequest("性格越界", CharacterRole.LEAD, "ok", over255)))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void update_shouldThrowResourceNotFound_whenCharacterMissing() {
        // given
        Long missingId = 999_999L;
        CharacterRequest updateReq = new CharacterRequest("x", CharacterRole.LEAD, "d", "t");

        // when / then
        assertThatThrownBy(() -> characterService.update(missingId, updateReq))
                .isInstanceOf(ResourceNotFoundException.class)
                .hasMessageContaining("Character");
        assertThat(characterRepository.findById(missingId)).isEmpty();
    }

    @Test
    void toResponse_shouldCarryCreatedAtAndUpdatedAt() {
        // given
        CharacterRequest request = new CharacterRequest("时间戳", CharacterRole.SUPPORTING, "d", "t");

        // when
        CharacterResponse created = characterService.create(project.getId(), request);

        // then
        assertThat(created.createdAt()).isNotNull();
        assertThat(created.updatedAt()).isNotNull();
        assertThat(created.createdAt()).isInstanceOf(LocalDateTime.class);
    }

    @Test
    void delete_shouldRemoveOnlyTargetCharacter_andKeepOthers() {
        // given
        CharacterResponse a = characterService.create(
                project.getId(), new CharacterRequest("A", CharacterRole.LEAD, "d", "t"));
        CharacterResponse b = characterService.create(
                project.getId(), new CharacterRequest("B", CharacterRole.SUPPORTING, "d", "t"));

        // when
        characterService.delete(a.id());

        // then
        assertThat(characterRepository.existsById(a.id())).isFalse();
        Optional<DramaCharacter> remaining = characterRepository.findById(b.id());
        assertThat(remaining).isPresent();
        assertThat(remaining.get().getName()).isEqualTo("B");
        assertThat(characterService.listByProject(project.getId())).hasSize(1);
    }
}