package com.dramafactory.service;

import com.dramafactory.dto.Records.ProjectRequest;
import com.dramafactory.dto.Records.ProjectResponse;
import com.dramafactory.dto.Records.StatsResponse;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.ProjectStatus;
import com.dramafactory.repository.DramaCharacterRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;

/**
 * 项目服务：负责短剧项目的增删改查与全局统计。
 */
@Service
public class ProjectService {

    private final DramaProjectRepository projectRepository;
    private final EpisodeRepository episodeRepository;
    private final DramaCharacterRepository characterRepository;
    private final SceneRepository sceneRepository;

    public ProjectService(DramaProjectRepository projectRepository,
                          EpisodeRepository episodeRepository,
                          DramaCharacterRepository characterRepository,
                          SceneRepository sceneRepository) {
        this.projectRepository = projectRepository;
        this.episodeRepository = episodeRepository;
        this.characterRepository = characterRepository;
        this.sceneRepository = sceneRepository;
    }

    /** 创建项目，status 默认 DRAFT，targetEpisodes 默认 20 */
    @Transactional
    public ProjectResponse create(ProjectRequest request) {
        DramaProject project = new DramaProject();
        project.setTitle(request.title());
        project.setGenre(request.genre());
        project.setSynopsis(request.synopsis());
        project.setStatus(request.status() != null ? request.status() : ProjectStatus.DRAFT);
        project.setTargetEpisodes(request.targetEpisodes() != null ? request.targetEpisodes() : 20);
        DramaProject saved = projectRepository.save(project);
        return toResponse(saved);
    }

    /** 按 id 查询项目 */
    @Transactional(readOnly = true)
    public ProjectResponse get(Long id) {
        DramaProject project = projectRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Project", id));
        return toResponse(project);
    }

    /** 列出全部项目（按 id 升序） */
    @Transactional(readOnly = true)
    public List<ProjectResponse> list() {
        List<DramaProject> projects = projectRepository.findAll(Sort.by("id"));
        List<ProjectResponse> result = new ArrayList<>(projects.size());
        for (DramaProject project : projects) {
            result.add(toResponse(project));
        }
        return result;
    }

    /** 更新项目 */
    @Transactional
    public ProjectResponse update(Long id, ProjectRequest request) {
        DramaProject project = projectRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Project", id));
        project.setTitle(request.title());
        project.setGenre(request.genre());
        project.setSynopsis(request.synopsis());
        if (request.status() != null) {
            project.setStatus(request.status());
        }
        if (request.targetEpisodes() != null) {
            project.setTargetEpisodes(request.targetEpisodes());
        }
        DramaProject saved = projectRepository.save(project);
        return toResponse(saved);
    }

    /** 删除项目 */
    @Transactional
    public void delete(Long id) {
        DramaProject project = projectRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Project", id));
        projectRepository.delete(project);
    }

    /** 全局统计：四张表的记录数 */
    @Transactional(readOnly = true)
    public StatsResponse stats() {
        long projects = projectRepository.count();
        long episodes = episodeRepository.count();
        long characters = characterRepository.count();
        long scenes = sceneRepository.count();
        return new StatsResponse(projects, episodes, characters, scenes);
    }

    /** 实体转响应 DTO，填充关联计数 */
    private ProjectResponse toResponse(DramaProject project) {
        long episodeCount = episodeRepository.countByProjectId(project.getId());
        long characterCount = characterRepository.countByProjectId(project.getId());
        return new ProjectResponse(
                project.getId(),
                project.getTitle(),
                project.getGenre(),
                project.getSynopsis(),
                project.getStatus(),
                project.getTargetEpisodes(),
                episodeCount,
                characterCount,
                project.getCreatedAt(),
                project.getUpdatedAt()
        );
    }
}
