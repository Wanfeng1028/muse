package com.dramafactory.service.prompt;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

public class PromptFavoritesConcurrencyTest {

    private static final Path FAVORITES_FILE = Paths.get(System.getProperty("user.home"), ".drama-factory", "prompt-favorites.json");
    private static final String ID_1 = "yuai-deepseek-prompt";
    private static final String ID_2 = "xiaozheng-mv-tutorial";
    private static final String ID_3 = "README";

    private PromptLibraryService service;

    @BeforeEach
    void setUp() throws IOException {
        Files.deleteIfExists(FAVORITES_FILE);
        service = new PromptLibraryService();
    }

    @Test
    void concurrentAddSameId_NoThrowAndSingleEntry() throws InterruptedException {
        int threadCount = 32;
        CountDownLatch startLatch = new CountDownLatch(1);
        CountDownLatch doneLatch = new CountDownLatch(threadCount);
        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        AtomicInteger trueCount = new AtomicInteger(0);
        List<Throwable> errors = Collections.synchronizedList(new ArrayList<>());

        for (int i = 0; i < threadCount; i++) {
            executor.submit(() -> {
                try {
                    startLatch.await();
                    if (service.addFavorite(ID_1)) {
                        trueCount.incrementAndGet();
                    }
                } catch (Throwable t) {
                    errors.add(t);
                } finally {
                    doneLatch.countDown();
                }
            });
        }

        startLatch.countDown();
        doneLatch.await();
        executor.shutdown();

        assertTrue(errors.isEmpty(), "No exceptions expected: " + errors);
        assertEquals(32, trueCount.get(), "All 32 threads should return true");
        assertEquals(1, service.favorites().size(), "Should have exactly one favorite");
        assertTrue(service.isFavorite(ID_1), "Should be favorite");
    }

    @Test
    void concurrentAddDistinctIds_AllPresent() throws InterruptedException {
        int threadCount = 16;
        String[] ids = {ID_1, ID_2, ID_3};
        CountDownLatch startLatch = new CountDownLatch(1);
        CountDownLatch doneLatch = new CountDownLatch(threadCount);
        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        List<Throwable> errors = Collections.synchronizedList(new ArrayList<>());

        for (int i = 0; i < threadCount; i++) {
            String id = ids[i % 3];
            executor.submit(() -> {
                try {
                    startLatch.await();
                    service.addFavorite(id);
                } catch (Throwable t) {
                    errors.add(t);
                } finally {
                    doneLatch.countDown();
                }
            });
        }

        startLatch.countDown();
        doneLatch.await();
        executor.shutdown();

        assertTrue(errors.isEmpty(), "No exceptions expected: " + errors);
        assertTrue(service.isFavorite(ID_1));
        assertTrue(service.isFavorite(ID_2));
        assertTrue(service.isFavorite(ID_3));
        assertEquals(3, service.favorites().size());
    }

    @Test
    void concurrentAddRemove_NoCorruption() throws InterruptedException {
        int threadCount = 16;
        CountDownLatch startLatch = new CountDownLatch(1);
        CountDownLatch doneLatch = new CountDownLatch(threadCount);
        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        List<Throwable> errors = Collections.synchronizedList(new ArrayList<>());

        for (int i = 0; i < threadCount; i++) {
            boolean isAdder = i < threadCount / 2;
            executor.submit(() -> {
                try {
                    startLatch.await();
                    for (int j = 0; j < 200; j++) {
                        if (isAdder) {
                            service.addFavorite(ID_1);
                        } else {
                            service.removeFavorite(ID_1);
                        }
                    }
                } catch (Throwable t) {
                    errors.add(t);
                } finally {
                    doneLatch.countDown();
                }
            });
        }

        startLatch.countDown();
        doneLatch.await();
        executor.shutdown();

        assertTrue(errors.isEmpty(), "No exceptions expected: " + errors);
        boolean inFavorites = service.favorites().stream().anyMatch(s -> s.id().equals(ID_1));
        assertEquals(service.isFavorite(ID_1), inFavorites, "In-memory state must be consistent");
    }

    @Test
    void concurrentSaves_FileAlwaysValidJson() throws InterruptedException, IOException {
        int threadCount = 16;
        String[] ids = {ID_1, ID_2, ID_3};
        CountDownLatch startLatch = new CountDownLatch(1);
        CountDownLatch doneLatch = new CountDownLatch(threadCount);
        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        List<Throwable> errors = Collections.synchronizedList(new ArrayList<>());

        for (int i = 0; i < threadCount; i++) {
            String id = ids[i % 3];
            boolean doAdd = i % 2 == 0;
            executor.submit(() -> {
                try {
                    startLatch.await();
                    for (int j = 0; j < 50; j++) {
                        if (doAdd) {
                            service.addFavorite(id);
                        } else {
                            service.removeFavorite(id);
                        }
                    }
                } catch (Throwable t) {
                    errors.add(t);
                } finally {
                    doneLatch.countDown();
                }
            });
        }

        startLatch.countDown();
        doneLatch.await();
        executor.shutdown();

        assertTrue(errors.isEmpty(), "No exceptions expected: " + errors);
        if (Files.exists(FAVORITES_FILE)) {
            new ObjectMapper().readValue(FAVORITES_FILE.toFile(), new TypeReference<List<String>>() {});
        }
    }

    @Test
    void saveIsAtomic_NoPartialFile() throws IOException {
        service.addFavorite(ID_1);
        assertTrue(Files.exists(FAVORITES_FILE), "File should exist after add");
        new ObjectMapper().readValue(FAVORITES_FILE.toFile(), new TypeReference<List<String>>() {});
    }

    @Test
    void favoritesFile_UnknownIdIgnoredOnReload() throws IOException {
        service.addFavorite(ID_1);
        service.addFavorite(ID_2);

        String content = Files.readString(FAVORITES_FILE);
        List<String> ids = new ObjectMapper().readValue(content, new TypeReference<List<String>>() {});
        ids.add("ghost-id-zzz");
        String newContent = new ObjectMapper().writeValueAsString(ids);
        Files.writeString(FAVORITES_FILE, newContent);

        PromptLibraryService reloadedService = new PromptLibraryService();
        assertFalse(reloadedService.isFavorite("ghost-id-zzz"), "Unknown id should be ignored on reload");
        assertTrue(reloadedService.isFavorite(ID_1), "Known id should remain favorite");
        assertTrue(reloadedService.isFavorite(ID_2), "Known id should remain favorite");
    }
}
