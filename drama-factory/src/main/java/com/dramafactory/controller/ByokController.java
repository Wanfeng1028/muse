package com.dramafactory.controller;

import com.dramafactory.service.byok.ByokGenerateService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

@RestController
@RequestMapping("/api/byok")
@Tag(name = "BYOK", description = "BYOK 生成调用接口")
public class ByokController {

    public record GenerateBody(String module, Long providerId, String modelId, String prompt, Map<String, String> options) {}

    private final ByokGenerateService generateService;
    private final String storageDir;
    private static final Set<String> MODULES = Set.of("IMAGE", "MUSIC", "AVATAR");
    private static final Set<String> FILE_MODULES = Set.of("image", "music", "avatar");
    private static final Pattern FILENAME_PATTERN = Pattern.compile("^[A-Za-z0-9._-]{1,128}$");

    public ByokController(ByokGenerateService generateService,
                          @Value("${drama.storage:./data/media}") String storageDir) {
        this.generateService = generateService;
        this.storageDir = storageDir;
    }

    @PostMapping("/generate")
    @Operation(summary = "BYOK 生成调用")
    public ResponseEntity<Map<String, String>> generate(@RequestBody GenerateBody body) {
        if (body == null || body.module() == null || !MODULES.contains(body.module())) {
            String moduleName = body == null ? "" : String.valueOf(body.module());
            return ResponseEntity.badRequest()
                    .body(Map.of("status", "FAILED", "error", "不支持的模块：" + moduleName));
        }
        if (body.providerId() == null || body.modelId() == null || body.modelId().isBlank()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("status", "FAILED", "error", "缺少必要参数"));
        }
        if (body.prompt() == null || body.prompt().isBlank()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("status", "FAILED", "error", "请填写提示词"));
        }
        try {
            ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                    body.module(),
                    body.providerId(),
                    body.modelId(),
                    body.prompt(),
                    body.options()
            );
            ByokGenerateService.GenerateResponse r = generateService.generate(req);
            return ResponseEntity.ok(Map.of(
                    "status", "SUCCEEDED",
                    "url", r.url() == null ? "" : r.url()
            ));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest()
                    .body(Map.of("status", "FAILED", "error", safe(e)));
        } catch (com.dramafactory.exception.ResourceNotFoundException e) {
            throw e;
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("status", "FAILED", "error", safe(e)));
        }
    }

    @GetMapping("/file/{module}/{filename}")
    @Operation(summary = "下载 BYOK 产物文件")
    public ResponseEntity<Resource> file(@PathVariable String module, @PathVariable String filename) {
        if (module == null || !FILE_MODULES.contains(module)) {
            return ResponseEntity.badRequest().build();
        }
        if (filename == null
                || filename.contains("..")
                || !FILENAME_PATTERN.matcher(filename).matches()) {
            return ResponseEntity.badRequest().build();
        }

        Path baseDir = Paths.get(storageDir, "byok", module).normalize();
        Path p = Paths.get(storageDir, "byok", module, filename).normalize();
        if (!p.startsWith(baseDir)) {
            return ResponseEntity.badRequest().build();
        }
        if (!Files.exists(p) || !Files.isReadable(p) || Files.isDirectory(p)) {
            return ResponseEntity.notFound().build();
        }

        MediaType mediaType = resolveMediaType(filename);
        return ResponseEntity.ok()
                .contentType(mediaType)
                .body(new FileSystemResource(p));
    }

    private static MediaType resolveMediaType(String filename) {
        String lower = filename.toLowerCase();
        int dot = lower.lastIndexOf('.');
        String ext = dot >= 0 ? lower.substring(dot + 1) : "";
        return switch (ext) {
            case "png" -> MediaType.IMAGE_PNG;
            case "jpg", "jpeg" -> MediaType.IMAGE_JPEG;
            case "mp3" -> MediaType.parseMediaType("audio/mpeg");
            case "mp4" -> MediaType.parseMediaType("video/mp4");
            default -> MediaType.APPLICATION_OCTET_STREAM;
        };
    }

    private static String safe(Exception e) {
        String msg = e.getMessage();
        if (msg == null || msg.isBlank()) {
            msg = e.getClass().getSimpleName();
        }
        return msg.length() > 500 ? msg.substring(0, 500) : msg;
    }
}
