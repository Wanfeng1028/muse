package com.dramafactory.service.prompt;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class PromptFavoritesCorruptionTest {
    private Path favFile;

    @BeforeEach
    void setUp() throws IOException {
        favFile = Paths.get(System.getProperty("user.home"), ".drama-factory", "prompt-favorites.json");
        Files.createDirectories(favFile.getParent());
        Files.deleteIfExists(favFile);
    }

    @Test
    void garbageTextFile_EmptyFavorites() throws IOException {
        Files.writeString(favFile, "this is not json {{{");
        PromptLibraryService service = assertDoesNotThrow(() -> new PromptLibraryService());
        assertTrue(service.favorites().isEmpty());
    }

    @Test
    void jsonObjectNotArray_EmptyFavorites() throws IOException {
        Files.writeString(favFile, "{\"a\":1}");
        PromptLibraryService service = assertDoesNotThrow(() -> new PromptLibraryService());
        assertTrue(service.favorites().isEmpty());
    }

    @Test
    void arrayWithNulls_SkipsNulls() throws IOException {
        Files.writeString(favFile, "[\"yuai-deepseek-prompt\", null]");
        PromptLibraryService service = assertDoesNotThrow(() -> new PromptLibraryService());
        assertTrue(service.isFavorite("yuai-deepseek-prompt"));
    }

    @Test
    void unknownIds_Filtered() throws IOException {
        Files.writeString(favFile, "[\"yuai-deepseek-prompt\", \"ghost-id-zzz\"]");
        PromptLibraryService service = assertDoesNotThrow(() -> new PromptLibraryService());
        assertTrue(service.isFavorite("yuai-deepseek-prompt"));
        assertFalse(service.isFavorite("ghost-id-zzz"));
    }

    @Test
    void emptyArray_EmptyFavorites() throws IOException {
        Files.writeString(favFile, "[]");
        PromptLibraryService service = assertDoesNotThrow(() -> new PromptLibraryService());
        assertTrue(service.favorites().isEmpty());
    }

    @Test
    void missingFile_EmptyFavorites() {
        PromptLibraryService service = assertDoesNotThrow(() -> new PromptLibraryService());
        assertTrue(service.favorites().isEmpty());
    }

    @Test
    void corruptedThenRecoverable() throws IOException {
        Files.writeString(favFile, "garbage text !!!");
        PromptLibraryService service = assertDoesNotThrow(() -> new PromptLibraryService());
        assertTrue(service.favorites().isEmpty());
        assertTrue(service.addFavorite("xiaozheng-mv-tutorial"));
        String content = Files.readString(favFile);
        assertTrue(content.contains("xiaozheng-mv-tutorial"));
    }
}