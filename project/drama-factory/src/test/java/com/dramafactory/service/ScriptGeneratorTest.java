package com.dramafactory.service;

import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ScriptGeneratorTest {

    private Episode buildEpisode(String genre, String title, String outline) {
        DramaProject project = new DramaProject();
        project.setTitle(title);
        project.setGenre(genre);

        Episode episode = new Episode();
        episode.setProject(project);
        episode.setEpisodeNo(1);
        episode.setTitle("第一集");
        episode.setOutline(outline);
        return episode;
    }

    @Test
    void generateReturnsExactlyFourScenesWithRequiredFields() {
        ScriptGenerator generator = new ScriptGenerator();
        Episode episode = buildEpisode("都市逆袭", "重回巅峰", "主角被陷害后重生，誓要夺回属于自己的一切");

        List<ScriptGenerator.SceneDraft> drafts = generator.generate(episode);

        assertEquals(4, drafts.size());
        for (int i = 0; i < drafts.size(); i++) {
            ScriptGenerator.SceneDraft draft = drafts.get(i);
            assertEquals(i + 1, draft.sceneNo());
            assertNotNull(draft.location());
            assertNotNull(draft.timeOfDay());
            assertNotNull(draft.description());
            assertNotNull(draft.dialogue());
            assertNotNull(draft.prompt());
            assertTrue(!draft.description().isEmpty());
            assertTrue(!draft.dialogue().isEmpty());
            assertTrue(!draft.prompt().isEmpty());
            String prompt = draft.prompt().toLowerCase();
            assertTrue(prompt.contains("close-up") || prompt.contains("cinematic"),
                    "prompt should contain a cinematic shot keyword");
        }
    }

    @Test
    void generateHandlesNullOutline() {
        ScriptGenerator generator = new ScriptGenerator();
        Episode episode = buildEpisode("悬疑", "迷雾", null);

        List<ScriptGenerator.SceneDraft> drafts = generator.generate(episode);

        assertEquals(4, drafts.size());
        for (int i = 0; i < drafts.size(); i++) {
            ScriptGenerator.SceneDraft draft = drafts.get(i);
            assertEquals(i + 1, draft.sceneNo());
            assertTrue(draft.description() != null && !draft.description().isEmpty());
            assertTrue(draft.dialogue() != null && !draft.dialogue().isEmpty());
            assertTrue(draft.prompt() != null && !draft.prompt().isEmpty());
        }
    }
}
