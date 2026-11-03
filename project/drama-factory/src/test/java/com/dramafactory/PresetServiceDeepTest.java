package com.dramafactory;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.repository.DramaCharacterRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.SceneRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.PresetService;
import com.dramafactory.service.PresetService.Preset;
import com.dramafactory.service.PresetService.PresetModel;
import com.dramafactory.service.ProviderService;
import com.dramafactory.service.ProviderService.ProviderDto;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * PresetService 深测：预设 CRUD、默认值回填、非法参数拒绝。
 */
@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:presetdeep;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class PresetServiceDeepTest {

    @Autowired
    private PresetService presetService;

    @Autowired
    private ProviderService providerService;

    @Autowired
    private VideoTaskRepository videoTaskRepository;

    @Autowired
    private ShotRepository shotRepository;

    @Autowired
    private SceneRepository sceneRepository;

    @Autowired
    private DramaCharacterRepository characterRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private DramaProjectRepository projectRepository;

    @BeforeEach
    void cleanUp() {
        videoTaskRepository.deleteAll();
        shotRepository.deleteAll();
        sceneRepository.deleteAll();
        characterRepository.deleteAll();
        episodeRepository.deleteAll();
        projectRepository.deleteAll();
    }

    /** 预设列表应非空（presets.json 至少有一条） */
    @Test
    void listPresets_all_returnsNonEmpty() {
        List<Preset> all = presetService.listPresets(null);
        assertFalse(all.isEmpty(), "全部预设不应为空");
    }

    /** module 为 null 与空串都视为查全部 */
    @Test
    void listPresets_nullAndEmptyReturnAll() {
        List<Preset> viaNull = presetService.listPresets(null);
        List<Preset> viaEmpty = presetService.listPresets("");
        assertEquals(viaNull.size(), viaEmpty.size(), "null 与空串结果条数应一致");
    }

    /** 按 module 过滤，只返回该 module 的预设 */
    @Test
    void listPresets_byModule_filtersCorrectly() {
        List<Preset> all = presetService.listPresets(null);
        assertFalse(all.isEmpty(), "全部预设不应为空");
        String module = all.get(0).module();
        assertNotNull(module, "预设 module 不应为 null");
        List<Preset> filtered = presetService.listPresets(module);
        assertFalse(filtered.isEmpty(), "按已知 module 过滤不应为空");
        for (Preset p : filtered) {
            assertEquals(module, p.module(), "过滤结果的 module 应一致");
        }
    }

    /** 未知 module 返回空列表 */
    @Test
    void listPresets_unknownModule_returnsEmpty() {
        List<Preset> filtered = presetService.listPresets("__no_such_module__");
        assertTrue(filtered.isEmpty(), "未知 module 应返回空列表");
    }

    /** 返回的列表应为副本，修改不影响内部状态 */
    @Test
    void listPresets_returnsMutableCopy() {
        List<Preset> first = presetService.listPresets(null);
        int sizeBefore = first.size();
        first.clear();
        List<Preset> second = presetService.listPresets(null);
        assertEquals(sizeBefore, second.size(), "清空外部列表不应影响内部预设集合");
    }

    /** 按已知 id 取预设成功 */
    @Test
    void getPreset_existingId_returnsPreset() {
        Preset any = presetService.listPresets(null).get(0);
        Preset fetched = presetService.getPreset(any.id());
        assertNotNull(fetched, "已知 id 应能取到预设");
        assertEquals(any.id(), fetched.id(), "取回的 id 应一致");
    }

    /** 不存在的 id 抛 ResourceNotFoundException */
    @Test
    void getPreset_unknownId_throwsNotFound() {
        assertThrows(ResourceNotFoundException.class,
                () -> presetService.getPreset("__no_such_preset__"));
    }

    /** id 为 null 抛 ResourceNotFoundException（内部 equals 不匹配） */
    @Test
    void getPreset_nullId_throwsNotFound() {
        assertThrows(ResourceNotFoundException.class,
                () -> presetService.getPreset(null));
    }

    /** 正常从预设创建供应商：默认值应回填 name/module/description/apiAddress */
    @Test
    void createFromPreset_validKey_createsProviderWithPresetDefaults() {
        Preset preset = presetService.listPresets(null).get(0);
        ProviderDto dto = presetService.createFromPreset(preset.id(), "sk-test-123");
        assertNotNull(dto, "创建结果不应为 null");
        assertNotNull(dto.id(), "新建供应商应有 id");
        assertEquals(preset.name(), dto.name(), "name 应回填预设值");
        assertEquals(preset.module(), dto.module(), "module 应回填预设值");
        assertEquals(preset.description(), dto.description(), "description 应回填预设值");
        assertEquals(preset.apiAddress(), dto.apiAddress(), "apiAddress 应回填预设值");
    }

    /** apiKey 前后空白应被 trim */
    @Test
    void createFromPreset_keyWithWhitespace_isTrimmed() {
        Preset preset = presetService.listPresets(null).get(0);
        ProviderDto dto = presetService.createFromPreset(preset.id(), "  sk-trim-me  ");
        assertNotNull(dto, "创建结果不应为 null");
        ProviderDto reloaded = providerService.listProviders().stream()
                .filter(p -> p.id().equals(dto.id()))
                .findFirst()
                .orElseThrow();
        assertNotNull(reloaded.maskedKey(), "maskedKey 不应为 null");
        assertFalse(reloaded.maskedKey().contains(" "), "maskedKey 不应含空格（trim 已生效）");
    }

    /** apiKey 为 null 抛 IllegalArgumentException */
    @Test
    void createFromPreset_nullKey_throwsIllegalArgument() {
        Preset preset = presetService.listPresets(null).get(0);
        assertThrows(IllegalArgumentException.class,
                () -> presetService.createFromPreset(preset.id(), null));
    }

    /** apiKey 为空白串抛 IllegalArgumentException */
    @Test
    void createFromPreset_blankKey_throwsIllegalArgument() {
        Preset preset = presetService.listPresets(null).get(0);
        assertThrows(IllegalArgumentException.class,
                () -> presetService.createFromPreset(preset.id(), "   "));
    }

    /** 空串 apiKey 抛 IllegalArgumentException */
    @Test
    void createFromPreset_emptyKey_throwsIllegalArgument() {
        Preset preset = presetService.listPresets(null).get(0);
        assertThrows(IllegalArgumentException.class,
                () -> presetService.createFromPreset(preset.id(), ""));
    }

    /** 未知 presetId 抛 ResourceNotFoundException */
    @Test
    void createFromPreset_unknownPreset_throwsNotFound() {
        assertThrows(ResourceNotFoundException.class,
                () -> presetService.createFromPreset("__no_such_preset__", "sk-test-123"));
    }

    /** 预设的模型应被逐个写入新供应商 */
    @Test
    void createFromPreset_presetModels_areAddedToProvider() {
        Preset preset = null;
        for (Preset p : presetService.listPresets(null)) {
            if (p.models() != null && !p.models().isEmpty()) {
                preset = p;
                break;
            }
        }
        assertNotNull(preset, "至少应有一个带模型的预设");
        ProviderDto dto = presetService.createFromPreset(preset.id(), "sk-models-123");
        ProviderDto reloaded = providerService.listProviders().stream()
                .filter(p -> p.id().equals(dto.id()))
                .findFirst()
                .orElseThrow();
        assertNotNull(reloaded.models(), "新建供应商应有模型列表");
        assertEquals(preset.models().size(), reloaded.models().size(), "模型数量应与预设一致");
        for (PresetModel m : preset.models()) {
            boolean found = reloaded.models().stream()
                    .anyMatch(rm -> m.modelId().equals(rm.modelId()));
            assertTrue(found, "预设模型应被写入：" + m.modelId());
        }
    }

    /** 连续两次创建不同 key，应生成不同供应商且互不覆盖 */
    @Test
    void createFromPreset_calledTwice_producesDistinctProviders() {
        Preset preset = presetService.listPresets(null).get(0);
        int before = providerService.listProviders().size();
        ProviderDto first = presetService.createFromPreset(preset.id(), "sk-a");
        ProviderDto second = presetService.createFromPreset(preset.id(), "sk-b");
        assertNotNull(first.id(), "第一次应有 id");
        assertNotNull(second.id(), "第二次应有 id");
        assertFalse(first.id().equals(second.id()), "两次创建应得到不同 id");
        assertEquals(before + 2, providerService.listProviders().size(), "供应商数量应增加 2");
    }

    /** 创建后返回的对象应与仓库中记录一致（findFirst 回填） */
    @Test
    void createFromPreset_returnsReloadedProvider() {
        Preset preset = presetService.listPresets(null).get(0);
        ProviderDto dto = presetService.createFromPreset(preset.id(), "sk-reload");
        ProviderDto reloaded = providerService.listProviders().stream()
                .filter(p -> p.id().equals(dto.id()))
                .findFirst()
                .orElseThrow();
        assertEquals(reloaded.id(), dto.id(), "返回对象 id 应与仓库一致");
        assertEquals(reloaded.name(), dto.name(), "返回对象 name 应与仓库一致");
    }
}
