package com.dramafactory.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeUnit;

@Service
public class CanvasEventService {

    private final CopyOnWriteArrayList<SseEmitter> emitters = new CopyOnWriteArrayList<>();
    private final ObjectMapper objectMapper = new ObjectMapper();

    public SseEmitter subscribe(int version) {
        SseEmitter emitter = new SseEmitter(30 * 60 * 1000L);
        emitters.add(emitter);
        emitter.onCompletion(() -> emitters.remove(emitter));
        emitter.onTimeout(() -> emitters.remove(emitter));
        emitter.onError(e -> emitters.remove(emitter));
        CompletableFuture.delayedExecutor(100, TimeUnit.MILLISECONDS).execute(() -> {
            Map<String, Object> connected = new LinkedHashMap<>();
            connected.put("version", version);
            try {
                sendEvent(emitter, "connected", objectMapper.writeValueAsString(connected));
            } catch (IOException e) {
                emitters.remove(emitter);
            }
        });
        return emitter;
    }

    public void broadcast(String name, Map<String, Object> dataMap) {
        String json;
        try {
            json = objectMapper.writeValueAsString(dataMap);
        } catch (IOException e) {
            return;
        }
        for (SseEmitter emitter : emitters) {
            sendEvent(emitter, name, json);
        }
    }

    void sendEvent(SseEmitter emitter, String name, String json) {
        try {
            emitter.send(SseEmitter.event().name(name).data(json));
        } catch (Exception e) {
            emitters.remove(emitter);
        }
    }
}
