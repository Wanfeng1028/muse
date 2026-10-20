package com.dramafactory.service.prompt;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;

public class PromptLibraryServiceFavoritesTest {

    private PromptLibraryService service;
    private Path favFile;

    @BeforeEach
    void setUp() throws Exception {
        favFile = Paths.get(System.getProperty("user.home"), ".drama-factory", "prompt-favorites.json");
        Files.deleteIfExists(favFile);
        service = new PromptLibraryService();
    }

    @Test
    void addFavoriteUnknownIdReturnsFalse() {
        assertFalse(service.addFavorite("this-id-does-not-exist-zzz"));
        assertTrue(service.favorites().isEmpty());
        assertFalse(service.isFavorite("this-id-does-not-exist-zzz"));
    }

    @Test
    void addFavoriteKnownIdReturnsTrueAndIsFavorite() {
        assertTrue(service.addFavorite("yuai-deepseek-prompt"));
        assertTrue(service.isFavorite("yuai-deepseek-prompt"));
        assertEquals(1, service.favorites().size());
    }

    @Test
    void addFavoriteIsIdempotent() {
        assertTrue(service.addFavorite("yuai-deepseek-prompt"));
        assertTrue(service.addFavorite("yuai-deepseek-prompt"));
        assertEquals(1, service.favorites().size());
    }

    @Test
    void removeFavoriteNotFavoritedIsIdempotent() {
        assertTrue(service.removeFavorite("xiaozheng-mv-tutorial"));
        assertTrue(service.removeFavorite("xiaozheng-mv-tutorial"));
        assertTrue(service.favorites().isEmpty());
        assertFalse(service.isFavorite("xiaozheng-mv-tutorial"));
    }

    @Test
    void removeFavoriteFavoritedThenNotFavorite() {
        assertTrue(service.addFavorite("yuai-deepseek-prompt"));
        assertTrue(service.removeFavorite("yuai-deepseek-prompt"));
        assertFalse(service.isFavorite("yuai-deepseek-prompt"));
        assertTrue(service.favorites().isEmpty());
        assertTrue(service.removeFavorite("yuai-deepseek-prompt"));
    }

    @Test
    void removeFavoriteUnknownIdReturnsFalse() {
        assertFalse(service.removeFavorite("this-id-does-not-exist-zzz"));
    }

    @Test
    void favoritesReturnsCompleteSummary() {
        assertTrue(service.addFavorite("yuai-deepseek-prompt"));
        List<PromptLibraryService.PromptSummary> favorites = service.favorites();
        assertEquals(1, favorites.size());
        PromptLibraryService.PromptSummary summary = favorites.get(0);
        PromptLibraryService.PromptDetail detail = service.get("yuai-deepseek-prompt").orElseThrow();

        assertEquals(detail.id(), summary.id());
        assertEquals(detail.title(), summary.title());
        assertEquals(detail.source(), summary.source());
        assertEquals(detail.path(), summary.path());
        assertEquals(detail.summary(), summary.summary());

        assertEquals("yuai-deepseek-prompt", summary.id());
        assertEquals("DeepSeek 做《雨爱》MV 的提示词（部分转录）", summary.title());
        assertEquals("根目录", summary.source());
    }

    @Test
    void addFavoriteNullReturnsFalse() {
        assertFalse(service.addFavorite(null));
        assertTrue(service.favorites().isEmpty());
    }

    @Test
    void favoritesContainsMultiple() {
        assertTrue(service.addFavorite("yuai-deepseek-prompt"));
        assertTrue(service.addFavorite("xiaozheng-mv-tutorial"));
        List<PromptLibraryService.PromptSummary> favorites = service.favorites();
        assertEquals(2, favorites.size());
        assertTrue(favorites.stream().anyMatch(s -> s.id().equals("yuai-deepseek-prompt")));
        assertTrue(favorites.stream().anyMatch(s -> s.id().equals("xiaozheng-mv-tutorial")));
    }
}