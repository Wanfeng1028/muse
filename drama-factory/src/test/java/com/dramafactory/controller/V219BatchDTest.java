package com.dramafactory.controller;

import com.dramafactory.model.Skill;
import com.dramafactory.model.SkillInstall;
import com.dramafactory.model.SkillRating;
import com.dramafactory.model.SkillVersion;
import com.dramafactory.repository.SkillRatingRepository;
import com.dramafactory.repository.SkillVersionRepository;
import com.dramafactory.service.byok.ByokGenerateService;
import com.dramafactory.service.SkillService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class V219BatchDTest {

    // ---------------- ByokController ----------------

    @Test
    void byokFile_directoryFilename_returns404() throws Exception {
        Path tempDir = Files.createTempDirectory("byok-v219");
        Path sub = tempDir.resolve("byok").resolve("image").resolve("subdir1");
        Files.createDirectories(sub);

        ByokController controller = new ByokController(
                mock(ByokGenerateService.class), tempDir.toString());

        ResponseEntity<Resource> resp = controller.file("image", "subdir1");
        assertEquals(404, resp.getStatusCode().value());
    }

    @Test
    void byokFile_noExtensionFile_returnsOctetStream() throws Exception {
        Path tempDir = Files.createTempDirectory("byok-v219");
        Path dir = tempDir.resolve("byok").resolve("image");
        Files.createDirectories(dir);
        Files.writeString(dir.resolve("noextfile"), "hello");

        ByokController controller = new ByokController(
                mock(ByokGenerateService.class), tempDir.toString());

        ResponseEntity<Resource> resp = controller.file("image", "noextfile");
        assertEquals(200, resp.getStatusCode().value());
        assertEquals(MediaType.APPLICATION_OCTET_STREAM, resp.getHeaders().getContentType());
    }

    // ---------------- SkillController.SkillDetailDto.from ----------------

    private Skill sampleSkill() {
        Skill s = new Skill();
        s.setId(1L);
        s.setName("n");
        s.setSlug("s");
        s.setDescription("d");
        s.setAuthor("a");
        s.setCategory("c");
        s.setTags("t");
        s.setIcon("i");
        s.setOfficial(true);
        s.setInstallCount(0L);
        s.setRatingSum(0L);
        s.setRatingCount(0L);
        s.setCreatedAt(LocalDateTime.now());
        return s;
    }

    @Test
    void skillDetailDtoFrom_versionsNull_latestVersionIsNull() {
        SkillController.SkillDetailDto dto =
                SkillController.SkillDetailDto.from(sampleSkill(), null, List.of(), null);
        assertNull(dto.latestVersion());
    }

    @Test
    void skillDetailDtoFrom_versionsEmpty_latestVersionIsNull() {
        SkillController.SkillDetailDto dto =
                SkillController.SkillDetailDto.from(sampleSkill(), List.of(), List.of(), null);
        assertNull(dto.latestVersion());
    }

    // ---------------- SkillController.get ----------------

    @Test
    void get_moreThanFiveRatings_onlyFirstFiveReturned() {
        SkillService skillService = mock(SkillService.class);
        SkillVersionRepository versionRepo = mock(SkillVersionRepository.class);
        SkillRatingRepository ratingRepo = mock(SkillRatingRepository.class);

        Skill skill = sampleSkill();
        SkillVersion version = new SkillVersion();
        version.setSkillId(1L);
        version.setVersion("1.0.0");
        version.setPromptTemplate("p");

        SkillService.SkillDetail detail = new SkillService.SkillDetail(
                skill, List.of(version), null, 4.5);
        when(skillService.getDetail(1L)).thenReturn(detail);

        List<SkillRating> ratings = new ArrayList<>();
        for (int i = 0; i < 6; i++) {
            SkillRating r = new SkillRating();
            r.setId((long) i);
            r.setSkillId(1L);
            r.setScore(5);
            r.setComment("c" + i);
            r.setCreatedAt(LocalDateTime.now());
            ratings.add(r);
        }
        when(ratingRepo.findBySkillIdOrderByCreatedAtDesc(1L)).thenReturn(ratings);

        SkillController controller = new SkillController(skillService, versionRepo, ratingRepo);
        SkillController.SkillDetailDto dto = controller.get(1L);

        assertEquals(5, dto.ratings().size());
    }

    // ---------------- SkillController.install ----------------

    @Test
    void install_nullRequest_doesNotThrowAndVersionMatches() {
        SkillService skillService = mock(SkillService.class);
        SkillVersionRepository versionRepo = mock(SkillVersionRepository.class);
        SkillRatingRepository ratingRepo = mock(SkillRatingRepository.class);

        SkillInstall install = new SkillInstall();
        install.setId(11L);
        install.setSkillId(7L);
        install.setVersion("2.0.0");
        install.setInstalledAt(LocalDateTime.now());

        when(skillService.install(7L, null)).thenReturn(install);

        SkillController controller = new SkillController(skillService, versionRepo, ratingRepo);
        SkillController.InstallDto dto = controller.install(7L, null);

        assertEquals("2.0.0", dto.version());
    }

    // ---------------- SkillController.publish ----------------

    @Test
    void publish_emptyVersions_latestVersionIsNull() {
        SkillService skillService = mock(SkillService.class);
        SkillVersionRepository versionRepo = mock(SkillVersionRepository.class);
        SkillRatingRepository ratingRepo = mock(SkillRatingRepository.class);

        Skill skill = sampleSkill();
        skill.setId(5L);
        when(skillService.publish(anyString(), anyString(), anyString(), anyString(),
                anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(skill);
        when(versionRepo.findBySkillIdOrderByCreatedAtDesc(5L)).thenReturn(List.of());

        SkillController controller = new SkillController(skillService, versionRepo, ratingRepo);
        SkillController.SkillDto dto = controller.publish(
                new SkillController.CreateSkillRequest("n", "s", "d", "a", "c", "t", "i", "p", "c"));

        assertNull(dto.latestVersion());
    }
}