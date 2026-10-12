package com.dramafactory.service;

import com.dramafactory.dto.Records.CharacterRequest;
import com.dramafactory.dto.Records.CharacterResponse;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.CharacterRole;
import com.dramafactory.model.DramaCharacter;
import com.dramafactory.model.DramaProject;
import com.dramafactory.repository.DramaCharacterRepository;
import com.dramafactory.repository.DramaProjectRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * 角色业务服务：负责项目下角色的增删改查。
 */
@Service
public class CharacterService {

    private final DramaCharacterRepository characterRepository;
    private final DramaProjectRepository projectRepository;

    // 构造器注入
    public CharacterService(DramaCharacterRepository characterRepository,
                            DramaProjectRepository projectRepository) {
        this.characterRepository = characterRepository;
        this.projectRepository = projectRepository;
    }

    /**
     * 在指定项目下创建角色。
     */
    @Transactional
    public CharacterResponse create(Long projectId, CharacterRequest request) {
        DramaProject project = projectRepository.findById(projectId)
                .orElseThrow(() -> new ResourceNotFoundException("Project", projectId));

        DramaCharacter character = new DramaCharacter();
        character.setProject(project);
        character.setName(request.name());
        character.setRole(request.role() != null ? request.role() : CharacterRole.SUPPORTING);
        character.setDescription(request.description());
        character.setTraits(request.traits());

        DramaCharacter saved = characterRepository.save(character);
        return toResponse(saved);
    }

    /**
     * 查询指定项目下的角色列表，按 id 升序。
     */
    @Transactional(readOnly = true)
    public List<CharacterResponse> listByProject(Long projectId) {
        if (!projectRepository.existsById(projectId)) {
            throw new ResourceNotFoundException("Project", projectId);
        }
        return characterRepository.findByProjectIdOrderByIdAsc(projectId)
                .stream()
                .map(this::toResponse)
                .toList();
    }

    /**
     * 更新角色信息。
     */
    @Transactional
    public CharacterResponse update(Long id, CharacterRequest request) {
        DramaCharacter character = characterRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Character", id));

        character.setName(request.name());
        if (request.role() != null) {
            character.setRole(request.role());
        }
        character.setDescription(request.description());
        character.setTraits(request.traits());

        DramaCharacter saved = characterRepository.save(character);
        return toResponse(saved);
    }

    /**
     * 删除角色。
     */
    @Transactional
    public void delete(Long id) {
        if (!characterRepository.existsById(id)) {
            throw new ResourceNotFoundException("Character", id);
        }
        characterRepository.deleteById(id);
    }

    /**
     * 实体转 DTO。
     */
    private CharacterResponse toResponse(DramaCharacter character) {
        return new CharacterResponse(
                character.getId(),
                character.getProject() != null ? character.getProject().getId() : null,
                character.getName(),
                character.getRole(),
                character.getDescription(),
                character.getTraits(),
                character.getCreatedAt(),
                character.getUpdatedAt()
        );
    }
}
