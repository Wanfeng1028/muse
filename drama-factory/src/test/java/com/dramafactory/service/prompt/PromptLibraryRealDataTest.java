package com.dramafactory.service.prompt;

import org.junit.jupiter.api.Test;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PromptLibraryRealDataTest {

    private final PromptLibraryService service = new PromptLibraryService();

    @Test
    void testYuaiDeepSeekPromptExistsAndMetadata() {
        Optional<PromptLibraryService.PromptDetail> detail = service.get("yuai-deepseek-prompt");
        assertTrue(detail.isPresent());
        PromptLibraryService.PromptDetail d = detail.get();
        assertEquals("yuai-deepseek-prompt", d.id());
        assertEquals("DeepSeek 做《雨爱》MV 的提示词（部分转录）", d.title());
        assertEquals("根目录", d.source());
        assertEquals("yuai-deepseek-prompt.md", d.path());
    }

    @Test
    void testYuaiDeepSeekPromptSummaryTruncated() {
        Optional<PromptLibraryService.PromptDetail> detail = service.get("yuai-deepseek-prompt");
        assertTrue(detail.isPresent());
        PromptLibraryService.PromptDetail d = detail.get();
        String expectedSummary = "来源：抖音 @千Bright Future《deepseek 制作〈雨爱〉视频讲解》（2026-10-19 发布，13:03） 转录状态：**不完整**——讲解视频里把 16 页 Word（提示词.doc，共 16951 字）在约 02:38–03:10 用 32 秒快速滚动展示，且页面顺序跳跃（02:38 显示第 12 页、02:40 显示第 1 页、02:53 显示第 13 页），视频进度条无";
        assertEquals(expectedSummary, d.summary());
        assertEquals(200, d.summary().length());
    }

    @Test
    void testYuaiDeepSeekPromptContent() {
        Optional<PromptLibraryService.PromptDetail> detail = service.get("yuai-deepseek-prompt");
        assertTrue(detail.isPresent());
        PromptLibraryService.PromptDetail d = detail.get();
        assertNotNull(d.content());
        assertFalse(d.content().isEmpty());
        assertTrue(d.content().startsWith("# DeepSeek 做《雨爱》MV 的提示词（部分转录）"));
        assertTrue(d.content().contains("分镜八（186–224 秒，尾声副歌）"));
    }

    @Test
    void testYuaiSummaryTruncationProof() {
        Optional<PromptLibraryService.PromptDetail> detail = service.get("yuai-deepseek-prompt");
        assertTrue(detail.isPresent());
        PromptLibraryService.PromptDetail d = detail.get();
        assertTrue(d.summary().endsWith("视频进度条无"));
        assertTrue(d.content().contains("视频进度条无法精确定位到每一页"));
    }

    @Test
    void testPdoomStoryboardExistsAndMetadata() {
        Optional<PromptLibraryService.PromptDetail> detail = service.get("pdoom-video__STORYBOARD");
        assertTrue(detail.isPresent());
        PromptLibraryService.PromptDetail d = detail.get();
        assertEquals("pdoom-video__STORYBOARD", d.id());
        assertEquals("I'm Upping My P(doom): storyboard", d.title());
        assertEquals("pdoom-video", d.source());
        assertEquals("pdoom-video/STORYBOARD.md", d.path());
    }

    @Test
    void testPdoomStoryboardContent() {
        Optional<PromptLibraryService.PromptDetail> detail = service.get("pdoom-video__STORYBOARD");
        assertTrue(detail.isPresent());
        PromptLibraryService.PromptDetail d = detail.get();
        assertNotNull(d.content());
        assertTrue(d.content().startsWith("# I'm Upping My P(doom): storyboard"));
        assertTrue(d.content().contains("Was it all for show?"));
    }

    @Test
    void testPdoomStoryboardEmptySummary() {
        Optional<PromptLibraryService.PromptDetail> detail = service.get("pdoom-video__STORYBOARD");
        assertTrue(detail.isPresent());
        PromptLibraryService.PromptDetail d = detail.get();
        assertNotNull(d.summary());
        assertEquals("", d.summary());
    }

    @Test
    void testOpusInferenceStartupLaunchExistsAndMetadata() {
        Optional<PromptLibraryService.PromptDetail> detail = service.get("opus-video-prompts__prompts__01-inference-startup-launch");
        assertTrue(detail.isPresent());
        PromptLibraryService.PromptDetail d = detail.get();
        assertEquals("opus-video-prompts__prompts__01-inference-startup-launch", d.id());
        assertEquals("推理创业公司发布视频", d.title());
        assertEquals("opus-video-prompts", d.source());
        assertEquals("opus-video-prompts/prompts/01-inference-startup-launch.md", d.path());
    }

    @Test
    void testOpusInferenceStartupLaunchSummary() {
        Optional<PromptLibraryService.PromptDetail> detail = service.get("opus-video-prompts__prompts__01-inference-startup-launch");
        assertTrue(detail.isPresent());
        PromptLibraryService.PromptDetail d = detail.get();
        String expectedSummary = "- **作者**：Deedy (@deedydas) - **原帖 / 来源**：https://x.com/deedydas/status/2102787937482252537 - **分组**：2.1 一句话即可出片";
        assertEquals(expectedSummary, d.summary());
        assertEquals(111, d.summary().length());
    }

    @Test
    void testOpusInferenceStartupLaunchContent() {
        Optional<PromptLibraryService.PromptDetail> detail = service.get("opus-video-prompts__prompts__01-inference-startup-launch");
        assertTrue(detail.isPresent());
        PromptLibraryService.PromptDetail d = detail.get();
        assertNotNull(d.content());
        assertTrue(d.content().contains("make a modern slick and punchy video for a modern startup that works on inference"));
    }

    @Test
    void testPdoomReadmeArchiveChineseFilename() {
        Optional<PromptLibraryService.PromptDetail> detail = service.get("pdoom-video__README-archive-note");
        assertTrue(detail.isPresent());
        PromptLibraryService.PromptDetail d = detail.get();
        assertEquals("pdoom-video__README-archive-note", d.id());
        assertEquals("PDoomVideo 存档说明", d.title());
        assertEquals("pdoom-video", d.source());
        assertEquals("pdoom-video/README-archive-note.md", d.path());
    }

    @Test
    void testPdoomReadmeArchiveSummaryAndContent() {
        Optional<PromptLibraryService.PromptDetail> detail = service.get("pdoom-video__README-archive-note");
        assertTrue(detail.isPresent());
        PromptLibraryService.PromptDetail d = detail.get();
        String expectedSummary = "来源仓库：https://github.com/JohnHeibel/PDoomVideo （本次存档基于 main 分支浅克隆后逐文件拉取，2026-10-20）";
        assertEquals(expectedSummary, d.summary());
        assertEquals(82, d.summary().length());
        assertTrue(d.content().contains("https://github.com/JohnHeibel/PDoomVideo"));
    }

    @Test
    void testXiaozhengMvTutorialExistsAndMetadata() {
        Optional<PromptLibraryService.PromptDetail> detail = service.get("xiaozheng-mv-tutorial");
        assertTrue(detail.isPresent());
        PromptLibraryService.PromptDetail d = detail.get();
        assertEquals("xiaozheng-mv-tutorial", d.id());
        assertEquals("AI MV 七步教程拆解（小政zzzzz）", d.title());
        assertEquals("根目录", d.source());
        assertEquals("xiaozheng-mv-tutorial.md", d.path());
    }

    @Test
    void testXiaozhengMvTutorialSummaryAndContent() {
        Optional<PromptLibraryService.PromptDetail> detail = service.get("xiaozheng-mv-tutorial");
        assertTrue(detail.isPresent());
        PromptLibraryService.PromptDetail d = detail.get();
        String expectedSummary = "来源：抖音 @小政zzzzz《5天做了4支MV，一帧都没手绘》（2026-10-04 发布，时长 09:14） 拆解对象：《才不是为你回答的！》——从空文件夹到成片的完整过程。作者称一支 MV 约消耗 20 亿 token，主调度为 Claude Code（Claude Opus 5.5）。";
        assertEquals(expectedSummary, d.summary());
        assertEquals(146, d.summary().length());
        assertTrue(d.content().contains("人只做 4 个决定"));
    }

    @Test
    void testRootReadme() {
        Optional<PromptLibraryService.PromptDetail> detail = service.get("README");
        assertTrue(detail.isPresent());
        PromptLibraryService.PromptDetail d = detail.get();
        assertEquals("README", d.id());
        assertEquals("Prompt 仓库", d.title());
        assertEquals("根目录", d.source());
        assertEquals("README.md", d.path());
        String expectedSummary = "存放从各处收集、实测有用的提示词与教程拆解，配合剧坊（drama-factory）与 skill 库使用。";
        assertEquals(expectedSummary, d.summary());
        assertEquals(53, d.summary().length());
    }

    @Test
    void testIdRulesAndGetNonExistent() {
        Optional<PromptLibraryService.PromptDetail> storyboard = service.get("pdoom-video__STORYBOARD");
        assertTrue(storyboard.isPresent());
        assertTrue(storyboard.get().id().contains("__"));
        assertFalse(storyboard.get().id().contains("/"));

        Optional<PromptLibraryService.PromptDetail> opus = service.get("opus-video-prompts__prompts__01-inference-startup-launch");
        assertTrue(opus.isPresent());
        assertTrue(opus.get().id().contains("__"));
        assertFalse(opus.get().id().contains("/"));

        assertFalse(service.get("no-such-id").isPresent());
        assertFalse(service.get(null).isPresent());
    }
}
