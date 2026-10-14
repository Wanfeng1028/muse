package com.dramafactory.controller;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.MvSong;
import com.dramafactory.service.MvService;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/mv")
@Tag(name = "AI MV")
public class MvController {

    private final MvService mvService;
    private final String storageDir;

    public MvController(MvService mvService,
                        @Value("${drama.storage:./data/media}") String storageDir) {
        this.mvService = mvService;
        this.storageDir = storageDir;
    }

    @PostMapping("")
    public ResponseEntity<Map<String, Object>> create(@RequestBody Map<String, String> body) {
        try {
            String theme = body == null ? null : body.get("theme");
            if (theme == null || theme.isBlank()) {
                throw new IllegalArgumentException("theme 不能为空");
            }
            String mood = body.get("mood");
            String style = body.get("style");
            Long id = mvService.create(theme, mood, style);
            return ResponseEntity.ok(Map.of("status", "SUCCEEDED", "id", id));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("status", "FAILED", "error", safe(e)));
        } catch (ResourceNotFoundException e) {
            throw e;
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("status", "FAILED", "error", safe(e)));
        }
    }

    @PostMapping("/{id}/lyrics")
    public ResponseEntity<Map<String, Object>> lyrics(@PathVariable Long id) {
        try {
            MvSong song = mvService.generateLyrics(id);
            return ResponseEntity.ok(Map.of(
                    "status", "SUCCEEDED",
                    "lyricsJson", song.getLyricsJson() == null ? "" : song.getLyricsJson()));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("status", "FAILED", "error", safe(e)));
        } catch (ResourceNotFoundException e) {
            throw e;
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("status", "FAILED", "error", safe(e)));
        }
    }

    @PostMapping("/{id}/compose")
    public ResponseEntity<Map<String, Object>> compose(@PathVariable Long id,
                                                       @RequestBody Map<String, Object> body) {
        try {
            Long providerId = null;
            String modelId = null;
            if (body != null) {
                Object pid = body.get("providerId");
                if (pid instanceof Number n) {
                    providerId = n.longValue();
                } else if (pid instanceof String s && !s.isBlank()) {
                    providerId = Long.parseLong(s);
                }
                Object mid = body.get("modelId");
                if (mid != null) {
                    modelId = String.valueOf(mid);
                }
            }
            MvSong song = mvService.compose(id, providerId, modelId);
            return ResponseEntity.ok(Map.of(
                    "status", "SUCCEEDED",
                    "audioUrl", song.getAudioUrl() == null ? "" : song.getAudioUrl()));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("status", "FAILED", "error", safe(e)));
        } catch (ResourceNotFoundException e) {
            throw e;
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("status", "FAILED", "error", safe(e)));
        }
    }

    @PostMapping("/{id}/storyboard")
    public ResponseEntity<Map<String, Object>> storyboard(@PathVariable Long id) {
        try {
            List<Map<String, String>> sections = mvService.storyboard(id);
            return ResponseEntity.ok(Map.of("status", "SUCCEEDED", "sections", sections));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("status", "FAILED", "error", safe(e)));
        } catch (ResourceNotFoundException e) {
            throw e;
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("status", "FAILED", "error", safe(e)));
        }
    }

    @PostMapping("/{id}/render")
    public ResponseEntity<Map<String, Object>> render(@PathVariable Long id,
                                                      @RequestParam(name = "dryRun", defaultValue = "true") boolean dryRun) {
        try {
            mvService.render(id, dryRun);
            return ResponseEntity.ok(Map.of(
                    "status", "SUCCEEDED",
                    "videoUrl", "/api/mv/" + id + "/video"));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("status", "FAILED", "error", safe(e)));
        } catch (ResourceNotFoundException e) {
            throw e;
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("status", "FAILED", "error", safe(e)));
        }
    }

    @GetMapping("/{id}")
    public ResponseEntity<Map<String, Object>> get(@PathVariable Long id) {
        try {
            MvSong song = mvService.getById(id);
            Map<String, Object> out = new HashMap<>();
            out.put("id", song.getId());
            out.put("theme", song.getTheme());
            out.put("mood", song.getMood());
            out.put("style", song.getStyle());
            out.put("status", song.getStatus());
            out.put("audioUrl", song.getAudioUrl());
            out.put("durationMs", song.getDurationMs());
            out.put("runId", song.getRunId());
            return ResponseEntity.ok(out);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("status", "FAILED", "error", safe(e)));
        } catch (ResourceNotFoundException e) {
            throw e;
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("status", "FAILED", "error", safe(e)));
        }
    }

    @GetMapping("/{id}/status")
    public ResponseEntity<Map<String, Object>> status(@PathVariable Long id) {
        try {
            MvSong song = mvService.getById(id);
            Map<String, Object> out = new HashMap<>();
            out.put("id", song.getId());
            out.put("status", song.getStatus());
            out.put("runId", song.getRunId());
            out.put("steps", mvService.getStepStatuses(song.getRunId()));
            return ResponseEntity.ok(out);
        } catch (ResourceNotFoundException e) {
            throw e;
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("status", "FAILED", "error", safe(e)));
        }
    }

    @GetMapping("/{id}/video")
    public ResponseEntity<Resource> video(@PathVariable Long id) {
        String sid = String.valueOf(id);
        if (!sid.matches("^[A-Za-z0-9._-]{1,128}$")) {
            throw new ResourceNotFoundException("mv_video", id);
        }
        Path baseDir = Paths.get(storageDir, "mv").normalize();
        Path target = baseDir.resolve(sid).resolve("final.mp4").normalize();
        if (!target.startsWith(baseDir)) {
            throw new ResourceNotFoundException("mv_video", id);
        }
        if (!Files.exists(target) || !Files.isRegularFile(target)) {
            throw new ResourceNotFoundException("mv_video", id);
        }
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("video/mp4"))
                .body(new FileSystemResource(target));
    }

    private static String safe(Exception e) {
        String m = e.getMessage();
        return m == null ? "操作失败" : (m.length() > 300 ? m.substring(0, 300) : m);
    }
}
