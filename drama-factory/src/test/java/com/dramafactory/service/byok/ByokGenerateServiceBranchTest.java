package com.dramafactory.service.byok;

import com.dramafactory.model.MediaProvider;
import com.dramafactory.repository.MediaProviderRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * v2.15 分支覆盖补充测试（第 A 批：ByokGenerateService）。
 *
 * <p>已跳过、测试不可达的分支（在文件头统一注明原因）：</p>
 * <ul>
 *   <li>L141 switch default —— generate() 已在 L118 校验 module ∈ {IMAGE,MUSIC,AVATAR}，
 *       default 分支不可达，无法在不改生产代码的前提下构造。</li>
 *   <li>L180 图片轮询 deadline 超时 —— deadline 写死 150_000L，且轮询中间态只允许一次
 *       sleep(4000L)（L183），无法在不 sleep 150s 的前提下触达，跳过。</li>
 *   <li>L253 数字人轮询 deadline 超时 —— deadline 写死 240_000L，同理不可达，跳过。</li>
 * </ul>
 *
 * <p>轮询中间态说明：L183 / L256 的 sleep 通过先返回中间态、再返回终态各触发一次 4 秒 sleep，
 * 这是本文件唯一允许的 sleep 场景，已在对应测试内注释说明。</p>
 */
class ByokGenerateServiceBranchTest {

    // ---------- helpers ----------

    private MediaProvider provider(Long id, String name) {
        MediaProvider p = new MediaProvider();
        p.setId(id);
        p.setName(name);
        p.setApiKey("k");
        p.setApiAddress("https://api.example");
        return p;
    }

    private HttpResponse<InputStream> okResponse(byte[] bytes) {
        @SuppressWarnings("unchecked")
        HttpResponse<InputStream> resp = mock(HttpResponse.class);
        when(resp.statusCode()).thenReturn(200);
        when(resp.body()).thenReturn(new ByteArrayInputStream(bytes));
        return resp;
    }

    private HttpResponse<InputStream> errResponse(int code) {
        @SuppressWarnings("unchecked")
        HttpResponse<InputStream> resp = mock(HttpResponse.class);
        when(resp.statusCode()).thenReturn(code);
        when(resp.body()).thenReturn(new ByteArrayInputStream(new byte[0]));
        return resp;
    }

    private ByokGenerateService newService(MediaProviderRepository repo,
                                           Map<String, ImageProvider> imageProviders,
                                           Map<String, MusicProvider> musicProviders,
                                           Map<String, AvatarProvider> avatarProviders,
                                           Path dir,
                                           ByokGenerateService.DownloadSender sender) {
        return new ByokGenerateService(repo, imageProviders, musicProviders, avatarProviders, dir.toString(), sender);
    }

    private static Method privateStatic(String name, Class<?>... types) throws Exception {
        Method m = ByokGenerateService.class.getDeclaredMethod(name, types);
        m.setAccessible(true);
        return m;
    }

    // =====================================================================
    // toNameMap (L102): key == null 分支
    // =====================================================================
    /**
     * 覆盖 L102 (m1c1)：toNameMap forEach 内 if (key != null) 的 key==null 分支。
     * 通过反射调用私有静态方法 toNameMap，传含 null key 的 HashMap。
     */
    @Test
    void toNameMapShouldSkipNullKeyBranch() throws Exception {
        Map<String, String> src = new HashMap<>();
        src.put(null, "v-null");
        src.put("DASH", "v-dash");
        Method m = privateStatic("toNameMap", Map.class);
        @SuppressWarnings("unchecked")
        Map<String, String> result = (Map<String, String>) m.invoke(null, src);
        // Map.copyOf 返回不可变映射，get(null)/containsKey(null) 都会抛 NPE；只断言 null key 被跳过后的内容
        assertEquals("v-dash", result.get("dash"));
        assertEquals(1, result.size());
    }



    // =====================================================================
    // generate() 前置校验未覆盖半支
    // =====================================================================

    /**
     * 覆盖 L126 (m1c3)：modelId == null 半支（既有测试用 ""）。
     */
    @Test
    void generateShouldRejectNullModelIdBranch() {
        ByokGenerateService svc = newService(mock(MediaProviderRepository.class),
                Map.of(), Map.of(), Map.of(), Path.of("byok-test"), r -> okResponse(new byte[0]));
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.generate(new ByokGenerateService.GenerateRequest("IMAGE", 1L, null, "p", null)));
        assertEquals("请选择模型", ex.getMessage());
    }

    /**
     * 覆盖 L126 (m1c3)：modelId.isBlank() 半支（空白串）。
     */
    @Test
    void generateShouldRejectBlankModelIdSpaceBranch() {
        ByokGenerateService svc = newService(mock(MediaProviderRepository.class),
                Map.of(), Map.of(), Map.of(), Path.of("byok-test"), r -> okResponse(new byte[0]));
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.generate(new ByokGenerateService.GenerateRequest("IMAGE", 1L, " ", "p", null)));
        assertEquals("请选择模型", ex.getMessage());
    }

    /**
     * 覆盖 L130 (m1c3)：prompt == null 半支（既有测试用 ""）。
     */
    @Test
    void generateShouldRejectNullPromptBranch() {
        ByokGenerateService svc = newService(mock(MediaProviderRepository.class),
                Map.of(), Map.of(), Map.of(), Path.of("byok-test"), r -> okResponse(new byte[0]));
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.generate(new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m", null, null)));
        assertEquals("请填写提示词", ex.getMessage());
    }

    /**
     * 覆盖 L130 (m1c3)：prompt.isBlank() 半支（空白串）。
     */
    @Test
    void generateShouldRejectBlankPromptSpaceBranch() {
        ByokGenerateService svc = newService(mock(MediaProviderRepository.class),
                Map.of(), Map.of(), Map.of(), Path.of("byok-test"), r -> okResponse(new byte[0]));
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.generate(new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m", " ", null)));
        assertEquals("请填写提示词", ex.getMessage());
    }

    /**
     * 覆盖 L137 (m1c1)：req.options()==null 三元 → 走 Map.of() 分支。
     * 走完整图片流程成功，验证 options 为 null 时不 NPE。
     */
    @Test
    void generateShouldTreatNullOptionsAsEmptyMapBranch(@TempDir Path dir) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "dashscope image");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ImageProvider imageProvider = mock(ImageProvider.class);
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "http://x/a.png", null, 100));

        ByokGenerateService svc = newService(repo,
                Map.of("dashscopeimageprovider", imageProvider), Map.of(), Map.of(), dir,
                r -> okResponse("PNG".getBytes()));

        ByokGenerateService.GenerateResponse resp = svc.generate(
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m", "p", null));
        assertEquals("SUCCEEDED", resp.status());
        assertNotNull(resp.url());
    }

    /**
     * 覆盖 L138 (m1c1)：provider.getName()==null 三元 → 走 "" 分支。
     * provider 不设 name，lowerName=""，matchImage 返回 null → imageProvider==null → IllegalStateException。
     * 断言不 NPE（即没有把 null 传给 toLowerCase）。
     */
    @Test
    void generateShouldHandleNullProviderNameBranch(@TempDir Path dir) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = new MediaProvider();
        p.setId(1L);
        p.setApiKey("k");
        p.setApiAddress("https://api.example");
        // setName 不调用 → getName() == null
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ByokGenerateService svc = newService(repo,
                Map.of("dashscopeimageprovider", mock(ImageProvider.class)), Map.of(), Map.of(), dir,
                r -> okResponse(new byte[0]));

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> svc.generate(new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m", "p", null)));
        assertTrue(ex.getMessage().contains("该供应商暂未接入生成实现"));
    }

    // =====================================================================
    // generateImage: size 空白串走默认
    // =====================================================================

    /**
     * 覆盖 L158 (m3c1)：size==null||isBlank 中 isBlank 半支（既有测试用 null）。
     * 传 size=" "，用 ArgumentCaptor 抓 submit 的第 5 个参数断言为 "1024*1024"。
     */
    @Test
    void generateImageShouldDefaultSizeWhenBlankBranch(@TempDir Path dir) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "dashscope image");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ImageProvider imageProvider = mock(ImageProvider.class);
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "http://x/a.png", null, 100));

        ByokGenerateService svc = newService(repo,
                Map.of("dashscopeimageprovider", imageProvider), Map.of(), Map.of(), dir,
                r -> okResponse("PNG".getBytes()));

        Map<String, String> opts = new HashMap<>();
        opts.put("size", " ");
        ByokGenerateService.GenerateResponse resp = svc.generate(
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m", "p", opts));
        assertEquals("SUCCEEDED", resp.status());

        ArgumentCaptor<String> sizeCaptor = ArgumentCaptor.forClass(String.class);
        verify(imageProvider).submit(anyString(), anyString(), anyString(), anyString(), sizeCaptor.capture());
        assertEquals("1024*1024", sizeCaptor.getValue());
    }

    /**
     * 覆盖 L186 (m1c3)：poll SUCCEEDED 但 imageUrl 为空白串 → RuntimeException。
     */
    @Test
    void generateImageShouldFailWhenPollSucceededWithBlankUrlBranch(@TempDir Path dir) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "dashscope image");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ImageProvider imageProvider = mock(ImageProvider.class);
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, " ", null, 100));

        ByokGenerateService svc = newService(repo,
                Map.of("dashscopeimageprovider", imageProvider), Map.of(), Map.of(), dir,
                r -> okResponse(new byte[0]));

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> svc.generate(new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m", "p", null)));
        assertEquals("图片生成失败：未返回产物地址", ex.getMessage());
    }

    // =====================================================================
    // generateMusic: match 命中但 map 缺失 → null provider
    // =====================================================================

    /**
     * 覆盖 L198 (m1c1) 与 L199 (m1c1)：matchMusic 命中 "minimaxmusicprovider"，
     * 但 musicProvidersByName 为空 map → get 返回 null → IllegalStateException。
     */
    @Test
    void generateMusicShouldFailWhenMatchedBeanMissingFromMapBranch(@TempDir Path dir) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "minimax music");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ByokGenerateService svc = newService(repo,
                Map.of("dashscopeimageprovider", mock(ImageProvider.class)),
                Map.of(),
                Map.of("didavatarprovider", mock(AvatarProvider.class)),
                dir, r -> okResponse(new byte[0]));

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> svc.generate(new ByokGenerateService.GenerateRequest("MUSIC", 1L, "m", "p", null)));
        assertTrue(ex.getMessage().contains("该供应商暂未接入生成实现"));
    }

    /**
     * 覆盖 L211 (m1c3)：music generate 返回 audioUrl=" "（空白串）→ RuntimeException。
     */
    @Test
    void generateMusicShouldFailWhenUrlBlankBranch(@TempDir Path dir) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "minimax music");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        MusicProvider musicProvider = mock(MusicProvider.class);
        when(musicProvider.generate(anyString(), anyString(), anyString(), anyString(), any(), anyBoolean()))
                .thenReturn(new MusicProvider.GenerateResult(" ", 1000));

        ByokGenerateService svc = newService(repo,
                Map.of(), Map.of("minimaxmusicprovider", musicProvider), Map.of(), dir,
                r -> okResponse(new byte[0]));

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> svc.generate(new ByokGenerateService.GenerateRequest("MUSIC", 1L, "m", "p", null)));
        assertEquals("音乐生成失败：未返回产物地址", ex.getMessage());
    }

    // =====================================================================
    // generateAvatar: match 命中但 map 缺失 → null provider
    // =====================================================================

    /**
     * 覆盖 L223 (m1c1) 与 L224 (m1c1)：matchAvatar 命中 "didavatarprovider"，
     * 但 avatarProvidersByName 为空 map → get 返回 null → IllegalStateException。
     */
    @Test
    void generateAvatarShouldFailWhenMatchedBeanMissingFromMapBranch(@TempDir Path dir) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "d-id avatar");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ByokGenerateService svc = newService(repo,
                Map.of("dashscopeimageprovider", mock(ImageProvider.class)),
                Map.of("minimaxmusicprovider", mock(MusicProvider.class)),
                Map.of(),
                dir, r -> okResponse(new byte[0]));

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> svc.generate(new ByokGenerateService.GenerateRequest("AVATAR", 1L, "m", "p", null)));
        assertTrue(ex.getMessage().contains("该供应商暂未接入生成实现"));
    }

    /**
     * 覆盖 L229 (m1c3)：avatar options imageUrl=" "（空白串）→ IllegalArgumentException。
     */
    @Test
    void generateAvatarShouldRejectBlankImageUrlBranch(@TempDir Path dir) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "d-id avatar");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ByokGenerateService svc = newService(repo,
                Map.of(), Map.of(), Map.of("didavatarprovider", mock(AvatarProvider.class)), dir,
                r -> okResponse(new byte[0]));

        Map<String, String> opts = new HashMap<>();
        opts.put("imageUrl", " ");
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.generate(new ByokGenerateService.GenerateRequest("AVATAR", 1L, "m", "p", opts)));
        assertEquals("请提供人物图 URL", ex.getMessage());
    }

    /**
     * 覆盖 L250 (m1c1)：avatar poll FAILED 且 errorMessage=null 变体。
     * 断言异常信息含 "数字人生成失败"。
     */
    @Test
    void generateAvatarShouldFailWhenPollFailedWithNullMessageBranch(@TempDir Path dir) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "d-id avatar");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        AvatarProvider avatarProvider = mock(AvatarProvider.class);
        when(avatarProvider.submit(anyString(), anyString(), any(), anyString()))
                .thenReturn(new AvatarProvider.SubmitResult("talk1"));
        when(avatarProvider.poll(anyString(), anyString()))
                .thenReturn(new AvatarProvider.PollResult(AvatarProvider.RemoteStatus.FAILED, null, null, 100));

        ByokGenerateService svc = newService(repo,
                Map.of(), Map.of(), Map.of("didavatarprovider", avatarProvider), dir,
                r -> okResponse(new byte[0]));

        Map<String, String> opts = new HashMap<>();
        opts.put("imageUrl", "http://x/img.png");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> svc.generate(new ByokGenerateService.GenerateRequest("AVATAR", 1L, "m", "p", opts)));
        assertTrue(ex.getMessage().contains("数字人生成失败"));
    }

    /**
     * 覆盖 L259 (m1c3)：avatar poll SUCCEEDED 但 videoUrl=" "（空白串）→ RuntimeException。
     */
    @Test
    void generateAvatarShouldFailWhenPollSucceededWithBlankUrlBranch(@TempDir Path dir) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "d-id avatar");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        AvatarProvider avatarProvider = mock(AvatarProvider.class);
        when(avatarProvider.submit(anyString(), anyString(), any(), anyString()))
                .thenReturn(new AvatarProvider.SubmitResult("talk1"));
        when(avatarProvider.poll(anyString(), anyString()))
                .thenReturn(new AvatarProvider.PollResult(AvatarProvider.RemoteStatus.SUCCEEDED, " ", null, 100));

        ByokGenerateService svc = newService(repo,
                Map.of(), Map.of(), Map.of("didavatarprovider", avatarProvider), dir,
                r -> okResponse(new byte[0]));

        Map<String, String> opts = new HashMap<>();
        opts.put("imageUrl", "http://x/img.png");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> svc.generate(new ByokGenerateService.GenerateRequest("AVATAR", 1L, "m", "p", opts)));
        assertEquals("数字人生成失败：未返回产物地址", ex.getMessage());
    }

    // =====================================================================
    // matchImage / matchAvatar 未覆盖分支
    // =====================================================================

    /**
     * 覆盖 L272/273 (m1c3/m1c1)：matchImage 的 || 链。
     */
    @Test
    void matchImageShouldHitAlternateBranches() {
        assertEquals("dashscopeimageprovider", ByokGenerateService.matchImage("万相"));
        assertEquals("dashscopeimageprovider", ByokGenerateService.matchImage("image-gen"));
        assertNull(ByokGenerateService.matchImage("nothing"));
    }

    /**
     * 覆盖 L296 (m1c5)：matchAvatar 的 || 链。
     */
    @Test
    void matchAvatarShouldHitChineseBranch() {
        assertEquals("didavatarprovider", ByokGenerateService.matchAvatar("数字人供应商"));
        assertNull(ByokGenerateService.matchAvatar("nothing"));
    }

    // =====================================================================
    // download: 状态码分支
    // =====================================================================

    /**
     * 覆盖 L331 (m1c3)：statusCode<200||>=300 的 <200 半支。
     * errSender(199)，断言抛 RuntimeException 且信息含 "HTTP 199"。
     */
    @Test
    void downloadShouldFailOnStatus199Branch(@TempDir Path dir) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "dashscope image");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ImageProvider imageProvider = mock(ImageProvider.class);
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "http://x/a.png", null, 100));

        ByokGenerateService svc = newService(repo,
                Map.of("dashscopeimageprovider", imageProvider), Map.of(), Map.of(), dir,
                r -> errResponse(199));

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> svc.generate(new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m", "p", null)));
        assertTrue(ex.getMessage().contains("HTTP 199"));
    }
    /**
     * 覆盖 L334 (m1c1)：非 2xx 时 drain body 抛 IOException 仍吞掉。
     * body() 桩抛 IOException，statusCode 500，断言仍抛 "产物下载失败，HTTP 500"。
     */
    @Test
    void downloadShouldSwallowBodyIOExceptionOnErrorStatusBranch(@TempDir Path dir) throws Exception {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "dashscope image");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ImageProvider imageProvider = mock(ImageProvider.class);
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "http://x/a.png", null, 100));

        @SuppressWarnings("unchecked")
        HttpResponse<InputStream> bad = mock(HttpResponse.class);
        when(bad.statusCode()).thenReturn(500);
        // body() 未声明受检异常，Mockito 禁止 thenThrow 受检异常，改用 doAnswer
        org.mockito.Mockito.doAnswer(inv -> { throw new IOException("boom"); }).when(bad).body();

        ByokGenerateService svc = newService(repo,
                Map.of("dashscopeimageprovider", imageProvider), Map.of(), Map.of(), dir,
                r -> bad);

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> svc.generate(new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m", "p", null)));
        assertEquals("产物下载失败，HTTP 500", ex.getMessage());
    }



    // =====================================================================
    // resolveExtension: 反射覆盖各分支
    // =====================================================================

    /**
     * 覆盖 L362 (m1c1)：url==null 分支 → 用 extHint。
     */
    @Test
    void resolveExtensionShouldUseHintWhenUrlNullBranch() throws Exception {
        Method m = privateStatic("resolveExtension", String.class, String.class);
        assertEquals("png", m.invoke(null, null, "png"));
    }

    /**
     * 覆盖 L373 (m1c3)：candidate 合法分支的另一半——bmp 非法 → 回退 hint。
     */
    @Test
    void resolveExtensionShouldFallbackWhenCandidateIllegalBranch() throws Exception {
        Method m = privateStatic("resolveExtension", String.class, String.class);
        assertEquals("png", m.invoke(null, "http://x/a.bmp", "png"));
    }

    /**
     * 覆盖 L375 (m1c3)：extHint==null → 抛 IllegalStateException。
     */
    @Test
    void resolveExtensionShouldThrowWhenHintNullBranch() throws Exception {
        Method m = privateStatic("resolveExtension", String.class, String.class);
        Exception ex = assertThrows(Exception.class, () -> m.invoke(null, "http://x/a", null));
        assertTrue(ex.getCause() instanceof IllegalStateException);
    }

    /**
     * 覆盖 L382 (m1c1)：hint 非法 → 抛 IllegalStateException。
     */
    @Test
    void resolveExtensionShouldThrowWhenHintIllegalBranch() throws Exception {
        Method m = privateStatic("resolveExtension", String.class, String.class);
        Exception ex = assertThrows(Exception.class, () -> m.invoke(null, "http://x/a", "exe"));
        assertTrue(ex.getCause() instanceof IllegalStateException);
    }

    /**
     * 覆盖 L392 (m1c5)：isAllowedExt 的 || 链。
     * jpeg 走 jpeg 分支；大小写+query 截断走 mp4 分支。
     */
    @Test
    void resolveExtensionShouldHitAllowedExtBranches() throws Exception {
        Method m = privateStatic("resolveExtension", String.class, String.class);
        assertEquals("jpeg", m.invoke(null, "http://x/a.jpeg", "png"));
        assertEquals("mp4", m.invoke(null, "http://x/a.MP4?x=1", "png"));
    }

    // =====================================================================
    // extractRunId: 反射覆盖各分支
    // =====================================================================
    /**
     * 覆盖 L406 (m1c1)：extractRunId options==null → null（实例方法反射调用）。
     */
    @Test
    void extractRunIdShouldReturnNullWhenOptionsNullBranch() throws Exception {
        ByokGenerateService svc = newService(
                mock(MediaProviderRepository.class),
                Map.of(),
                Map.of(),
                Map.of(),
                Path.of("byok-test"),
                r -> okResponse(new byte[0]));
        Method m = ByokGenerateService.class.getDeclaredMethod("extractRunId", Map.class);
        m.setAccessible(true);

        assertNull(m.invoke(svc, new Object[]{null}));
    }
    /**
     * 覆盖 L410 (m3c1)：extractRunId 空白串/非数字/合法数字分支（实例方法反射调用）。
     */
    @Test
    void extractRunIdShouldCoverBlankAndParseBranches() throws Exception {
        ByokGenerateService svc = newService(
                mock(MediaProviderRepository.class),
                Map.of(),
                Map.of(),
                Map.of(),
                Path.of("byok-test"),
                r -> okResponse(new byte[0]));
        Method m = ByokGenerateService.class.getDeclaredMethod("extractRunId", Map.class);
        m.setAccessible(true);

        assertNull(m.invoke(svc, Map.of("runId", " ")));
        assertNull(m.invoke(svc, Map.of("runId", "abc")));
        assertEquals(123L, m.invoke(svc, Map.of("runId", "123")));
    }


    // =====================================================================
    // registerAsset: L422 / L427-429
    // =====================================================================

    /**
     * 覆盖 L422 (m3c1)：assetService 未注入（null）时 generate 成功不 NPE。
     */
    @Test
    void registerAssetShouldBeNoopWhenAssetServiceNullBranch(@TempDir Path dir) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "dashscope image");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ImageProvider imageProvider = mock(ImageProvider.class);
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "http://x/a.png", null, 100));

        ByokGenerateService svc = newService(repo,
                Map.of("dashscopeimageprovider", imageProvider), Map.of(), Map.of(), dir,
                r -> okResponse("PNG".getBytes()));

        ByokGenerateService.GenerateResponse resp = svc.generate(
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m", "p", null));
        assertEquals("SUCCEEDED", resp.status());
        assertNotNull(resp.url());
    }

    /**
     * 覆盖 L427-429 (m2c0×3)：assetService 注入后 registerGenerated 被调 1 次。
     */
    @Test
    void registerAssetShouldInvokeAssetServiceWhenPresentBranch(@TempDir Path dir) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "dashscope image");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ImageProvider imageProvider = mock(ImageProvider.class);
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "http://x/a.png", null, 100));

        com.dramafactory.service.AssetService assetService = mock(com.dramafactory.service.AssetService.class);

        ByokGenerateService svc = newService(repo,
                Map.of("dashscopeimageprovider", imageProvider), Map.of(), Map.of(), dir,
                r -> okResponse("PNG".getBytes()));
        svc.setAssetService(assetService);

        ByokGenerateService.GenerateResponse resp = svc.generate(
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m", "p", null));
        assertEquals("SUCCEEDED", resp.status());
        verify(assetService, times(1)).registerGenerated(
                any(), any(), any(), anyLong(), any(), any(), any());
    }

    /**
     * 覆盖 L431 (m1c1)：assetService.registerGenerated 抛 RuntimeException 时主流程不受影响。
     */
    @Test
    void registerAssetShouldSwallowExceptionFromAssetServiceBranch(@TempDir Path dir) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "dashscope image");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ImageProvider imageProvider = mock(ImageProvider.class);
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "http://x/a.png", null, 100));

        com.dramafactory.service.AssetService assetService = mock(com.dramafactory.service.AssetService.class);
        doThrow(new RuntimeException("register boom")).when(assetService)
                .registerGenerated(any(), any(), any(), anyLong(), any(), any(), any());

        ByokGenerateService svc = newService(repo,
                Map.of("dashscopeimageprovider", imageProvider), Map.of(), Map.of(), dir,
                r -> okResponse("PNG".getBytes()));
        svc.setAssetService(assetService);

        ByokGenerateService.GenerateResponse resp = svc.generate(
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m", "p", null));
        assertEquals("SUCCEEDED", resp.status());
    }
}
