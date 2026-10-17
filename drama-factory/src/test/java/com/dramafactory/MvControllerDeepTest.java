package com.dramafactory;

import com.dramafactory.controller.MvController;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.MvSong;
import com.dramafactory.service.MvService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest(classes = MvControllerDeepTest.TestConfig.class)
class MvControllerDeepTest {

    @org.springframework.boot.test.context.TestConfiguration
    static class TestConfig {
        @org.springframework.context.annotation.Bean
        MvController mvController(MvService mvService) {
            return new MvController(mvService, "./data/media");
        }
    }

    @MockBean
    private MvService mvService;

    @Autowired
    private MvController mvController;

    private MvSong newSong(Long id, String status, Long runId) {
        MvSong s = new MvSong();
        s.setId(id);
        s.setTheme("theme-" + id);
        s.setMood("mood-" + id);
        s.setStyle("style-" + id);
        s.setStatus(status);
        s.setSource("IMPORT");
        s.setAudioUrl("http://audio/" + id + ".mp3");
        s.setDurationMs(12345);
        s.setTimelineJson("{\"t\":1}");
        s.setRunId(runId);
        return s;
    }

    @BeforeEach
    void resetStubs() {
        org.mockito.Mockito.reset(mvService);
    }

    @Test
    void createRejectsBlankThemeWithBadRequestAndFailedStatus() {
        // given
        Map<String, String> body = new HashMap<>();
        body.put("theme", "   ");
        body.put("mood", "calm");

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.create(body);

        // then
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("FAILED", resp.getBody().get("status"));
        assertNotNull(resp.getBody().get("error"));
    }

    @Test
    void createReturnsSucceededAndIdFromService() {
        // given
        Map<String, String> body = new HashMap<>();
        body.put("theme", "夜航");
        body.put("mood", "sad");
        body.put("style", "pop");
        when(mvService.create(eq("夜航"), eq("sad"), eq("pop"))).thenReturn(77L);

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.create(body);

        // then
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("SUCCEEDED", resp.getBody().get("status"));
        assertEquals(77L, resp.getBody().get("id"));
        verify(mvService, times(1)).create(eq("夜航"), eq("sad"), eq("pop"));
    }

    @Test
    void importAudioPropagatesResourceNotFoundAsException() {
        // given
        when(mvService.importAudio(any(), any(), any(), any(), any()))
                .thenThrow(new ResourceNotFoundException("mv_song", 404L));

        // when / then
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> mvController.importAudio(null, "t", null, null, null));
        assertNotNull(ex);
        assertEquals("mv_song", ex.getResource());
        assertEquals(404L, ex.getId());
    }

    @Test
    void lyricsWrapsServiceExceptionAsInternalServerError() {
        // given
        when(mvService.generateLyrics(anyLong())).thenThrow(new RuntimeException("boom"));

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.lyrics(5L);

        // then
        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("FAILED", resp.getBody().get("status"));
        assertTrue(resp.getBody().get("error").toString().contains("boom"));
    }

    @Test
    void lyricsReturnsLyricsJsonWhenServiceSucceeds() {
        // given
        MvSong song = newSong(9L, "LYRICS_READY", 900L);
        song.setLyricsJson("{\"lines\":[\"a\"]}");
        when(mvService.generateLyrics(9L)).thenReturn(song);

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.lyrics(9L);

        // then
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("SUCCEEDED", resp.getBody().get("status"));
        assertEquals("{\"lines\":[\"a\"]}", resp.getBody().get("lyricsJson"));
    }

    @Test
    void composeParsesNumericAndStringProviderIdAndModelId() {
        // given
        MvSong numeric = newSong(1L, "COMPOSED", 10L);
        numeric.setAudioUrl("http://a/1.mp3");
        numeric.setDurationMs(5000);
        MvSong stringy = newSong(2L, "COMPOSED", 20L);
        stringy.setAudioUrl(null);
        stringy.setDurationMs(null);

        when(mvService.compose(eq(1L), eq(123L), eq("m1"))).thenReturn(numeric);
        when(mvService.compose(eq(2L), eq(456L), eq("99"))).thenReturn(stringy);

        Map<String, Object> bodyNumeric = new HashMap<>();
        bodyNumeric.put("providerId", 123);
        bodyNumeric.put("modelId", "m1");
        Map<String, Object> bodyString = new HashMap<>();
        bodyString.put("providerId", "456");
        bodyString.put("modelId", 99);

        // when
        ResponseEntity<Map<String, Object>> r1 = mvController.compose(1L, bodyNumeric);
        ResponseEntity<Map<String, Object>> r2 = mvController.compose(2L, bodyString);

        // then
        assertEquals(HttpStatus.OK, r1.getStatusCode());
        assertEquals("http://a/1.mp3", r1.getBody().get("audioUrl"));
        assertEquals(5000, r1.getBody().get("durationMs")); // MvSong.durationMs 是 Integer，controller 原样放入 map

        assertEquals(HttpStatus.OK, r2.getStatusCode());
        assertEquals("", r2.getBody().get("audioUrl"));
        assertEquals(0, r2.getBody().get("durationMs"));

        verify(mvService, times(1)).compose(eq(1L), eq(123L), eq("m1"));
        verify(mvService, times(1)).compose(eq(2L), eq(456L), eq("99"));
    }

    @Test
    void composeWithNullBodyPassesNullProviderAndModel() {
        // given
        MvSong song = newSong(3L, "COMPOSED", 30L);
        when(mvService.compose(eq(3L), eq((Long) null), eq((String) null))).thenReturn(song);

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.compose(3L, null);

        // then
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("SUCCEEDED", resp.getBody().get("status"));
        verify(mvService, times(1)).compose(eq(3L), eq((Long) null), eq((String) null));
    }

    @Test
    void composeMapsIllegalStateToBadRequest() {
        // given
        when(mvService.compose(anyLong(), any(), any()))
                .thenThrow(new IllegalStateException("状态不合法"));

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.compose(8L, new HashMap<>());

        // then
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
        assertEquals("FAILED", resp.getBody().get("status"));
        assertTrue(resp.getBody().get("error").toString().contains("状态不合法"));
    }

    @Test
    void storyboardReturnsItemsList() {
        // given
        List<Map<String, String>> items = new ArrayList<>();
        Map<String, String> it = new HashMap<>();
        it.put("shot", "1");
        it.put("desc", "open");
        items.add(it);
        when(mvService.storyboard(11L)).thenReturn(items);

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.storyboard(11L);

        // then
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("SUCCEEDED", resp.getBody().get("status"));
        assertSame(items, resp.getBody().get("items"));
    }

    @Test
    void storyboardOnEmptyListReturnsSucceededWithEmptyItems() {
        // given
        when(mvService.storyboard(12L)).thenReturn(Collections.emptyList());

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.storyboard(12L);

        // then
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("SUCCEEDED", resp.getBody().get("status"));
        assertTrue(((List<?>) resp.getBody().get("items")).isEmpty());
    }

    @Test
    void renderDefaultDryRunTrueAndReturnsVideoUrl() {
        // given
        when(mvService.render(eq(21L), eq(true))).thenReturn(newSong(21L, "RENDERED", 210L));

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.render(21L, true);

        // then
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("SUCCEEDED", resp.getBody().get("status"));
        assertEquals("/api/mv/21/video", resp.getBody().get("videoUrl"));
        verify(mvService, times(1)).render(eq(21L), eq(true));
    }

    @Test
    void renderIsIdempotentAcrossRepeatedCalls() {
        // given
        when(mvService.render(eq(22L), eq(false))).thenReturn(newSong(22L, "RENDERED", 220L));

        // when
        ResponseEntity<Map<String, Object>> first = mvController.render(22L, false);
        ResponseEntity<Map<String, Object>> second = mvController.render(22L, false);

        // then
        assertEquals(HttpStatus.OK, first.getStatusCode());
        assertEquals(HttpStatus.OK, second.getStatusCode());
        assertEquals(first.getBody().get("videoUrl"), second.getBody().get("videoUrl"));
        assertEquals(first.getBody().get("status"), second.getBody().get("status"));
        verify(mvService, times(2)).render(eq(22L), eq(false));
    }

    @Test
    void renderMapsResourceNotFoundThroughException() {
        // given
        when(mvService.render(anyLong(), anyBoolean()))
                .thenThrow(new ResourceNotFoundException("mv_song", 23L));

        // when / then
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> mvController.render(23L, true));
        assertEquals("mv_song", ex.getResource());
        assertEquals(23L, ex.getId());
    }

    @Test
    void getReturnsFullSongFields() {
        // given
        MvSong song = newSong(31L, "READY", 310L);
        when(mvService.getById(31L)).thenReturn(song);

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.get(31L);

        // then
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        Map<String, Object> out = resp.getBody();
        assertEquals(31L, out.get("id"));
        assertEquals("READY", out.get("status"));
        assertEquals("theme-31", out.get("theme"));
        assertEquals(310L, out.get("runId"));
        assertEquals("{\"t\":1}", out.get("timelineJson"));
    }

    @Test
    void getWithNullTimelineReturnsEmptyString() {
        // given
        MvSong song = newSong(32L, "READY", 320L);
        song.setTimelineJson(null);
        when(mvService.getById(32L)).thenReturn(song);

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.get(32L);

        // then
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("", resp.getBody().get("timelineJson"));
        assertEquals(32L, resp.getBody().get("id"));
    }

    @Test
    void getUnknownIdThrowsResourceNotFound() {
        // given
        when(mvService.getById(99L)).thenThrow(new ResourceNotFoundException("mv_song", 99L));

        // when / then
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> mvController.get(99L));
        assertEquals("mv_song", ex.getResource());
        assertEquals(99L, ex.getId());
    }

    @Test
    void statusIncludesStepStatusesFromService() {
        // given
        MvSong song = newSong(41L, "RUNNING", 410L);
        List<Map<String, String>> steps = new ArrayList<>();
        Map<String, String> s1 = new HashMap<>();
        s1.put("name", "compose");
        s1.put("state", "DONE");
        steps.add(s1);
        when(mvService.getById(41L)).thenReturn(song);
        when(mvService.getStepStatuses(410L)).thenReturn(steps);

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.status(41L);

        // then
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("RUNNING", resp.getBody().get("status"));
        assertEquals(410L, resp.getBody().get("runId"));
        assertSame(steps, resp.getBody().get("steps"));
    }

    @Test
    void statusWithNullRunIdReturnsEmptyStepsAndDoesNotThrow() {
        // given
        MvSong song = newSong(42L, "CREATED", null);
        when(mvService.getById(42L)).thenReturn(song);
        when(mvService.getStepStatuses(null)).thenReturn(Collections.emptyList());

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.status(42L);

        // then
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("CREATED", resp.getBody().get("status"));
        assertTrue(((List<?>) resp.getBody().get("steps")).isEmpty());
    }

    @Test
    void concurrentRenderOnSameRunProducesConsistentResults() throws Exception {
        // given
        final AtomicInteger calls = new AtomicInteger(0);
        final MvSong song = newSong(51L, "RENDERED", 510L);
        when(mvService.render(eq(51L), eq(true))).thenAnswer(inv -> {
            calls.incrementAndGet();
            return song;
        });

        int threads = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        List<Callable<ResponseEntity<Map<String, Object>>>> tasks = new ArrayList<>();
        for (int i = 0; i < threads; i++) {
            tasks.add(() -> {
                start.await();
                return mvController.render(51L, true);
            });
        }

        // when
        List<Future<ResponseEntity<Map<String, Object>>>> futures = new ArrayList<>();
        for (Callable<ResponseEntity<Map<String, Object>>> t : tasks) {
            futures.add(pool.submit(t));
        }
        start.countDown();

        // then
        for (Future<ResponseEntity<Map<String, Object>>> f : futures) {
            ResponseEntity<Map<String, Object>> r = f.get(5, TimeUnit.SECONDS);
            assertEquals(HttpStatus.OK, r.getStatusCode());
            assertEquals("SUCCEEDED", r.getBody().get("status"));
            assertEquals("/api/mv/51/video", r.getBody().get("videoUrl"));
        }
        assertEquals(threads, calls.get());
        pool.shutdown();
        assertTrue(pool.awaitTermination(5, TimeUnit.SECONDS));
    }

    @Test
    void videoRejectsIllegalIdPatternBeforeTouchingFilesystem() {
        // given
        long badId = -1L;

        // when / then
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> mvController.video(badId));
        assertEquals("mv_video", ex.getResource());
        assertEquals(badId, ex.getId());
    }

    @Test
    void videoMissingFileThrowsResourceNotFound() {
        // given
        long id = 600000L;

        // when / then
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> mvController.video(id));
        assertEquals("mv_video", ex.getResource());
        assertEquals(id, ex.getId());
    }

    @Test
    void largePayloadCreateIsHandledAndPassedToService() {
        // given
        StringBuilder big = new StringBuilder();
        for (int i = 0; i < 200000; i++) {
            big.append('x');
        }
        String hugeTheme = big.toString();
        Map<String, String> body = new HashMap<>();
        body.put("theme", hugeTheme);
        body.put("mood", "epic");
        body.put("style", "cinematic");
        when(mvService.create(eq(hugeTheme), eq("epic"), eq("cinematic"))).thenReturn(999L);

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.create(body);

        // then
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("SUCCEEDED", resp.getBody().get("status"));
        assertEquals(999L, resp.getBody().get("id"));
        verify(mvService, times(1)).create(eq(hugeTheme), eq("epic"), eq("cinematic"));
    }

    @Test
    void createWithNullBodyReturnsBadRequestNotServerError() {
        // given
        Map<String, String> body = null;

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.create(body);

        // then
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
        assertEquals("FAILED", resp.getBody().get("status"));
        assertFalse(resp.getBody().containsKey("id"));
    }

    @Test
    void importAudioSuccessReturnsFieldsAndDefaultsForNulls() {
        // given
        MvSong song = newSong(71L, "IMPORTED", 710L);
        song.setAudioUrl(null);
        song.setDurationMs(null);
        when(mvService.importAudio(any(), eq("t"), eq("l"), eq("m"), eq("s"))).thenReturn(song);

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.importAudio(null, "t", "l", "m", "s");

        // then
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("SUCCEEDED", resp.getBody().get("status"));
        assertEquals(71L, resp.getBody().get("id"));
        assertEquals("", resp.getBody().get("audioUrl"));
        assertEquals(0, resp.getBody().get("durationMs"));
    }

    @Test
    void importAudioIllegalArgumentReturnsBadRequest() {
        // given
        when(mvService.importAudio(any(), any(), any(), any(), any()))
                .thenThrow(new IllegalArgumentException("标题为空"));

        // when
        ResponseEntity<Map<String, Object>> resp = mvController.importAudio(null, "", null, null, null);

        // then
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
        assertEquals("FAILED", resp.getBody().get("status"));
        assertTrue(resp.getBody().get("error").toString().contains("标题为空"));
    }
}