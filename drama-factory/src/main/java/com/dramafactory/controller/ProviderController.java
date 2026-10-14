package com.dramafactory.controller;

import com.dramafactory.service.PresetService;
import com.dramafactory.service.ProviderService;
import com.dramafactory.service.ProviderService.ModelDto;
import com.dramafactory.service.ProviderService.ProviderDto;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * 媒体供应商卡片制接口。
 * 注意：任何响应都不会包含 apiKey 原文。
 */
@RestController
@RequestMapping("/api/providers")
@Tag(name = "Providers", description = "媒体供应商与模型的增删改查接口")
public class ProviderController {

    private final ProviderService providerService;

    private final PresetService presetService;

    public ProviderController(ProviderService providerService, PresetService presetService) {
        this.providerService = providerService;
        this.presetService = presetService;
    }

    /* ---------- 请求体 ---------- */

    public record ProviderCreateRequest(
            String name,
            String module,
            String description,
            String apiKey,
            String apiAddress
    ) {}

    public record ProviderUpdateRequest(
            String name,
            String module,
            String description,
            String apiKey,
            String apiAddress,
            Boolean enabled
    ) {}

    public record ModelUpsertRequest(
            String displayName,
            String modelId,
            String scale,
            String description,
            Integer concurrency,
            Boolean enabled
    ) {}

    /* ---------- 供应商 ---------- */

    @GetMapping
    @Operation(summary = "查询供应商列表")
    public List<ProviderDto> listProviders(@RequestParam(required = false) String module) {
        return providerService.listProviders(module);
    }

    /** 供应商模块清单：VIDEO/IMAGE/MUSIC/TTS/AVATAR */
    @GetMapping("/modules")
    @Operation(summary = "查询供应商模块清单")
    public List<Map<String, String>> listModules() {
        return List.of(
                Map.of("id", "VIDEO", "label", "视频"),
                Map.of("id", "TEXT", "label", "文本"),
                Map.of("id", "IMAGE", "label", "图片"),
                Map.of("id", "MUSIC", "label", "音乐"),
                Map.of("id", "TTS", "label", "TTS 语音"),
                Map.of("id", "AVATAR", "label", "数字人"));
    }

    @PostMapping
    @Operation(summary = "创建供应商")
    public ResponseEntity<ProviderDto> createProvider(@RequestBody ProviderCreateRequest req) {
        if (req.name() == null || req.name().trim().isEmpty()) {
            return ResponseEntity.badRequest().build();
        }
        ProviderDto dto = providerService.createProvider(
                req.name(), req.module(), req.description(), req.apiKey(), req.apiAddress());
        return ResponseEntity.ok(dto);
    }

    @PutMapping("/{id}")
    @Operation(summary = "更新供应商")
    public ResponseEntity<ProviderDto> updateProvider(@PathVariable Long id,
                                                      @RequestBody ProviderUpdateRequest req) {
        if (req.name() == null || req.name().trim().isEmpty()) {
            return ResponseEntity.badRequest().build();
        }
        ProviderDto dto = providerService.updateProvider(
                id, req.name(), req.module(), req.description(), req.apiKey(), req.apiAddress(), req.enabled());
        return ResponseEntity.ok(dto);
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "删除供应商")
    public ResponseEntity<Void> deleteProvider(@PathVariable Long id) {
        providerService.deleteProvider(id);
        return ResponseEntity.noContent().build();
    }

    /* ---------- 模型 ---------- */

    @PostMapping("/{id}/models")
    @Operation(summary = "新增供应商模型")
    public ResponseEntity<ModelDto> addModel(@PathVariable Long id,
                                             @RequestBody ModelUpsertRequest req) {
        if (req.displayName() == null || req.displayName().trim().isEmpty()) {
            return ResponseEntity.badRequest().build();
        }
        ModelDto dto = providerService.addModel(
                id, req.displayName(), req.modelId(), req.scale(), req.description(), req.concurrency());
        return ResponseEntity.ok(dto);
    }

    @PutMapping("/{id}/models/{modelId}")
    @Operation(summary = "更新供应商模型")
    public ResponseEntity<ModelDto> updateModel(@PathVariable Long id,
                                                @PathVariable Long modelId,
                                                @RequestBody ModelUpsertRequest req) {
        if (req.displayName() == null || req.displayName().trim().isEmpty()) {
            return ResponseEntity.badRequest().build();
        }
        // provider_id 由路径决定，请求体里即便传了 provider_id 也忽略
        ModelDto dto = providerService.updateModel(
                id, modelId, req.displayName(), req.modelId(),
                req.scale(), req.description(), req.concurrency(), req.enabled());
        return ResponseEntity.ok(dto);
    }

    @DeleteMapping("/{id}/models/{modelId}")
    @Operation(summary = "删除供应商模型")
    public ResponseEntity<Void> deleteModel(@PathVariable Long id,
                                            @PathVariable Long modelId) {
        providerService.deleteModel(id, modelId);
        return ResponseEntity.noContent().build();
    }

    /* ---------- 预设 ---------- */

    /** 供应商预设模板：base URL 与模型 id 预填，用户只填 key */
    @GetMapping("/presets")
    @Operation(summary = "查询供应商预设模板")
    public List<PresetService.Preset> listPresets(@RequestParam(required = false) String module) {
        return presetService.listPresets(module);
    }

    public record FromPresetRequest(String presetId, String apiKey) {
    }

    /** 从预设创建供应商：用户只填自己的 key */
    @PostMapping("/from-preset")
    @Operation(summary = "从预设创建供应商")
    public ResponseEntity<ProviderDto> createFromPreset(@RequestBody FromPresetRequest req) {
        if (req.presetId() == null || req.presetId().trim().isEmpty()
                || req.apiKey() == null || req.apiKey().trim().isEmpty()) {
            return ResponseEntity.badRequest().build();
        }
        return ResponseEntity.ok(presetService.createFromPreset(req.presetId().trim(), req.apiKey()));
    }

    /** 供应商连接自检：真实探测，只报告真实结论，不伪造成功 */
    @PostMapping("/{id}/test")
    @Operation(summary = "供应商连接自检")
    public ProviderService.TestConnectionResponse testConnection(@PathVariable Long id) {
        return providerService.testConnection(id);
    }
}
