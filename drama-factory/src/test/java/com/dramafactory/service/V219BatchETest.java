package com.dramafactory.service;

import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.PromptRecipe;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.PromptRecipeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.video.SurrogateAuthClient;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class V219BatchETest {

    @TempDir
    Path tempDir;

    /**
     * 覆盖 EpisodeStatusFlowService#refreshAfterTaskDone 中
     * latestTask.isEmpty() == true 的短路臂（第 65 行）。
     * 当任务仓库返回 Optional.empty() 时应提前返回，不推进状态、不保存。
     */
    @Test
    void refreshAfterTaskDone_whenLatestTaskEmpty_returnsEarlyWithoutSaving() {
        EpisodeRepository episodeRepository = mock(EpisodeRepository.class);
        ShotRepository shotRepository = mock(ShotRepository.class);
        VideoTaskRepository videoTaskRepository = mock(VideoTaskRepository.class);

        EpisodeStatusFlowService service =
                new EpisodeStatusFlowService(episodeRepository, shotRepository, videoTaskRepository, mock(ReviewService.class));

        Episode episode = new Episode();
        episode.setId(9L);
        episode.setStatus(EpisodeStatus.DRAFT);
        when(episodeRepository.findById(9L)).thenReturn(Optional.of(episode));

        Shot shot = new Shot();
        shot.setId(3L);
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(9L)).thenReturn(List.of(shot));

        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(3L)).thenReturn(Optional.empty());

        service.refreshAfterTaskDone(9L);

        verify(episodeRepository, never()).save(any());
    }

    /**
     * 覆盖 PresetService#createFromPreset 中 preset.models() == null 的臂（第 97 行）。
     * 通过反射替换私有 final 字段 presets，注入一个 models 为 null 的 Preset。
     * 说明：final 实例字段反射 setAccessible(true) 后可写（无 static 常量折叠），
     * 因此可在测试中替换字段内容以触发该分支。
     */
    @Test
    void createFromPreset_whenPresetModelsNull_skipsAddModel() throws Exception {
        ProviderService providerService = mock(ProviderService.class);
        PresetService service = new PresetService(providerService);

        Field presetsField = PresetService.class.getDeclaredField("presets");
        presetsField.setAccessible(true);
        @SuppressWarnings("unchecked")
        List<PresetService.Preset> original = (List<PresetService.Preset>) presetsField.get(service);
        presetsField.set(service, List.of(
                new PresetService.Preset("p1", "m", "n", "d", "http://a", null)));

        ProviderService.ProviderDto dto = mock(ProviderService.ProviderDto.class);
        when(dto.id()).thenReturn(11L);
        when(providerService.createProvider(eq("n"), eq("m"), eq("d"), eq("k"), eq("http://a")))
                .thenReturn(dto);
        when(providerService.listProviders()).thenReturn(List.of(dto));

        ProviderService.ProviderDto result = service.createFromPreset("p1", "k");

        assertEquals(11L, result.id());
        verify(providerService, never()).addModel(
                anyLong(), anyString(), anyString(), anyString(), anyString(), anyInt());

        presetsField.set(service, original);
    }

    /**
     * 覆盖 CredentialResolver#minimaxAuth 中 cardKey.isBlank() == true 的臂（第 85 行）。
     * 传入空白 cardKey 时应回退到 readKey("minimax.api-key")。
     */
    @Test
    void minimaxAuth_whenCardKeyBlank_fallsBackToSettingsKey() {
        SettingsService settingsService = mock(SettingsService.class);
        SurrogateAuthClient surrogateAuthClient = mock(SurrogateAuthClient.class);

        LinkedHashMap<String, String> store = new LinkedHashMap<>();
        store.put("minimax.api-key", "mini-k");
        when(settingsService.loadAll()).thenReturn(store);

        CredentialResolver resolver = new CredentialResolver(settingsService, surrogateAuthClient);

        Map.Entry<String, String> headers = resolver.minimaxAuth(" ");
        assertEquals("Authorization", headers.getKey());
        assertEquals("Bearer " + "mini-k", headers.getValue());
    }

    /**
     * 覆盖 CredentialResolver#didAuth 中 cardKey.isBlank() == true 的臂（第 96 行）。
     * 传入空白 cardKey 时应回退到 readKey("did.api-key")，并生成 Basic 认证头。
     */
    @Test
    void didAuth_whenCardKeyBlank_fallsBackToSettingsKey() {
        SettingsService settingsService = mock(SettingsService.class);
        SurrogateAuthClient surrogateAuthClient = mock(SurrogateAuthClient.class);

        LinkedHashMap<String, String> store = new LinkedHashMap<>();
        store.put("did.api-key", "did-k");
        when(settingsService.loadAll()).thenReturn(store);

        CredentialResolver resolver = new CredentialResolver(settingsService, surrogateAuthClient);

        Map.Entry<String, String> headers = resolver.didAuth(" ");

        String expected = "Basic " + Base64.getEncoder()
                .encodeToString("did-k:".getBytes(StandardCharsets.UTF_8));
        assertEquals("Authorization", headers.getKey());
        assertEquals(expected, headers.getValue());
    }

    /**
     * 覆盖 PromptRecipeService#list 中 comparator 内
     * b.getUsageCount() == null ? 0L : b.getUsageCount() 的 null 臂（第 133 行）。
     * 当某个 recipe 的 usageCount 为 null 时应视为 0，排序不抛 NPE。
     */
    @Test
    void list_whenUsageCountNull_treatsAsZeroAndSortsWithoutNpe() {
        PromptRecipeRepository repository = mock(PromptRecipeRepository.class);
        PromptRecipeService service = new PromptRecipeService(repository);

        PromptRecipe r1 = new PromptRecipe();
        r1.setId(1L);
        r1.setUsageCount(null);

        PromptRecipe r2 = new PromptRecipe();
        r2.setId(2L);
        r2.setUsageCount(5L);

        when(repository.findAll()).thenReturn(List.of(r1, r2));

        List<PromptRecipe> result = service.list(null, null);

        assertEquals(2, result.size());
    }

    /**
     * 覆盖 PromptRecipeService#render 经 extractVariables 时
     * content == null 的臂（第 213 行）。
     * 说明：覆盖 content == null 臂；当前生产行为为 NPE，本测试锁定该行为。
     */
    @Test
    void render_whenContentNull_extractVariablesNullArmThenNpe() {
        PromptRecipeRepository repository = mock(PromptRecipeRepository.class);
        PromptRecipeService service = new PromptRecipeService(repository);

        PromptRecipe recipe = new PromptRecipe();
        recipe.setId(1L);
        // 不设 content，保持 null
        when(repository.findById(1L)).thenReturn(Optional.of(recipe));

        assertThrows(NullPointerException.class, () -> service.render(1L, Map.of()));
    }
}