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

@SpringBootTest
class CreatorControllerFollowingTest {

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

    private void publishSkillFor(String author, String slug) {
        skillService.publish("skill-" + slug, slug, "desc", author, "GENERAL", "t1", "puzzle", "tpl {{x}}", "v1");
    }

    private void setSkillCreatedAt(String slug, LocalDateTime time) {
        var skill = skillRepository.findBySlug(slug).orElseThrow();
        skill.setCreatedAt(time);
        skillRepository.save(skill);
    }

    @Test
    void followingEmptyWhenNoFollows() {
        String handle = uniqueHandle("solo");
        createProfile(handle, "Solo Creator");
        publishSkillFor(handle, uniqueHandle("solo-skill"));
        assertEquals(0, creatorController.following().size());
    }

    @Test
    void followingOrderedByFollowedAtDesc() {
        String handleA = uniqueHandle("alpha");
        String handleB = uniqueHandle("beta");
        createProfile(handleA, "Alpha");
        createProfile(handleB, "Beta");
        creatorController.follow(handleA);
        creatorController.follow(handleB);
        var idA = profileRepository.findByHandle(handleA).orElseThrow().getId();
        var idB = profileRepository.findByHandle(handleB).orElseThrow().getId();
        CreatorFollow followA = followRepository.findByCreatorIdAndFollowerId(idA, "local").orElseThrow();
        CreatorFollow followB = followRepository.findByCreatorIdAndFollowerId(idB, "local").orElseThrow();
        followA.setCreatedAt(LocalDateTime.of(2026, 10, 27, 10, 0));
        followB.setCreatedAt(LocalDateTime.of(2026, 10, 20, 10, 0));
        followRepository.save(followA);
        followRepository.save(followB);
        var following = creatorController.following();
        assertEquals(2, following.size());
        assertEquals(handleA, following.get(0).handle());
        assertEquals(handleB, following.get(1).handle());
    }

    @Test
    void followingLatestSkillIsNewestAndDeduped() {
        String handle = uniqueHandle("author");
        createProfile(handle, handle);
        String oldSlug = uniqueHandle("sk-old");
        String newSlug = uniqueHandle("sk-new");
        publishSkillFor(handle, oldSlug);
        publishSkillFor(handle, newSlug);
        setSkillCreatedAt(oldSlug, LocalDateTime.of(2026, 10, 20, 10, 0));
        setSkillCreatedAt(newSlug, LocalDateTime.of(2026, 10, 26, 10, 0));
        creatorController.follow(handle);
        var following = creatorController.following();
        assertEquals(1, following.size());
        assertEquals(2, following.get(0).skillCount());
        assertEquals("skill-" + newSlug, following.get(0).latestSkillName());
        assertEquals(LocalDateTime.of(2026, 10, 26, 10, 0), following.get(0).latestSkillCreatedAt());
    }

    @Test
    void followingSkipsMissingProfile() {
        CreatorFollow orphan = new CreatorFollow();
        orphan.setCreatorId(999999L);
        orphan.setFollowerId("local");
        followRepository.save(orphan);
        String handle = uniqueHandle("real");
        createProfile(handle, "Real Creator");
        creatorController.follow(handle);
        var following = creatorController.following();
        assertEquals(1, following.size());
        assertEquals(handle, following.get(0).handle());
    }

    @Test
    void followingExcludesUnfollowed() {
        String handle = uniqueHandle("gone");
        createProfile(handle, "Gone Creator");
        creatorController.follow(handle);
        creatorController.unfollow(handle);
        assertEquals(0, creatorController.following().size());
    }
}