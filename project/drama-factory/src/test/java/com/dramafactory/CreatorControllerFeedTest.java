package com.dramafactory;

import com.dramafactory.controller.CreatorController;
import com.dramafactory.controller.CreatorController.CreateCreatorRequest;
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
class CreatorControllerFeedTest {

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
    void feedEmptyWhenNoFollows() {
        String handle = uniqueHandle("feed-none");
        createProfile(handle, "No Follow Maker");
        publishSkillFor(handle, uniqueHandle("sk-none"));
        assertEquals(0, creatorController.feed(20).size());
    }

@Test
    void feedOnlyFollowedCreatorsNewestFirst() {
        String followed = uniqueHandle("feed-a");
        String unfollowed = uniqueHandle("feed-b");
        createProfile(followed, "Feed Maker A");
        createProfile(unfollowed, "Feed Maker B");
        String oldSlug = uniqueHandle("sk-old");
        String newSlug = uniqueHandle("sk-new");
        String otherSlug = uniqueHandle("sk-other");
        publishSkillFor(followed, oldSlug);
        publishSkillFor(followed, newSlug);
        publishSkillFor(unfollowed, otherSlug);
        setSkillCreatedAt(oldSlug, LocalDateTime.of(2026, 10, 20, 10, 0));
        setSkillCreatedAt(newSlug, LocalDateTime.of(2026, 10, 26, 10, 0));
        setSkillCreatedAt(otherSlug, LocalDateTime.of(2026, 10, 27, 10, 0));
        creatorController.follow(followed);
        var feed = creatorController.feed(20);
        assertEquals(2, feed.size());
        assertEquals(newSlug, feed.get(0).skillSlug());
        assertEquals(oldSlug, feed.get(1).skillSlug());
        assertEquals(followed, feed.get(0).handle());
    }

    @Test
    void feedLimitTruncatesAndRejectsIllegal() {
        String handle = uniqueHandle("feed-lim");
        createProfile(handle, "Limit Maker");
        publishSkillFor(handle, uniqueHandle("sk-l1"));
        publishSkillFor(handle, uniqueHandle("sk-l2"));
        publishSkillFor(handle, uniqueHandle("sk-l3"));
        creatorController.follow(handle);
        assertEquals(2, creatorController.feed(2).size());
        assertThrows(IllegalArgumentException.class, () -> creatorController.feed(0));
        assertThrows(IllegalArgumentException.class, () -> creatorController.feed(51));
    }

    @Test
    void feedDeduplicatesWhenHandleEqualsDisplayName() {
        String handle = uniqueHandle("feed-dup");
        createProfile(handle, handle);
        publishSkillFor(handle, uniqueHandle("sk-dup"));
        creatorController.follow(handle);
        assertEquals(1, creatorController.feed(20).size());
    }
}
