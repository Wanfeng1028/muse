package com.dramafactory.service;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.Scene;
import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
public class ScriptService {

    private final EpisodeRepository episodeRepository;
    private final SceneRepository sceneRepository;
    private ScriptGenerator scriptGenerator = new ScriptGenerator();

    public ScriptService(EpisodeRepository episodeRepository, SceneRepository sceneRepository) {
        this.episodeRepository = episodeRepository;
        this.sceneRepository = sceneRepository;
    }

    @Transactional
    public Records.GenerateScriptResponse generate(Long episodeId) {
        Episode episode = episodeRepository.findById(episodeId)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", episodeId));

        sceneRepository.deleteByEpisodeId(episodeId);

        List<ScriptGenerator.SceneDraft> drafts = scriptGenerator.generate(episode);

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

        return new Records.GenerateScriptResponse(episodeId, drafts.size(), sb.toString());
    }
}
