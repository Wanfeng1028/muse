package com.dramafactory;

import com.dramafactory.controller.CreatorController;
import com.dramafactory.controller.CreatorController.CreateCreatorRequest;
import com.dramafactory.model.CreatorFollow;
import com.dramafactory.model.CreatorProfile;
import com.dramafactory.model.Skill;
import com.dramafactory.repository.CreatorFollowRepository;
import com.dramafactory.repository.CreatorProfileRepository;
import com.dramafactory.repository.SkillRepository;
import com.dramafactory.service.SkillService;
import java.time.LocalDateTime;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class CreatorControllerLeaderboardTest {

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

    private CreatorProfile createProfileAs(String handle, String displayName, String ownerId) {
        creatorController.create(new CreateCreatorRequest(handle, displayName, "bio-" + handle, null));
        CreatorProfile profile = profileRepository.findByHandle(handle).orElseThrow();
        profile.setOwnerId(ownerId);
        return profileRepository.save(profile);
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
    void leaderboardEmptyWhenNoCreators() {
        assertEquals(0, creatorController.leaderboard(10).size());
    }

    @Test
    void leaderboardIncludesFollowedAndOwn() {
        String handleA = uniqueHandle("self");
        createProfile(handleA, "Self Display");
        String handleB = uniqueHandle("other");
        createProfileAs(handleB, "Other Display", "user-b");
        creatorController.follow(handleB);

        List<CreatorController.CreatorLeaderboardItemDto> board = creatorController.leaderboard(10);

        assertEquals(2, board.size());
        List<String> handles = board.stream()
                .map(CreatorController.CreatorLeaderboardItemDto::handle)
                .sorted()
                .toList();
        List<String> expected = Stream.of(handleA, handleB).sorted().toList();
        assertEquals(expected, handles);
    }

    @Test
    void leaderboardRankedByFollowersThenSkills() {
        String handleX = uniqueHandle("x");
        String handleY = uniqueHandle("y");
        String handleZ = uniqueHandle("z");
        CreatorProfile x = createProfileAs(handleX, "X Display", "user-x");
        CreatorProfile y = createProfileAs(handleY, "Y Display", "user-y");
        createProfileAs(handleZ, "Z Display", "user-z");

        addFollower(x.getId(), "u1");
        addFollower(x.getId(), "u2");
        addFollower(y.getId(), "u1");

        publishSkillFor(handleY, uniqueHandle("yskill"));
        publishSkillFor(handleZ, uniqueHandle("zskill1"));
        publishSkillFor(handleZ, uniqueHandle("zskill2"));

        List<CreatorController.CreatorLeaderboardItemDto> board = creatorController.leaderboard(10);

        assertEquals(3, board.size());
        assertEquals(handleX, board.get(0).handle());
        assertEquals(handleY, board.get(1).handle());
        assertEquals(handleZ, board.get(2).handle());
        assertEquals(1, board.get(0).rank());
        assertEquals(2, board.get(1).rank());
        assertEquals(3, board.get(2).rank());
    }

    @Test
    void leaderboardLimitAndIllegal() {
        createProfileAs(uniqueHandle("lb-a"), "LB A", "user-a");
        createProfileAs(uniqueHandle("lb-b"), "LB B", "user-b");
        createProfileAs(uniqueHandle("lb-c"), "LB C", "user-c");

        var top2 = creatorController.leaderboard(2);
        assertEquals(2, top2.size());
        assertEquals(1, top2.get(0).rank());
        assertEquals(2, top2.get(1).rank());

        assertThrows(IllegalArgumentException.class, () -> creatorController.leaderboard(0));
        assertThrows(IllegalArgumentException.class, () -> creatorController.leaderboard(51));
    }

    @Test
    void leaderboardLatestSkillDeduped() {
        String handle = uniqueHandle("author");
        createProfileAs(handle, handle, "user-author");
        String oldSlug = uniqueHandle("sk-old");
        String newSlug = uniqueHandle("sk-new");
        publishSkillFor(handle, oldSlug);
        publishSkillFor(handle, newSlug);
        setSkillCreatedAt(oldSlug, LocalDateTime.of(2026, 10, 20, 10, 0));
        setSkillCreatedAt(newSlug, LocalDateTime.of(2026, 10, 26, 10, 0));

        var items = creatorController.leaderboard(10);
        assertEquals(1, items.size());
        var first = items.get(0);
        assertEquals(2, first.skillCount());
        assertEquals("skill-" + newSlug, first.latestSkillName());
        assertEquals(LocalDateTime.of(2026, 10, 26, 10, 0), first.latestSkillCreatedAt());
        assertEquals(1, first.rank());
    }
}
