// MvService loadTimeline/resolveLocalAudio 分支覆盖（v2.14）
package com.dramafactory.service;

import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetSource;
import com.dramafactory.model.AssetType;
import com.dramafactory.model.MvSong;
import com.dramafactory.repository.AssetRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MvServiceResolveBranchTest {

    @Autowired
    private MvService mvService;

    @Autowired
    private AssetRepository assetRepository;

    @Autowired
    private MvTimelineService mvTimelineService;

    @MockBean
    private MvLyricsService mvLyricsService;

    @MockBean
    private com.dramafactory.service.byok.ByokGenerateService byokGenerateService;

    private Object invokePrivate(String name, Class<?>[] types, Object... args) throws Exception {
        Method m = MvService.class.getDeclaredMethod(name, types);
        m.setAccessible(true);
        // MvService 是 @Transactional CGLIB 代理：私有方法反射必须打在 target 上，
        // 直接打在代理实例上会读到代理自身未初始化的 null 字段。
        Object target = org.springframework.test.util.AopTestUtils.getTargetObject(mvService);
        try {
            return m.invoke(target, args);
        } catch (InvocationTargetException e) {
            Throwable c = e.getCause();
            if (c instanceof RuntimeException re) {
                throw re;
            }
            throw new RuntimeException(c);
        }
    }

    // ---------- loadTimeline ----------

    @Test
    void loadTimeline_withJson_parses() throws Exception {
        MvSong song = new MvSong();
        String json = mvTimelineService.toJson(
                mvTimelineService.buildInstrumentalTimeline(60000L, 10000L));
        song.setTimelineJson(json);

        Object result = invokePrivate("loadTimeline", new Class<?>[]{MvSong.class}, song);

        assertNotNull(result);
        assertTrue(result instanceof MvTimelineService.Timeline);
        MvTimelineService.Timeline timeline = (MvTimelineService.Timeline) result;
        assertNotNull(timeline.sections());
        assertFalse(timeline.sections().isEmpty());
    }

    @Test
    void loadTimeline_withoutJson_realigns() throws Exception {
        MvSong song = new MvSong();
        song.setLyricsJson("{\"title\":\"t\",\"sections\":[{\"name\":\"段落 1\",\"lyrics\":\"第一行\\n第二行\",\"estSeconds\":8}]}");
        song.setDurationMs(60000);

        Object result = invokePrivate("loadTimeline", new Class<?>[]{MvSong.class}, song);

        assertNotNull(result);
        assertTrue(result instanceof MvTimelineService.Timeline);
        MvTimelineService.Timeline timeline = (MvTimelineService.Timeline) result;
        assertNotNull(timeline.sections());
    }

    // ---------- resolveLocalAudio ----------

    @Test
    void resolveLocalAudio_byokPath() throws Exception {
        Object result = invokePrivate("resolveLocalAudio", new Class<?>[]{String.class},
                "/api/byok/file/music/t.mp3");

        assertNotNull(result);
        assertTrue(result instanceof Path);
        String s = result.toString();
        assertTrue(s.contains("byok"), "路径应包含 byok，实际: " + s);
        assertTrue(s.contains("t.mp3"), "路径应包含 t.mp3，实际: " + s);
    }

    @Test
    void resolveLocalAudio_assetPath() throws Exception {
        Asset a = new Asset();
        a.setType(AssetType.AUDIO);
        a.setSource(AssetSource.UPLOADED);
        a.setFileName("b.mp3");
        a.setFilePath("a/b.mp3");
        Asset saved = assetRepository.save(a);

        Object result = invokePrivate("resolveLocalAudio", new Class<?>[]{String.class},
                "/api/assets/" + saved.getId() + "/file");

        assertNotNull(result);
        assertTrue(result instanceof Path);
        String s = result.toString();
        assertTrue(s.contains("b.mp3"), "路径应包含 b.mp3，实际: " + s);
    }

    @Test
    void resolveLocalAudio_assetNotFound() throws Exception {
        try {
            invokePrivate("resolveLocalAudio", new Class<?>[]{String.class},
                    "/api/assets/999998877/file");
            fail("应当抛异常");
        } catch (IllegalStateException e) {
            assertNotNull(e.getMessage());
            assertTrue(e.getMessage().contains("音频资产不存在"),
                    "消息应包含关键字，实际: " + e.getMessage());
        }
    }

    @Test
    void resolveLocalAudio_pathTraversal() throws Exception {
        Asset a = new Asset();
        a.setType(AssetType.AUDIO);
        a.setSource(AssetSource.UPLOADED);
        a.setFileName("evil.mp3");
        a.setFilePath("../evil.mp3");
        Asset saved = assetRepository.save(a);

        try {
            invokePrivate("resolveLocalAudio", new Class<?>[]{String.class},
                    "/api/assets/" + saved.getId() + "/file");
            fail("应当抛异常");
        } catch (IllegalStateException e) {
            assertNotNull(e.getMessage());
            assertTrue(e.getMessage().contains("音频资产路径非法"),
                    "消息应包含关键字，实际: " + e.getMessage());
        }
    }

    @Test
    void resolveLocalAudio_badId() throws Exception {
        try {
            invokePrivate("resolveLocalAudio", new Class<?>[]{String.class},
                    "/api/assets/abc/file");
            fail("应当抛异常");
        } catch (IllegalStateException e) {
            assertNotNull(e.getMessage());
            assertTrue(e.getMessage().contains("音频地址格式错误"),
                    "消息应包含关键字，实际: " + e.getMessage());
        }
    }

    @Test
    void resolveLocalAudio_unsupported() throws Exception {
        try {
            invokePrivate("resolveLocalAudio", new Class<?>[]{String.class},
                    "https://cdn/x/y.mp3");
            fail("应当抛异常");
        } catch (IllegalStateException e) {
            assertNotNull(e.getMessage());
            assertTrue(e.getMessage().contains("不支持的音频地址"),
                    "消息应包含关键字，实际: " + e.getMessage());
        }
    }
}
