package com.dramafactory.api;

import com.dramafactory.model.CameraMove;
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

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class SlideshowRiskApiTest {
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

        mockMvc.perform(get("/api/projects/" + pid + "/episodes/" + eid + "/review/slideshow-risk"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.average").value(5.0))
                .andExpect(jsonPath("$.verdict").value("fail"))
                .andExpect(jsonPath("$.scenesChecked").value(0))
                .andExpect(jsonPath("$.dimensions").value(org.hamcrest.Matchers.anEmptyMap()));
    }

    @Test
    void episodeNotInProject_returns404() throws Exception {
        long pid = createProject();
        createEpisode(pid);

        mockMvc.perform(get("/api/projects/" + pid + "/episodes/999999/review/slideshow-risk"))
                .andExpect(status().isNotFound());
    }

    @Test
    void shotsWithVariedMotion_returnsDimensionScores() throws Exception {
        long pid = createProject();
        long eid = createEpisode(pid);

        Episode episode = episodeRepository.getReferenceById(eid);

        Shot s1 = new Shot();
        s1.setEpisode(episode);
        s1.setShotNo(1);
        s1.setShotSize(ShotSize.YUAN_JING);
        s1.setCameraMove(CameraMove.GU_DING);
        s1.setDescription("Wide establishing shot of the city skyline at dawn.");
        s1.setVideoPrompt("A slow wide shot of a city skyline at dawn, cinematic lighting.");
        shotRepository.save(s1);

        Shot s2 = new Shot();
        s2.setEpisode(episode);
        s2.setShotNo(2);
        s2.setShotSize(ShotSize.TE_XIE);
        s2.setCameraMove(CameraMove.TUI);
        s2.setDescription("Close-up of the protagonist's determined eyes.");
        s2.setVideoPrompt("A close-up push-in on the protagonist's eyes, shallow depth of field.");
        shotRepository.save(s2);

        Shot s3 = new Shot();
        s3.setEpisode(episode);
        s3.setShotNo(3);
        s3.setShotSize(ShotSize.JIN_JING);
        s3.setCameraMove(CameraMove.LA);
        s3.setDescription("Medium shot pulling back to reveal the empty room.");
        s3.setVideoPrompt("A medium shot pulling back to reveal an empty room, soft light.");
        shotRepository.save(s3);

        mockMvc.perform(get("/api/projects/" + pid + "/episodes/" + eid + "/review/slideshow-risk"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.scenesChecked").value(3))
                .andExpect(jsonPath("$.dimensions.repetition.score").isNumber())
                .andExpect(jsonPath("$.dimensions.decorative_visuals.score").isNumber())
                .andExpect(jsonPath("$.dimensions.weak_motion.score").isNumber())
                .andExpect(jsonPath("$.dimensions.weak_shot_intent.score").isNumber())
                .andExpect(jsonPath("$.dimensions.typography_overreliance.score").isNumber())
                .andExpect(jsonPath("$.dimensions.unsupported_cinematic_claims.score").isNumber());
    }
}
