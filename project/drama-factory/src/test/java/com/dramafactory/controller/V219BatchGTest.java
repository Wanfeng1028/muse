package com.dramafactory.controller;

import com.dramafactory.service.SettingsService;
import com.dramafactory.service.video.VideoProviderRouter;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class V219BatchGTest {

    @Test
    void put_patchIsNull_skipsLoopAndSavesEmptyMap() {
        SettingsService settingsService = mock(SettingsService.class);
        Environment environment = mock(Environment.class);
        VideoProviderRouter router = mock(VideoProviderRouter.class);
        SettingsController controller = new SettingsController(settingsService, environment, router);

        when(settingsService.allowedKeys()).thenReturn(Set.of("a"));
        when(settingsService.maskedView()).thenReturn(Map.of());

        ResponseEntity<Map<String, Object>> resp = controller.put(null);

        assertEquals(HttpStatus.OK, resp.getStatusCode());

        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, String>> captor = ArgumentCaptor.forClass(Map.class);
        verify(settingsService, times(1)).saveAll(captor.capture());
        assertTrue(captor.getValue().isEmpty());
    }

    @Test
    void put_keyIsNull_returnsBadRequest() {
        SettingsService settingsService = mock(SettingsService.class);
        Environment environment = mock(Environment.class);
        VideoProviderRouter router = mock(VideoProviderRouter.class);
        SettingsController controller = new SettingsController(settingsService, environment, router);

        when(settingsService.allowedKeys()).thenReturn(Set.of("a"));

        Map<String, String> patch = new LinkedHashMap<>();
        patch.put(null, "v");

        ResponseEntity<Map<String, Object>> resp = controller.put(patch);

        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
        assertNotNull(resp.getBody());
        Object error = resp.getBody().get("error");
        assertNotNull(error);
        assertTrue(error.toString().startsWith("非法设置键"));
        verify(settingsService, never()).saveAll(any());
    }

    @Test
    void put_secretKeyWithBlankValue_isSkippedAndNotSaved() {
        SettingsService settingsService = mock(SettingsService.class);
        Environment environment = mock(Environment.class);
        VideoProviderRouter router = mock(VideoProviderRouter.class);
        SettingsController controller = new SettingsController(settingsService, environment, router);

        when(settingsService.allowedKeys()).thenReturn(Set.of("deepseek.api-key", "plain.key"));
        when(settingsService.maskedView()).thenReturn(Map.of());

        Map<String, String> map = new LinkedHashMap<>();
        map.put("deepseek.api-key", " ");

        ResponseEntity<Map<String, Object>> resp = controller.put(map);

        assertEquals(HttpStatus.OK, resp.getStatusCode());

        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, String>> captor = ArgumentCaptor.forClass(Map.class);
        verify(settingsService, times(1)).saveAll(captor.capture());
        assertFalse(captor.getValue().containsKey("deepseek.api-key"));
    }

    @Test
    void put_secretKeyWithNullValue_isSkippedAndNotSaved() {
        SettingsService settingsService = mock(SettingsService.class);
        Environment environment = mock(Environment.class);
        VideoProviderRouter router = mock(VideoProviderRouter.class);
        SettingsController controller = new SettingsController(settingsService, environment, router);

        when(settingsService.allowedKeys()).thenReturn(Set.of("deepseek.api-key", "plain.key"));
        when(settingsService.maskedView()).thenReturn(Map.of());

        Map<String, String> map = new LinkedHashMap<>();
        map.put("deepseek.api-key", null);

        ResponseEntity<Map<String, Object>> resp = controller.put(map);

        assertEquals(HttpStatus.OK, resp.getStatusCode());

        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, String>> captor = ArgumentCaptor.forClass(Map.class);
        verify(settingsService, times(1)).saveAll(captor.capture());
        assertFalse(captor.getValue().containsKey("deepseek.api-key"));
    }

    @Test
    void effectiveProvider_lastFallbackNotNull_includesLastFallback() {
        SettingsService settingsService = mock(SettingsService.class);
        Environment environment = mock(Environment.class);
        VideoProviderRouter router = mock(VideoProviderRouter.class);
        SettingsController controller = new SettingsController(settingsService, environment, router);

        when(environment.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        when(router.chain()).thenReturn(List.of("agnes"));
        when(router.lastFallback()).thenReturn(
                new VideoProviderRouter.LastFallback("agnes", "mock", "熔断", LocalDateTime.of(2026, 10, 15, 12, 0)));

        Map<String, Object> result = controller.effectiveProvider();

        assertNotNull(result);
        assertEquals("agnes", result.get("provider"));
        assertTrue(result.containsKey("lastFallback"));
        assertNotNull(result.get("lastFallback"));
    }
}