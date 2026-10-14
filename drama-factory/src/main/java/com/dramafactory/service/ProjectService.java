package com.dramafactory.service;

import com.dramafactory.config.CurrentUser;
import com.dramafactory.dto.Records.ProjectRequest;
import com.dramafactory.dto.Records.ProjectResponse;
import com.dramafactory.dto.Records.StatsResponse;
import com.dramafactory.exception.ForbiddenException;
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
 *
 * <p>v2.6 多用户地基：Episode / Scene / Shot / VideoTask / FinalCut / Run 这些子实体
 * 本轮不加 owner，它们只能经由项目 API 访问，项目级隔离即覆盖整个 API 面。
 */
@Service
public class ProjectService {

    private final DramaProjectRepository projectRepository;
    private final EpisodeRepository episodeRepository;
    private final DramaCharacterRepository characterRepository;
    private final SceneRepository sceneRepository;
    private final CurrentUser currentUser;

    public ProjectService(DramaProjectRepository projectRepository,
                          EpisodeRepository episodeRepository,
                          DramaCharacterRepository characterRepository,
                          SceneRepository sceneRepository,
                          CurrentUser currentUser) {
        this.projectRepository = projectRepository;
        this.episodeRepository = episodeRepository;
        this.characterRepository = characterRepository;
        this.sceneRepository = sceneRepository;
        this.currentUser = currentUser;
    }

    /** 创建项目，status 默认 DRAFT，targetEpisodes 默认 20；归属当前用户 */
    @Transactional
    public ProjectResponse create(ProjectRequest request) {
        DramaProject project = new DramaProject();
        project.setTitle(request.title());
        project.setGenre(request.genre());
        project.setSynopsis(request.synopsis());
        project.setStatus(request.status() != null ? request.status() : ProjectStatus.DRAFT);
        project.setTargetEpisodes(request.targetEpisodes() != null ? request.targetEpisodes() : 20);
        project.setOwnerId(currentUser.currentUserId());
        DramaProject saved = projectRepository.save(project);
        return toResponse(saved);
    }

    /** 按 id 查询项目：只能看自己的，别人的返回 403 */
    @Transactional(readOnly = true)
    public ProjectResponse get(Long id) {
        return toResponse(requireOwnedProject(id));
    }

    /** 列出当前用户的项目（按 id 升序） */
    @Transactional(readOnly = true)
    public List<ProjectResponse> list() {
        List<DramaProject> projects = projectRepository.findByOwnerId(currentUser.currentUserId(), Sort.by("id"));
        List<ProjectResponse> result = new ArrayList<>(projects.size());
        for (DramaProject project : projects) {
            result.add(toResponse(project));
        }
        return result;
    }

    /** 更新项目：只能改自己的 */
    @Transactional
    public ProjectResponse update(Long id, ProjectRequest request) {
        DramaProject project = requireOwnedProject(id);
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

    /** 删除项目：只能删自己的 */
    @Transactional
    public void delete(Long id) {
        DramaProject project = requireOwnedProject(id);
        projectRepository.delete(project);
    }

    /**
     * 按当前用户隔离统计：只统计当前用户名下项目及其剧集/角色/场景数。
     *
     * <p>开放模式下 currentUserId() 恒为 "local"，与旧全局口径行为一致；用户无项目时全 0。
     */
    @Transactional(readOnly = true)
    public StatsResponse stats() {
        String ownerId = currentUser.currentUserId();
        long projectCount = projectRepository.countByOwnerId(ownerId);
        long episodeCount = episodeRepository.countByOwner(ownerId);
        long characterCount = characterRepository.countByOwner(ownerId);
        long sceneCount = sceneRepository.countByOwner(ownerId);
        return new StatsResponse(projectCount, episodeCount, characterCount, sceneCount);
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
                project.getUpdatedAt(),
                project.getOwnerId()
        );
    }

    /** 按 id 取项目并校验归属：不存在→404，不是自己的→403 */
    private DramaProject requireOwnedProject(Long id) {
        DramaProject project = projectRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Project", id));
        if (!currentUser.currentUserId().equals(project.getOwnerId())) {
            throw new ForbiddenException("Project", id);
        }
        return project;
    }
}
