package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.Scene;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * 剧本生成服务（v2.3）。
 *
 * <p>支持两种生成模式：</p>
 * <ul>
 *     <li>{@code ai}：调用真实大模型生成，失败自动降级为模板生成（source=template-fallback）；</li>
 *     <li>{@code template}：直接使用模板生成器（{@link ScriptGenerator}）。</li>
 * </ul>
 */
@Service
public class ScriptService {

    private static final Logger log = LoggerFactory.getLogger(ScriptService.class);

    private final EpisodeRepository episodeRepository;
    private final SceneRepository sceneRepository;
    private final LlmScriptService llmScriptService;
    private final CharacterService characterService;

    private final ScriptGenerator scriptGenerator = new ScriptGenerator();

    /**
     * 构造器。
     *
     * @param episodeRepository  剧集仓库
     * @param sceneRepository    场景仓库
     * @param llmScriptService   大模型剧本生成服务
     * @param characterService   角色服务
     */
    public ScriptService(EpisodeRepository episodeRepository,
                         SceneRepository sceneRepository,
                         LlmScriptService llmScriptService,
                         CharacterService characterService) {
        this.episodeRepository = episodeRepository;
        this.sceneRepository = sceneRepository;
        this.llmScriptService = llmScriptService;
        this.characterService = characterService;
    }

    /**
     * 生成剧本（默认 ai 模式，兼容旧调用）。
     *
     * @param episodeId 剧集 ID
     * @return 生成结果
     */
    public Records.GenerateScriptResponse generate(Long episodeId) {
        return generate(episodeId, "ai");
    }

    /**
     * 生成剧本。
     *
     * @param episodeId 剧集 ID
     * @param mode      生成模式：{@code ai} 或 {@code template}
     * @return 生成结果
     */
    @Transactional
    public Records.GenerateScriptResponse generate(Long episodeId, String mode) {
        if (!"ai".equals(mode) && !"template".equals(mode)) {
            throw new IllegalArgumentException("mode 只能是 ai 或 template");
        }

        Episode episode = episodeRepository.findById(episodeId)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", episodeId));

        sceneRepository.deleteByEpisodeId(episodeId);

        long t0 = System.currentTimeMillis();
        List<ScriptGenerator.SceneDraft> drafts;
        String source;
        String usedModel = null;

        if ("ai".equals(mode)) {
            String charactersSummary = buildCharactersSummary(episode);
            try {
                LlmScriptService.LlmScriptResult result = llmScriptService.generate(episode, charactersSummary);
                drafts = result.scenes();
                source = "ai";
                usedModel = result.model();
            } catch (LlmScriptUnavailableException e) {
                log.warn("AI 剧本生成失败，降级为模板生成：{}", e.getMessage());
                drafts = scriptGenerator.generate(episode);
                source = "template-fallback";
            }
        } else {
            drafts = scriptGenerator.generate(episode);
            source = "template";
        }

        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < drafts.size(); i++) {
            ScriptGenerator.SceneDraft draft = drafts.get(i);

            Scene scene = new Scene();
            scene.setEpisode(episode);
            scene.setSceneNo(draft.sceneNo());
            scene.setLocation(draft.location());
            scene.setTimeOfDay(draft.timeOfDay());
            scene.setDescription(draft.description());
            scene.setDialogue(draft.dialogue());
            scene.setPrompt(draft.prompt());
            sceneRepository.save(scene);

            if (i > 0) {
                sb.append("\n\n");
            }
            sb.append("【第").append(draft.sceneNo()).append("场】")
                    .append(draft.location()).append(" · ").append(draft.timeOfDay())
                    .append("\n画面：").append(draft.description())
                    .append("\n对白：").append(draft.dialogue())
                    .append("\n生成提示词：").append(draft.prompt());
        }

        episode.setStatus(EpisodeStatus.SCRIPTED);
        episodeRepository.save(episode);

        long latencyMs = System.currentTimeMillis() - t0;
        return new Records.GenerateScriptResponse(episodeId, drafts.size(), sb.toString(), source, usedModel, latencyMs);
    }

    /**
     * 构造角色摘要，取前 10 个角色拼 "姓名（身份/小传）"。
     * 任何异常不影响主流程，仅记 warn 并返回空字符串。
     *
     * @param episode 剧集
     * @return 角色摘要，失败或为空返回空字符串
     */
    private String buildCharactersSummary(Episode episode) {
        try {
            if (episode.getProject() == null) {
                return "";
            }
            Long projectId = episode.getProject().getId();
            if (projectId == null) {
                return "";
            }
            List<Records.CharacterResponse> characters = characterService.listByProject(projectId);
            if (characters == null || characters.isEmpty()) {
                return "";
            }
            StringBuilder sb = new StringBuilder();
            int limit = Math.min(10, characters.size());
            for (int i = 0; i < limit; i++) {
                Records.CharacterResponse c = characters.get(i);
                if (i > 0) {
                    sb.append("；");
                }
                sb.append(c.name());
                String desc = c.description();
                if (desc != null && !desc.isBlank()) {
                    sb.append("（").append(desc).append("）");
                }
            }
            return sb.toString();
        } catch (RuntimeException e) {
            log.warn("构造角色摘要失败，忽略：{}", e.getMessage());
            return "";
        }
    }
}

