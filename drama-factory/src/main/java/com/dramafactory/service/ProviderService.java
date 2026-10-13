package com.dramafactory.service;

import com.dramafactory.model.MediaProvider;
import com.dramafactory.model.ProviderModel;
import com.dramafactory.repository.MediaProviderRepository;
import com.dramafactory.repository.ProviderModelRepository;
import com.dramafactory.exception.ResourceNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * 供应商卡片制服务：供应商与模型的增删改查。
 * 密钥原文只进不出，对外一律返回掩码。
 */
@Service
public class ProviderService {

    /** 供应商模块：视频 / 图片 / 音乐 / TTS 语音 / 数字人 */
    public static final List<String> MODULES = List.of("VIDEO", "IMAGE", "MUSIC", "TTS", "AVATAR");

    private final MediaProviderRepository providerRepository;
    private final ProviderModelRepository modelRepository;

    public ProviderService(MediaProviderRepository providerRepository,
                           ProviderModelRepository modelRepository) {
        this.providerRepository = providerRepository;
        this.modelRepository = modelRepository;
    }

    /* ==================== DTO ==================== */

    /** 模型 DTO（对外） */
    public record ModelDto(
            Long id,
            String displayName,
            String modelId,
            String scale,
            String description,
            Integer concurrency,
            Boolean enabled
    ) {}

    /** 供应商 DTO（对外，key 只暴露掩码） */
    public record ProviderDto(
            Long id,
            String name,
            String module,
            String description,
            String maskedKey,
            String apiAddress,
            Boolean enabled,
            List<ModelDto> models
    ) {}

    /* ==================== 查询 ==================== */

    /**
     * 列出全部供应商及其模型，密钥以掩码形式返回。
     */
    @Transactional(readOnly = true)
    public List<ProviderDto> listProviders() {
        return listProviders(null);
    }

    /**
     * 列出供应商及其模型；module 为空查全部，否则按模块过滤。
     */
    @Transactional(readOnly = true)
    public List<ProviderDto> listProviders(String module) {
        List<MediaProvider> providers = (module == null || module.isEmpty())
                ? providerRepository.findAllByOrderByIdAsc()
                : providerRepository.findByModuleOrderByIdAsc(module);
        List<ProviderDto> result = new ArrayList<>(providers.size());
        for (MediaProvider p : providers) {
            result.add(toDto(p, modelRepository.findByProviderIdOrderByIdAsc(p.getId())));
        }
        return result;
    }

    /* ==================== 供应商 CRUD ==================== */

    /**
     * 创建供应商。
     */
    @Transactional
    public ProviderDto createProvider(String name, String module, String description, String apiKey, String apiAddress) {
        if (name == null || name.trim().isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        MediaProvider p = new MediaProvider();
        p.setName(name.trim());
        p.setModule(normalizeModule(module));
        p.setDescription(description);
        p.setApiKey(normalizeKey(apiKey));
        p.setApiAddress(apiAddress);
        p.setEnabled(Boolean.TRUE);
        LocalDateTime now = LocalDateTime.now();
        p.setCreatedAt(now);
        p.setUpdatedAt(now);
        MediaProvider saved = providerRepository.save(p);
        return toDto(saved, List.of());
    }

    /**
     * 更新供应商；apiKey 为空串或 null 时保留原值。
     */
    @Transactional
    public ProviderDto updateProvider(Long id, String name, String module, String description,
                                      String apiKey, String apiAddress, Boolean enabled) {
        MediaProvider p = providerRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("provider", id));
        if (name == null || name.trim().isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        p.setName(name.trim());
        if (module != null && !module.isEmpty()) {
            p.setModule(normalizeModule(module));
        }
        p.setDescription(description);
        if (apiKey != null && !apiKey.isEmpty()) {
            p.setApiKey(apiKey);
        }
        p.setApiAddress(apiAddress);
        if (enabled != null) {
            p.setEnabled(enabled);
        }
        p.setUpdatedAt(LocalDateTime.now());
        MediaProvider saved = providerRepository.save(p);
        return toDto(saved, modelRepository.findByProviderIdOrderByIdAsc(saved.getId()));
    }

    /**
     * 删除供应商，级联删除其模型。
     */
    @Transactional
    public void deleteProvider(Long id) {
        MediaProvider p = providerRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("provider", id));
        // 先删模型，保证不依赖数据库 FK 行为也正确（DB 侧同样有 ON DELETE CASCADE 兜底）
        modelRepository.deleteByProviderId(id);
        providerRepository.delete(p);
    }

    /* ==================== 模型 CRUD ==================== */

    /**
     * 新增模型。
     */
    @Transactional
    public ModelDto addModel(Long providerId, String displayName, String modelId,
                             String scale, String description, Integer concurrency) {
        MediaProvider p = providerRepository.findById(providerId)
                .orElseThrow(() -> new ResourceNotFoundException("provider", providerId));
        if (displayName == null || displayName.trim().isEmpty()) {
            throw new IllegalArgumentException("displayName must not be blank");
        }
        ProviderModel m = new ProviderModel();
        m.setProvider(p);
        m.setDisplayName(displayName.trim());
        m.setModelId(modelId);
        m.setScale(scale);
        m.setDescription(description);
        m.setConcurrency(concurrency == null ? 1 : concurrency);
        m.setEnabled(Boolean.TRUE);
        return toDto(modelRepository.save(m));
    }

    /**
     * 更新模型；provider_id 不可改。
     */
    @Transactional
    public ModelDto updateModel(Long providerId, Long modelId, String displayName,
                                String modelIdValue, String scale, String description,
                                Integer concurrency, Boolean enabled) {
        // 校验供应商存在
        providerRepository.findById(providerId)
                .orElseThrow(() -> new ResourceNotFoundException("provider", providerId));
        ProviderModel m = modelRepository.findById(modelId)
                .orElseThrow(() -> new ResourceNotFoundException("model", modelId));
        if (!m.getProvider().getId().equals(providerId)) {
            throw new ResourceNotFoundException("model", modelId);
        }
        if (displayName == null || displayName.trim().isEmpty()) {
            throw new IllegalArgumentException("displayName must not be blank");
        }
        m.setDisplayName(displayName.trim());
        m.setModelId(modelIdValue);
        m.setScale(scale);
        m.setDescription(description);
        if (concurrency != null) {
            m.setConcurrency(concurrency);
        }
        if (enabled != null) {
            m.setEnabled(enabled);
        }
        return toDto(modelRepository.save(m));
    }

    /**
     * 删除模型。
     */
    @Transactional
    public void deleteModel(Long providerId, Long modelId) {
        ProviderModel m = modelRepository.findById(modelId)
                .orElseThrow(() -> new ResourceNotFoundException("model", modelId));
        if (!m.getProvider().getId().equals(providerId)) {
            throw new ResourceNotFoundException("model", modelId);
        }
        modelRepository.delete(m);
    }

    /* ==================== 内部工具 ==================== */

    /** 模块归一化：空或非法值时回退 VIDEO */
    private String normalizeModule(String module) {
        if (module != null && MODULES.contains(module)) {
            return module;
        }
        return "VIDEO";
    }

    /** 空 key 归一化为 null；否则原样保存 */
    private String normalizeKey(String apiKey) {
        if (apiKey == null || apiKey.isEmpty()) {
            return null;
        }
        return apiKey;
    }

    /**
     * 掩码规则：
     * - key 为空 → ""
     * - key 长度 < 6 → "••••"
     * - 否则 → 首 2 字符 + "••••" + 末 4 字符
     */
    static String maskKey(String apiKey) {
        if (apiKey == null || apiKey.isEmpty()) {
            return "";
        }
        if (apiKey.length() < 6) {
            return "••••";
        }
        return apiKey.substring(0, 2) + "••••" + apiKey.substring(apiKey.length() - 4);
    }

    private ProviderDto toDto(MediaProvider p, List<ProviderModel> models) {
        List<ModelDto> modelDtos = new ArrayList<>(models.size());
        for (ProviderModel m : models) {
            modelDtos.add(toDto(m));
        }
        return new ProviderDto(
                p.getId(),
                p.getName(),
                p.getModule(),
                p.getDescription(),
                maskKey(p.getApiKey()),
                p.getApiAddress(),
                p.getEnabled(),
                modelDtos
        );
    }

    private ModelDto toDto(ProviderModel m) {
        return new ModelDto(
                m.getId(),
                m.getDisplayName(),
                m.getModelId(),
                m.getScale(),
                m.getDescription(),
                m.getConcurrency(),
                m.getEnabled()
        );
    }
}
