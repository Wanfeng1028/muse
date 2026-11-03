package com.dramafactory.service;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class CanvasEventServiceTest {

    static class CapturingEventService extends CanvasEventService {
        final List<String> names = Collections.synchronizedList(new ArrayList<>());
        final List<String> payloads = Collections.synchronizedList(new ArrayList<>());

        @Override
        void sendEvent(SseEmitter emitter, String name, String json) {
            names.add(name);
            payloads.add(json);
        }
    }

    private static void awaitSize(List<?> list, int n) throws InterruptedException {
        long deadline = System.currentTimeMillis() + 5000;
        while (System.currentTimeMillis() < deadline && list.size() < n) {
            Thread.sleep(50);
        }
    }

    @Test
    void subscribe_sendsConnectedWithVersion() throws Exception {
        CapturingEventService service = new CapturingEventService();
        SseEmitter emitter = service.subscribe(7);
        assertNotNull(emitter);
        awaitSize(service.names, 1);
        assertTrue(service.names.contains("connected"), "应收到 connected，实际: " + service.names);
        String payload = service.payloads.get(service.names.indexOf("connected"));
        assertTrue(payload.contains("\"version\":7"), "connected 应带 version=7，实际: " + payload);
    }

    @Test
    void broadcast_reachesAllSubscribers() throws Exception {
        CapturingEventService service = new CapturingEventService();
        service.subscribe(1);
        service.subscribe(1);
        awaitSize(service.names, 2); // 等两个 connected 都发完，避免晚到的 connected 污染断言
        service.names.clear();
        service.payloads.clear();
        service.broadcast("canvas.changed", Map.of("version", 8, "kind", "save"));
        awaitSize(service.names, 2);
        assertEquals(2, service.names.size(), "两个订阅者都应收到，实际: " + service.names);
        assertTrue(service.names.stream().allMatch("canvas.changed"::equals));
        assertTrue(service.payloads.stream().allMatch(p -> p.contains("\"version\":8")));
    }
}
