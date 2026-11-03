package com.dramafactory.tools;

import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetSource;
import com.dramafactory.model.AssetType;
import com.dramafactory.model.CameraMove;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.repository.AssetRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class QuickToolsControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private AssetRepository assetRepository;

    @Autowired
    private DramaProjectRepository dramaProjectRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private ShotRepository shotRepository;

    private Asset createAsset(AssetType type, String fileName) {
        Asset asset = new Asset();
        asset.setType(type);
        asset.setSource(AssetSource.UPLOADED);
        asset.setFileName(fileName);
        asset.setFilePath("assets/tools-test/" + fileName);
        asset.setMimeType("application/octet-stream");
        asset.setFileSize(10L);
        return assetRepository.save(asset);
    }

    @Test
    void batchTag_ok() throws Exception {
        Asset a1 = createAsset(AssetType.IMAGE, "c1.png");
        Asset a2 = createAsset(AssetType.IMAGE, "c2.png");

        String body = "{\"ids\":[" + a1.getId() + "," + a2.getId() + "],\"tags\":\"t1\",\"mode\":\"merge\"}";

        mockMvc.perform(post("/api/tools/assets/batch-tag")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(2));
    }

    @Test
    void batchTag_emptyIds_400() throws Exception {
        String body = "{\"ids\":[],\"tags\":\"t1\"}";

        mockMvc.perform(post("/api/tools/assets/batch-tag")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest());
    }

    @Test
    void batchRename_ok() throws Exception {
        Asset a1 = createAsset(AssetType.IMAGE, "rename-old.png");

        String body = "{\"renames\":{\"" + a1.getId() + "\":\"改名.png\"}}";

        mockMvc.perform(post("/api/tools/assets/batch-rename")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(1));
    }

    @Test
    void batchTag_notFound_404() throws Exception {
        String body = "{\"ids\":[999999],\"tags\":\"t1\"}";

        mockMvc.perform(post("/api/tools/assets/batch-tag")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isNotFound());
    }

    @Test
    void shotsCsv_notFound_404() throws Exception {
        mockMvc.perform(get("/api/tools/episodes/999999/shots.csv"))
                .andExpect(status().isNotFound());
    }

    @Test
    void shotsCsv_ok() throws Exception {
        DramaProject project = new DramaProject();
        project.setTitle("控制器测试项目");
        project.setOwnerId("test-owner");
        project = dramaProjectRepository.save(project);

        Episode episode = new Episode();
        episode.setProject(project);
        episode.setEpisodeNo(1);
        episode.setTitle("第一集");
        episode = episodeRepository.save(episode);

        Shot shot = new Shot();
        shot.setEpisode(episode);
        shot.setShotNo(1);
        shot.setShotSize(ShotSize.JIN_JING);
        shot.setCameraMove(CameraMove.GU_DING);
        shot.setDescription("测试镜头");
        shot.setDialogue("台词");
        shot.setDurationSeconds(2);
        shotRepository.save(shot);

        mockMvc.perform(get("/api/tools/episodes/" + episode.getId() + "/shots.csv"))
                .andExpect(status().isOk())
                .andExpect(header().string("Content-Disposition",
                        org.hamcrest.Matchers.containsString("attachment")));
    }

    @Test
    void opLogs_ok() throws Exception {
        mockMvc.perform(get("/api/tools/op-logs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());
    }
}
