package com.dramafactory.api;

import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class ContinuityApiTest {
    @Autowired
    private MockMvc mockMvc;
    @Autowired
    private ObjectMapper objectMapper;
    @Autowired
    private ShotRepository shotRepository;
    @Autowired
    private EpisodeRepository episodeRepository;

    private long createProject() throws Exception {
        String body = "{\"title\":\"T\",\"genre\":\"drama\",\"synopsis\":\"s\",\"targetEpisodes\":3}";
        String json = mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        JsonNode node = objectMapper.readTree(json);
        return node.get("id").asLong();
    }

    private long createEpisode(long pid) throws Exception {
        String body = "{\"episodeNo\":1,\"title\":\"E1\",\"outline\":\"o\",\"status\":null,\"durationSec\":null}";
        String json = mockMvc.perform(post("/api/projects/" + pid + "/episodes")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        JsonNode node = objectMapper.readTree(json);
        return node.get("id").asLong();
    }

    @Test
    void episodeWithoutShots_returnsEmptyReport() throws Exception {
        long pid = createProject();
        long eid = createEpisode(pid);

        mockMvc.perform(get("/api/projects/" + pid + "/episodes/" + eid + "/review/continuity"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.shotsChecked").value(0))
                .andExpect(jsonPath("$.hasWarnings").value(false))
                .andExpect(jsonPath("$.issues").isArray())
                .andExpect(jsonPath("$.issues", hasSize(0)));
    }

    @Test
    void episodeNotInProject_returns404() throws Exception {
        long pid = createProject();
        createEpisode(pid);

        mockMvc.perform(get("/api/projects/" + pid + "/episodes/999999/review/continuity"))
                .andExpect(status().isNotFound());
    }

    @Test
    void shotsWithSizeJump_reportsWarn() throws Exception {
        long pid = createProject();
        long eid = createEpisode(pid);

        Episode episode = episodeRepository.getReferenceById(eid);

        Shot s1 = new Shot();
        s1.setEpisode(episode);
        s1.setShotNo(1);
        s1.setShotSize(ShotSize.YUAN_JING);
        shotRepository.save(s1);

        Shot s2 = new Shot();
        s2.setEpisode(episode);
        s2.setShotNo(2);
        s2.setShotSize(ShotSize.TE_XIE);
        shotRepository.save(s2);

        mockMvc.perform(get("/api/projects/" + pid + "/episodes/" + eid + "/review/continuity"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.shotsChecked").value(2))
                .andExpect(jsonPath("$.hasWarnings").value(true))
                .andExpect(jsonPath("$.issues[0].severity").value("WARN"))
                .andExpect(jsonPath("$.issues[0].rule").value("SHOT_SIZE_JUMP"));
    }
}
