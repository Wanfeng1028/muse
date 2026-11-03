package com.dramafactory.service;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.service.ProviderService.ProviderDto;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class PresetServiceTest {

    private ProviderService providerService;
    private PresetService presetService;

    @BeforeEach
    void setUp() {
        providerService = mock(ProviderService.class);
        presetService = new PresetService(providerService);
    }

    // 覆盖 L55(mb=1)/L56(mi=1)/L57(mi=6)：module 为 null 时返回全部 16 条预设。
    @Test
    void listPresets_null_returnsAll() {
        List<PresetService.Preset> result = presetService.listPresets(null);
        assertEquals(16, result.size());
    }

    // 覆盖 L55(mb=1)/L56(mi=1)：module 为空字符串时同样返回全部 16 条预设。
    @Test
    void listPresets_empty_returnsAll() {
        List<PresetService.Preset> result = presetService.listPresets("");
        assertEquals(16, result.size());
    }

    // 覆盖 L63(mb=4)/L64(mi=6)：按 VIDEO 过滤返回 4 条且每条 module 都是 VIDEO。
    @Test
    void listPresets_video_returnsFour() {
        List<PresetService.Preset> result = presetService.listPresets("VIDEO");
        assertEquals(4, result.size());
        for (PresetService.Preset p : result) {
            assertEquals("VIDEO", p.module());
        }
    }

    // 覆盖 L63(mb=4)/L64(mi=6)：按 TEXT 过滤返回 6 条。
    @Test
    void listPresets_text_returnsSix() {
        List<PresetService.Preset> result = presetService.listPresets("TEXT");
        assertEquals(6, result.size());
    }

    // 覆盖 L63(mb=4)/L64(mi=6)：不存在的 module 返回空列表。
    @Test
    void listPresets_unknown_returnsEmpty() {
        List<PresetService.Preset> result = presetService.listPresets("NOT_EXIST");
        assertTrue(result.isEmpty());
    }

    // 覆盖 L63(mb=4)/L64(mi=6) 的命中分支：已知 id 返回对应预设。
    @Test
    void getPreset_existing_returnsPreset() {
        PresetService.Preset preset = presetService.getPreset("dashscope-video");
        assertNotNull(preset);
        assertEquals("dashscope-video", preset.id());
    }

    // 覆盖 L67(mb=2)/L68(mb=2)/L69(mi=4)：未知 id 抛 ResourceNotFoundException。
    @Test
    void getPreset_unknown_throws() {
        assertThrows(ResourceNotFoundException.class, () -> presetService.getPreset("no-such-id"));
    }

    // 覆盖 L77(mb=2)/L78(mb=2)/L79(mi=2)：空白 key 抛 IllegalArgumentException。
    @Test
    void createFromPreset_blankKey_throws() {
        assertThrows(IllegalArgumentException.class,
                () -> presetService.createFromPreset("dashscope-video", " "));
    }

    // 覆盖 L77(mb=2)/L78(mb=2)：null key 抛 IllegalArgumentException。
    @Test
    void createFromPreset_nullKey_throws() {
        assertThrows(IllegalArgumentException.class,
                () -> presetService.createFromPreset("dashscope-video", null));
    }

    // 覆盖 L91(mb=4)/L92(mi=5)/L94(mi=4)/L95(mi=5)/L96(mi=9)/L97(mb=2)/L98(mb=2)/L99(mi=11)
    // /L100(mi=5)/L101(mi=1)/L103(mi=7)/L104(mi=7)/L105(mi=2)/L106(mi=2)：正常创建主路径。
    @Test
    void createFromPreset_success_trimsKeyAndAddsModels() {
        ProviderDto created = new ProviderDto(1L, "n", "VIDEO", "d", "****", "https://x", true, List.of());
        when(providerService.createProvider(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(created);
        when(providerService.listProviders()).thenReturn(List.of(created));

        ProviderDto result = presetService.createFromPreset("dashscope-video", " sk-abc ");

        verify(providerService).createProvider(anyString(), anyString(), anyString(), eq("sk-abc"), anyString());
        verify(providerService, times(1)).addModel(any(), anyString(), anyString(), any(), anyString(), any());
        assertEquals(1L, result.id());
    }

    // 覆盖 L91(mb=4)/L92(mi=5) 的未知预设分支：抛 ResourceNotFoundException 且不创建供应商。
    @Test
    void createFromPreset_unknownPreset_throwsAndDoesNotCreate() {
        assertThrows(ResourceNotFoundException.class,
                () -> presetService.createFromPreset("no-such", "sk-x"));
        verify(providerService, never()).createProvider(anyString(), anyString(), anyString(), anyString(), anyString());
    }

    // 覆盖 L103(mi=7)/L104(mi=7)/L105(mb=2)/L106(mi=2) 的 orElse 回退分支：listProviders 不含该 dto 时返回原 dto。
    @Test
    void createFromPreset_listProvidersEmpty_returnsCreatedDto() {
        ProviderDto created = new ProviderDto(1L, "n", "VIDEO", "d", "****", "https://x", true, List.of());
        when(providerService.createProvider(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(created);
        when(providerService.listProviders()).thenReturn(List.of());

        ProviderDto result = presetService.createFromPreset("dashscope-video", "sk-abc");

        assertSame(created, result);
    }
}
