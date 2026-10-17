// 文件：src/test/java/com/dramafactory/service/CharacterServiceV229Test.java

package com.dramafactory.service;

import com.dramafactory.dto.Records.CharacterRequest;
import com.dramafactory.dto.Records.CharacterResponse;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.CharacterRole;
import com.dramafactory.model.DramaCharacter;
import com.dramafactory.model.DramaProject;
import com.dramafactory.repository.DramaCharacterRepository;
import com.dramafactory.repository.DramaProjectRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * CharacterService 分支覆盖补齐测试（C5）。纯 Mockito，无 Spring 上下文。
 */
@ExtendWith(MockitoExtension.class)
class CharacterServiceV229Test {

    @Mock
    private DramaCharacterRepository characterRepository;

    @Mock
    private DramaProjectRepository projectRepository;

    private CharacterService characterService;

    @BeforeEach
    void setUp() {
        characterService = new CharacterService(characterRepository, projectRepository);
    }

    @Test
    @DisplayName("create：项目不存在时抛 ResourceNotFoundException")
    void createProjectNotFound() {
        when(projectRepository.findById(99L)).thenReturn(Optional.empty());

        CharacterRequest request = new CharacterRequest("小明", CharacterRole.SUPPORTING, "描述", "特征");

        assertThatThrownBy(() -> characterService.create(99L, request))
                .isInstanceOf(ResourceNotFoundException.class);

        verify(characterRepository, never()).save(any());
    }

    @Test
    @DisplayName("create：role 为 null 时默认 SUPPORTING，并正常返回 response")
    void createDefaultsRoleToSupporting() {
        DramaProject project = new DramaProject();
        project.setId(1L);
        when(projectRepository.findById(1L)).thenReturn(Optional.of(project));

        DramaCharacter saved = new DramaCharacter();
        saved.setId(10L);
        saved.setProject(project);
        saved.setName("小明");
        saved.setRole(CharacterRole.SUPPORTING);
        saved.setDescription("描述");
        saved.setTraits("特征");
        saved.setCreatedAt(LocalDateTime.of(2026, 1, 1, 0, 0));
        saved.setUpdatedAt(LocalDateTime.of(2026, 1, 2, 0, 0));
        when(characterRepository.save(any(DramaCharacter.class))).thenReturn(saved);

        CharacterRequest request = new CharacterRequest("小明", null, "描述", "特征");

        CharacterResponse response = characterService.create(1L, request);

        assertThat(response.id()).isEqualTo(10L);
        assertThat(response.projectId()).isEqualTo(1L);
        assertThat(response.name()).isEqualTo("小明");
        assertThat(response.role()).isEqualTo(CharacterRole.SUPPORTING);
        assertThat(response.description()).isEqualTo("描述");
        assertThat(response.traits()).isEqualTo("特征");
        assertThat(response.createdAt()).isEqualTo(LocalDateTime.of(2026, 1, 1, 0, 0));
        assertThat(response.updatedAt()).isEqualTo(LocalDateTime.of(2026, 1, 2, 0, 0));
    }

    @Test
    @DisplayName("listByProject：项目不存在时抛 ResourceNotFoundException")
    void listByProjectNotFound() {
        when(projectRepository.existsById(42L)).thenReturn(false);

        assertThatThrownBy(() -> characterService.listByProject(42L))
                .isInstanceOf(ResourceNotFoundException.class);

        verify(characterRepository, never()).findByProjectIdOrderByIdAsc(any());
    }

    @Test
    @DisplayName("listByProject：项目存在时返回映射后的列表")
    void listByProjectReturnsList() {
        when(projectRepository.existsById(1L)).thenReturn(true);

        DramaProject project = new DramaProject();
        project.setId(1L);

        DramaCharacter c1 = new DramaCharacter();
        c1.setId(11L);
        c1.setProject(project);
        c1.setName("A");
        c1.setRole(CharacterRole.SUPPORTING);

        DramaCharacter c2 = new DramaCharacter();
        c2.setId(12L);
        c2.setProject(project);
        c2.setName("B");
        c2.setRole(CharacterRole.SUPPORTING);

        when(characterRepository.findByProjectIdOrderByIdAsc(1L)).thenReturn(List.of(c1, c2));

        List<CharacterResponse> result = characterService.listByProject(1L);

        assertThat(result).hasSize(2);
        assertThat(result.get(0).id()).isEqualTo(11L);
        assertThat(result.get(0).name()).isEqualTo("A");
        assertThat(result.get(1).id()).isEqualTo(12L);
        assertThat(result.get(1).name()).isEqualTo("B");
    }

    @Test
    @DisplayName("update：id 不存在时抛 ResourceNotFoundException")
    void updateNotFound() {
        when(characterRepository.findById(7L)).thenReturn(Optional.empty());

        CharacterRequest request = new CharacterRequest("新名", CharacterRole.SUPPORTING, "d", "t");

        assertThatThrownBy(() -> characterService.update(7L, request))
                .isInstanceOf(ResourceNotFoundException.class);

        verify(characterRepository, never()).save(any());
    }

    @Test
    @DisplayName("update：role 为 null 时保持原 role")
    void updateKeepsRoleWhenNull() {
        DramaProject project = new DramaProject();
        project.setId(1L);

        DramaCharacter existing = new DramaCharacter();
        existing.setId(5L);
        existing.setProject(project);
        existing.setName("旧名");
        existing.setRole(CharacterRole.SUPPORTING);

        when(characterRepository.findById(5L)).thenReturn(Optional.of(existing));
        when(characterRepository.save(existing)).thenReturn(existing);

        CharacterRequest request = new CharacterRequest("新名", null, "新描述", "新特征");

        CharacterResponse response = characterService.update(5L, request);

        assertThat(existing.getRole()).isEqualTo(CharacterRole.SUPPORTING);
        assertThat(response.name()).isEqualTo("新名");
        assertThat(response.description()).isEqualTo("新描述");
        assertThat(response.traits()).isEqualTo("新特征");
    }

    @Test
    @DisplayName("update：role 非 null 时更新为新 role")
    void updateAppliesNewRole() {
        DramaProject project = new DramaProject();
        project.setId(1L);

        DramaCharacter existing = new DramaCharacter();
        existing.setId(5L);
        existing.setProject(project);
        existing.setName("旧名");
        existing.setRole(CharacterRole.SUPPORTING);

        when(characterRepository.findById(5L)).thenReturn(Optional.of(existing));
        when(characterRepository.save(existing)).thenReturn(existing);

        CharacterRequest request = new CharacterRequest("新名", CharacterRole.SUPPORTING, "d", "t");

        CharacterResponse response = characterService.update(5L, request);

        assertThat(existing.getRole()).isEqualTo(CharacterRole.SUPPORTING);
        assertThat(response.role()).isEqualTo(CharacterRole.SUPPORTING);
        assertThat(response.name()).isEqualTo("新名");
    }

    @Test
    @DisplayName("delete：id 不存在时抛 ResourceNotFoundException")
    void deleteNotFound() {
        when(characterRepository.existsById(3L)).thenReturn(false);

        assertThatThrownBy(() -> characterService.delete(3L))
                .isInstanceOf(ResourceNotFoundException.class);

        verify(characterRepository, never()).deleteById(any());
    }

    @Test
    @DisplayName("delete：id 存在时调用 deleteById")
    void deleteExisting() {
        when(characterRepository.existsById(3L)).thenReturn(true);

        characterService.delete(3L);

        verify(characterRepository).deleteById(3L);
    }

    @Test
    @DisplayName("toResponse：character.getProject() 为 null 时 projectId 为 null")
    void toResponseNullProject() {
        DramaCharacter saved = new DramaCharacter();
        saved.setId(20L);
        saved.setProject(null);
        saved.setName("孤儿");
        saved.setRole(CharacterRole.SUPPORTING);

        when(projectRepository.findById(1L)).thenReturn(Optional.of(new DramaProject()));
        when(characterRepository.save(any(DramaCharacter.class))).thenReturn(saved);

        CharacterRequest request = new CharacterRequest("孤儿", CharacterRole.SUPPORTING, null, null);

        CharacterResponse response = characterService.create(1L, request);

        assertThat(response.id()).isEqualTo(20L);
        assertThat(response.projectId()).isNull();
        assertThat(response.name()).isEqualTo("孤儿");
    }
}

