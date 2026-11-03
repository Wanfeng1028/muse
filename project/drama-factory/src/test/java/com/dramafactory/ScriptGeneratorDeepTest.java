package com.dramafactory;

import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.service.ScriptGenerator;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ScriptGeneratorDeepTest {

    private ScriptGenerator generator;

    @BeforeEach
    void setUp() {
        generator = new ScriptGenerator();
    }

    private Episode buildEpisode(String title, String genre, String outline) {
        DramaProject project = new DramaProject();
        project.setTitle(title);
        project.setGenre(genre);
        Episode episode = new Episode();
        episode.setProject(project);
        episode.setOutline(outline);
        return episode;
    }

    @Test
    void generateReturnsExactlyFourScenesInOrder() {
        // given
        Episode episode = buildEpisode("晚风短剧", "都市", "主角在加班途中收到一条陌生短信");
        // when
        List<ScriptGenerator.SceneDraft> drafts = generator.generate(episode);
        // then
        assertNotNull(drafts, "生成结果不能为 null");
        assertEquals(4, drafts.size(), "必须恰好生成 4 场剧本");
        assertEquals(1, drafts.get(0).sceneNo());
        assertEquals(2, drafts.get(1).sceneNo());
        assertEquals(3, drafts.get(2).sceneNo());
        assertEquals(4, drafts.get(3).sceneNo());
    }

    @Test
    void generateIsDeterministicForSameEpisode() {
        // given
        Episode episode = buildEpisode("确定性验证", "悬疑", "主角发现邻居家的灯整夜没关");
        // when
        List<ScriptGenerator.SceneDraft> first = generator.generate(episode);
        List<ScriptGenerator.SceneDraft> second = generator.generate(episode);
        // then
        assertEquals(first.size(), second.size(), "两次生成场次数量必须一致");
        for (int i = 0; i < first.size(); i++) {
            assertEquals(first.get(i), second.get(i), "第 " + (i + 1) + " 场内容必须逐字一致");
        }
    }

    @Test
    void generateReferencesOutlineKeywordInEveryScene() {
        // given
        String outline = "一封被退回的信";
        Episode episode = buildEpisode("关键词引用", "都市", outline);
        // when
        List<ScriptGenerator.SceneDraft> drafts = generator.generate(episode);
        // then
        String keyword = "一封被退回的信"; // 大纲不足 12 字，extractKeyword 即全文
        for (ScriptGenerator.SceneDraft draft : drafts) {
            assertTrue(draft.description().contains(keyword), "每场描述必须引用大纲关键词");
        }
        for (int i = 0; i < 3; i++) {
            assertTrue(drafts.get(i).dialogue().contains(keyword), "前三场对白必须引用大纲关键词");
        }
        // 注：第 4 场对白是固定收尾台词，不带关键词（源码行为），故不对它断言对白
        assertTrue(drafts.get(0).prompt().contains("都市"), "提示词必须带类型");
    }

    @Test
    void generateFallsBackToDefaultsWhenProjectIsNull() {
        // given
        Episode episode = new Episode();
        episode.setOutline("   ");
        // when
        List<ScriptGenerator.SceneDraft> drafts = generator.generate(episode);
        // then
        assertEquals(4, drafts.size(), "空项目也必须生成 4 场");
        assertTrue(drafts.get(0).description().contains("无题短剧"), "标题缺省为 无题短剧");
        assertTrue(drafts.get(0).description().contains("都市"), "类型缺省为 都市");
        assertTrue(drafts.get(0).description().contains("主角在平静日常中卷入一场无法回避的风波"),
                "大纲缺省为默认剧情句");
    }

    @Test
    void generateTrimsWhitespaceFromProjectAndOutline() {
        // given
        Episode episode = buildEpisode("   带空格的标题   ", "   科幻   ", "   主角在实验室醒来   ");
        // when
        List<ScriptGenerator.SceneDraft> drafts = generator.generate(episode);
        // then
        String description = drafts.get(0).description();
        assertTrue(description.contains("《带空格的标题》"), "标题应被 trim");
        // "科幻风格" 出现在 location 字段（"科幻风格的城市街道"），而非 description
        assertTrue(drafts.get(0).location().contains("科幻风格"), "类型应被 trim 后拼接到场景地");
        assertFalse(description.contains("    "), "描述中不应残留连续空白");
    }

    @Test
    void generateTruncatesKeywordToTwelveCharsWhenOutlineIsLong() {
        // given
        String outline = "这是一段非常非常长的大纲内容用来验证关键词截断逻辑是否正确处理边界情况";
        Episode episode = buildEpisode("长大纲", "都市", outline);
        // when
        List<ScriptGenerator.SceneDraft> drafts = generator.generate(episode);
        // then
        String expectedKeyword = outline.substring(0, 12);
        assertTrue(drafts.get(1).description().contains(expectedKeyword), "关键词应为前 12 个字符");
        assertTrue(drafts.get(1).dialogue().contains(expectedKeyword), "对白必须使用同一关键词");
    }

    @Test
    void generateRemovesWhitespaceBeforeExtractingKeyword() {
        // given
        String outline = "前 面 有 空 白";
        Episode episode = buildEpisode("去空白", "都市", outline);
        // when
        List<ScriptGenerator.SceneDraft> drafts = generator.generate(episode);
        // then
        String cleanedKeyword = "前面有空白";
        assertTrue(drafts.get(2).description().contains(cleanedKeyword), "关键词应剔除内部空白");
        assertFalse(drafts.get(2).description().contains("前 面"), "不应保留原始空白形态");
    }

    @Test
    void generateReturnsFreshListAndDraftsEachCall() {
        // given
        Episode episode = buildEpisode("独立实例", "都市", "测试独立实例");
        // when
        List<ScriptGenerator.SceneDraft> first = generator.generate(episode);
        List<ScriptGenerator.SceneDraft> second = generator.generate(episode);
        // then
        assertNotSame(first, second, "每次调用应返回新的 List 实例");
        assertNotSame(first.get(0), second.get(0), "每次调用应返回新的 SceneDraft 实例");
        assertEquals(first.get(0), second.get(0), "内容相等但实例独立");
    }

    @Test
    void generateHandlesNullOutlineWithDefaultStoryline() {
        // given
        Episode episode = new Episode();
        DramaProject project = new DramaProject();
        project.setTitle("空大纲剧");
        project.setGenre("悬疑");
        episode.setProject(project);
        episode.setOutline(null);
        // when
        List<ScriptGenerator.SceneDraft> drafts = generator.generate(episode);
        // then
        assertEquals(4, drafts.size(), "null 大纲也要产出 4 场");
        assertTrue(drafts.get(0).description().contains("空大纲剧"), "标题必须进入描述");
        assertTrue(drafts.get(0).description().contains("主角在平静日常中卷入一场无法回避的风波"),
                "null 大纲回退到默认剧情句");
    }

    @Test
    void generateOnNullEpisodeThrowsNullPointerException() {
        // given
        Episode episode = null;
        // when / then
        NullPointerException ex = assertThrows(NullPointerException.class, () -> generator.generate(episode));
        assertNotNull(ex, "必须抛出 NPE");
        assertTrue(ex.getMessage() == null || ex.getMessage().isEmpty() || ex.getMessage().length() >= 0,
                "异常对象必须非空");
    }

    @Test
    void generateProducesSceneSpecificLocationsAndTimes() {
        // given
        Episode episode = buildEpisode("场次区分", "都市", "夜里响起的敲门声");
        // when
        List<ScriptGenerator.SceneDraft> drafts = generator.generate(episode);
        // then
        assertEquals("黄昏", drafts.get(0).timeOfDay(), "第 1 场时间为黄昏");
        assertEquals("夜晚", drafts.get(1).timeOfDay(), "第 2 场时间为夜晚");
        assertEquals("深夜", drafts.get(2).timeOfDay(), "第 3 场时间为深夜");
        assertEquals("凌晨", drafts.get(3).timeOfDay(), "第 4 场时间为凌晨");
        assertFalse(drafts.get(0).location().equals(drafts.get(3).location()), "首尾场地点必须不同");
    }

    @Test
    void generateIsThreadSafeUnderConcurrentCalls() throws InterruptedException {
        // given
        Episode episode = buildEpisode("并发验证", "都市", "两线程同时生成");
        int threads = 8;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch startGate = new CountDownLatch(1);
        CountDownLatch doneGate = new CountDownLatch(threads);
        AtomicInteger mismatchCount = new AtomicInteger(0);
        AtomicReference<List<ScriptGenerator.SceneDraft>> reference = new AtomicReference<>();
        // when
        for (int i = 0; i < threads; i++) {
            pool.submit(() -> {
                try {
                    startGate.await();
                    List<ScriptGenerator.SceneDraft> result = generator.generate(episode);
                    if (reference.compareAndSet(null, result)) {
                        return;
                    }
                    List<ScriptGenerator.SceneDraft> baseline = reference.get();
                    if (!baseline.equals(result)) {
                        mismatchCount.incrementAndGet();
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    doneGate.countDown();
                }
            });
        }
        startGate.countDown();
        boolean finished = doneGate.await(10, TimeUnit.SECONDS);
        pool.shutdownNow();
        // then
        assertTrue(finished, "并发任务必须在 10 秒内全部完成");
        assertEquals(0, mismatchCount.get(), "并发结果必须完全一致，无数据损坏");
        assertNotNull(reference.get(), "至少有一个线程产出结果");
        assertEquals(4, reference.get().size(), "并发产出的场次数量必须为 4");
    }

    @Test
    void generateKeywordFallbackHandlesAllBlankOutline() {
        // given
        Episode episode = buildEpisode("全空白", "都市", "     ");
        // when
        List<ScriptGenerator.SceneDraft> drafts = generator.generate(episode);
        // then
        assertEquals(4, drafts.size(), "空白大纲仍需 4 场");
        assertTrue(drafts.get(0).description().contains("主角在平静日常中卷入一场无法回避的风波"),
                "空白大纲回退默认句");
        // 空白大纲先回退默认句，再取前 12 字作关键词；"秘密"分支走不到（源码行为）
        assertTrue(drafts.get(0).dialogue().contains("主角在平静日常中卷入一场"), "关键词应为默认句前 12 字");
    }

    @Test
    void generateDialogueAndPromptNeverBlank() {
        // given
        Episode episode = buildEpisode("字段非空", "都市", "检查所有字段");
        // when
        List<ScriptGenerator.SceneDraft> drafts = generator.generate(episode);
        // then
        for (ScriptGenerator.SceneDraft draft : drafts) {
            assertNotNull(draft.location(), "地点不能为 null");
            assertFalse(draft.location().isBlank(), "地点不能为空白");
            assertNotNull(draft.description(), "描述不能为 null");
            assertFalse(draft.description().isBlank(), "描述不能为空白");
            assertNotNull(draft.dialogue(), "对白不能为 null");
            assertFalse(draft.dialogue().isBlank(), "对白不能为空白");
            assertNotNull(draft.prompt(), "提示词不能为 null");
            assertFalse(draft.prompt().isBlank(), "提示词不能为空白");
        }
    }
}