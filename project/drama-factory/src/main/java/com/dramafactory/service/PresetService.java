package com.dramafactory.service;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.service.ProviderService.ProviderDto;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

/**
 * 供应商预设服务：base URL 与模型 id 预填好的流行提供商模板。
 * 用户粘贴自己的 key 即可用；创建后成为普通供应商，可编辑可删除。
 * 预设会过期：数据在 presets.json，过期了直接改该文件。
 */
@Service
public class PresetService {

    /** 预设模型条目 */
    public record PresetModel(
            String displayName,
            String modelId,
            String scale,
            String description,
            Integer concurrency) {
    }

    /** 预设供应商模板 */
    public record Preset(
            String id,
            String module,
            String name,
            String description,
            String apiAddress,
            List<PresetModel> models) {
    }

    private final List<Preset> presets;
    private final ProviderService providerService;

    public PresetService(ProviderService providerService) {
        this.providerService = providerService;
        this.presets = loadPresets();
    }

    private List<Preset> loadPresets() {
        try (InputStream in = new ClassPathResource("presets.json").getInputStream()) {
            ObjectMapper mapper = new ObjectMapper();
            List<Preset> list = mapper.readValue(in, new TypeReference<List<Preset>>() {
            });
            return list == null ? List.of() : list;
        } catch (Exception e) {
            throw new IllegalStateException("presets.json 加载失败", e);
        }
    }

    /** 列出预设；module 为空查全部 */
    public List<Preset> listPresets(String module) {
        if (module == null || module.isEmpty()) {
            return new ArrayList<>(presets);
        }
        List<Preset> result = new ArrayList<>();
        for (Preset p : presets) {
            if (module.equals(p.module())) {
                result.add(p);
            }
        }
        return result;
    }

    /** 按 id 取预设，不存在抛 404 */
    public Preset getPreset(String presetId) {
        for (Preset p : presets) {
            if (p.id().equals(presetId)) {
                return p;
            }
        }
        throw new ResourceNotFoundException("preset", null);
    }

    /**
     * 从预设创建供应商：用户只填 key，base URL 与模型照预设写入。
     * 建好后是普通供应商，可编辑可删除。
     */
    @Transactional
    public ProviderDto createFromPreset(String presetId, String apiKey) {
        if (apiKey == null || apiKey.trim().isEmpty()) {
            throw new IllegalArgumentException("apiKey must not be blank");
        }
        Preset preset = getPreset(presetId);
        ProviderDto dto = providerService.createProvider(
                preset.name(), preset.module(), preset.description(), apiKey.trim(), preset.apiAddress());
        if (preset.models() != null) {
            for (PresetModel m : preset.models()) {
                providerService.addModel(dto.id(), m.displayName(), m.modelId(),
                        m.scale(), m.description(), m.concurrency());
            }
        }
        return providerService.listProviders().stream()
                .filter(p -> p.id().equals(dto.id()))
                .findFirst()
                .orElse(dto);
    }
}
