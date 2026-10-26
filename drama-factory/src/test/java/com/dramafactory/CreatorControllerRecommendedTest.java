package com.dramafactory;

import com.dramafactory.controller.CreatorController;
import com.dramafactory.controller.CreatorController.CreateCreatorRequest;
import com.dramafactory.model.CreatorFollow;
import com.dramafactory.repository.CreatorFollowRepository;
import com.dramafactory.repository.CreatorProfileRepository;
import com.dramafactory.repository.SkillRepository;
import com.dramafactory.service.SkillService;
import java.time.LocalDateTime;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class CreatorControllerRecommendedTest {

    @Autowired
    private CreatorController creatorController;

    @Autowired
    private SkillService skillService;

    @Autowired
    private CreatorProfileRepository profileRepository;

    @Autowired
    private CreatorFollowRepository followRepository;

    @Autowired
    private SkillRepository skillRepository;

    @BeforeEach
    void setUp() {
        followRepository.deleteAll();
        skillRepository.deleteAll();
        profileRepository.deleteAll();
    }

    private String uniqueHandle(String base) {
        String cleaned = (base + "-" + System.nanoTime()).replaceAll("[^a-z0-9-]", "");
        return cleaned.length() > 50 ? cleaned.substring(0, 50) : cleaned;
    }

    private void createProfile(String handle, String displayName) {
        creatorController.create(new CreateCreatorRequest(handle, displayName, "bio-" + handle, null));
    }

    private void createProfileAs(String handle, String displayName, String ownerId) {
        creatorController.create(new CreateCreatorRequest(handle, displayName, "bio-" + handle, null));
        var profile = profileRepository.findByHandle(handle).orElseThrow();
        profile.setOwnerId(ownerId);
        profileRepository.save(profile);
    }

    private void publishSkillFor(String author, String slug) {
        skillService.publish("skill-" + slug, slug, "desc", author, "GENERAL", "t1", "puzzle", "tpl {{x}}", "v1");
    }

    private void setSkillCreatedAt(String slug, LocalDateTime time) {
        var skill = skillRepository.findBySlug(slug).orElseThrow();
        skill.setCreatedAt(time);
        skillRepository.save(skill);
    }

    private void addFollower(Long creatorId, String followerId) {
        CreatorFollow follow = new CreatorFollow();
        follow.setCreatorId(creatorId);
        follow.setFollowerId(followerId);
        followRepository.save(follow);
    }

    @Test
    void recommendedEmptyWhenNoCreators() {
        assertEquals(0, creatorController.recommended(10).size());
    }

    @Test
    void recommendedExcludesFollowedAndOwn() {
        String handleA = uniqueHandle("alpha");
        String handleB = uniqueHandle("beta");
        String handleC = uniqueHandle("gamma");
        createProfile(handleA, "Alpha");
        createProfileAs(handleB, "Beta", "user-b");
        createProfileAs(handleC, "Gamma", "user-c");
        creatorController.follow(handleB);
        var recommended = creatorController.recommended(10);
        assertEquals(1, recommended.size());
        assertEquals(handleC, recommended.get(0).handle());
    }

    @Test
    void recommendedSortedByFollowersThenSkills() {
        String handleX = uniqueHandle("x");
        String handleY = uniqueHandle("y");
        String handleZ = uniqueHandle("z");
        createProfileAs(handleX, "X", "user-x");
        createProfileAs(handleY, "Y", "user-y");
        createProfileAs(handleZ, "Z", "user-z");
        Long xId = profileRepository.findByHandle(handleX).orElseThrow().getId();
        Long yId = profileRepository.findByHandle(handleY).orElseThrow().getId();
        addFollower(xId, "u1");
        addFollower(xId, "u2");
        addFollower(yId, "u1");
        publishSkillFor(handleY, uniqueHandle("y-skill"));
        publishSkillFor(handleZ, uniqueHandle("z-skill-a"));
        publishSkillFor(handleZ, uniqueHandle("z-skill-b"));
        var recommended = creatorController.recommended(10);
        assertEquals(3, recommended.size());
        assertEquals(handleX, recommended.get(0).handle());
        assertEquals(handleY, recommended.get(1).handle());
        assertEquals(handleZ, recommended.get(2).handle());
    }

    @Test
    void recommendedLimitAndIllegal() {
        createProfileAs(uniqueHandle("rec-a"), "Rec A", "user-a");
        createProfileAs(uniqueHandle("rec-b"), "Rec B", "user-b");
        createProfileAs(uniqueHandle("rec-c"), "Rec C", "user-c");
        assertEquals(2, creatorController.recommended(2).size());
        assertThrows(IllegalArgumentException.class, () -> creatorController.recommended(0));
        assertThrows(IllegalArgumentException.class, () -> creatorController.recommended(51));
    }

    @Test
    void recommendedLatestSkillDeduped() {
        String handle = uniqueHandle("author");
        createProfileAs(handle, handle, "user-author");
        String oldSlug = uniqueHandle("sk-old");
        String newSlug = uniqueHandle("sk-new");
        publishSkillFor(handle, oldSlug);
        publishSkillFor(handle, newSlug);
        setSkillCreatedAt(oldSlug, LocalDateTime.of(2026, 10, 20, 10, 0));
        setSkillCreatedAt(newSlug, LocalDateTime.of(2026, 10, 26, 10, 0));
        var recommended = creatorController.recommended(10);
        assertEquals(1, recommended.size());
        assertEquals(2, recommended.get(0).skillCount());
        assertEquals("skill-" + newSlug, recommended.get(0).latestSkillName());
        assertEquals(LocalDateTime.of(2026, 10, 26, 10, 0), recommended.get(0).latestSkillCreatedAt());
    }
}
