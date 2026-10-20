package com.dramafactory.service.prompt;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;

public class PromptLibraryServiceFavoritesPersistenceTest {

    private Path favoritesFile;

    @BeforeEach
    void setUp() throws IOException {
        favoritesFile = Paths.get(System.getProperty("user.home"), ".drama-factory", "prompt-favorites.json");
        Files.deleteIfExists(favoritesFile);
    }

    @Test
    void addFavoritePersistsToDisk() throws IOException {
        PromptLibraryService service = new PromptLibraryService();
        assertTrue(service.addFavorite("yuai-deepseek-prompt"));
        assertTrue(Files.exists(favoritesFile));
        String content = Files.readString(favoritesFile);
        assertTrue(content.contains("yuai-deepseek-prompt"));
    }

    @Test
    void newInstanceLoadsFavoritesFromDisk() {
        PromptLibraryService service = new PromptLibraryService();
        assertTrue(service.addFavorite("yuai-deepseek-prompt"));
        assertTrue(service.addFavorite("xiaozheng-mv-tutorial"));

        PromptLibraryService secondService = new PromptLibraryService();
        assertTrue(secondService.isFavorite("yuai-deepseek-prompt"));
        assertTrue(secondService.isFavorite("xiaozheng-mv-tutorial"));
        assertEquals(2, secondService.favorites().size());
    }

    @Test
    void corruptedJsonFileDoesNotThrow() throws IOException {
        PromptLibraryService service = new PromptLibraryService();
        Files.createDirectories(favoritesFile.getParent());
        Files.writeString(favoritesFile, "{not valid json!!!");

        PromptLibraryService secondService = new PromptLibraryService();
        assertTrue(secondService.favorites().isEmpty());
        assertFalse(secondService.isFavorite("yuai-deepseek-prompt"));
    }

    @Test
    void removeFavoritePersistsRemoval() throws IOException {
        PromptLibraryService service = new PromptLibraryService();
        assertTrue(service.addFavorite("yuai-deepseek-prompt"));
        assertTrue(service.addFavorite("xiaozheng-mv-tutorial"));

        String content = Files.readString(favoritesFile);
        assertTrue(content.contains("yuai-deepseek-prompt"));
        assertTrue(content.contains("xiaozheng-mv-tutorial"));

        assertTrue(service.removeFavorite("yuai-deepseek-prompt"));

        PromptLibraryService secondService = new PromptLibraryService();
        assertFalse(secondService.isFavorite("yuai-deepseek-prompt"));
        assertTrue(secondService.isFavorite("xiaozheng-mv-tutorial"));

        String updatedContent = Files.readString(favoritesFile);
        assertFalse(updatedContent.contains("yuai-deepseek-prompt"));
    }

    @Test
    void concurrentAddRemoveDoesNotThrow() throws InterruptedException {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> summaries = service.list(null);
        List<String> ids = new ArrayList<>();
        for (int i = 0; i < 5 && i < summaries.size(); i++) {
            ids.add(summaries.get(i).id());
        }

        List<Thread> threads = new ArrayList<>();
        List<AtomicReference<Throwable>> errors = new ArrayList<>();

        for (int i = 0; i < 10; i++) {
            AtomicReference<Throwable> error = new AtomicReference<>();
            errors.add(error);
            Thread thread = new Thread(() -> {
                try {
                    for (int j = 0; j < 20; j++) {
                        for (String id : ids) {
                            service.addFavorite(id);
                        }
                    }
                } catch (Throwable t) {
                    error.set(t);
                }
            });
            threads.add(thread);
            thread.start();
        }

        for (Thread thread : threads) {
            thread.join();
        }

        for (AtomicReference<Throwable> error : errors) {
            assertNull(error.get());
        }

        assertEquals(5, service.favorites().size());
        for (String id : ids) {
            assertTrue(service.isFavorite(id));
        }

        threads.clear();
        errors.clear();

        for (int i = 0; i < 10; i++) {
            AtomicReference<Throwable> error = new AtomicReference<>();
            errors.add(error);
            Thread thread = new Thread(() -> {
                try {
                    for (int j = 0; j < 20; j++) {
                        for (String id : ids) {
                            service.removeFavorite(id);
                        }
                    }
                } catch (Throwable t) {
                    error.set(t);
                }
            });
            threads.add(thread);
            thread.start();
        }

        for (Thread thread : threads) {
            thread.join();
        }

        for (AtomicReference<Throwable> error : errors) {
            assertNull(error.get());
        }

        assertTrue(service.favorites().isEmpty());
    }
}