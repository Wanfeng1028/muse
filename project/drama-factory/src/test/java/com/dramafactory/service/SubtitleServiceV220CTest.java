package com.dramafactory.service;

import com.dramafactory.model.Shot;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * SubtitleService 分支覆盖测试（v2.20 第 C 批）。
 *
 * 诚实跳过说明：
 * - buildSrt 的 IOException catch 臂（源码第 93-95 行）不可达：
 *   要触发该臂必须让 Files.createDirectories 或 Files.writeString 抛出 IOException。
 *   使用 @TempDir 得到的是可写目录，无法在不修改生产代码（无 seam、无依赖注入的 FileSystem 抽象）
 *   的前提下，通过 mock/只读目录等手段稳定制造 IOException（Java 的 Files.writeString 对只读目录
 *   抛的是 AccessDeniedException，其确实继承 IOException，但目录权限在 CI 上不稳定且非跨平台可靠）。
 *   因此按要求诚实跳过，不硬造假测试。
 *
 * - wrapText 的循环多段换行臂与 i>0 加换行臂（源码第 125-131 行）经 buildSrt 间接触达：
 *   通过构造长度 > 40 且 > 80 的 dialogue 文本覆盖多次循环与 i>0 分支。
 */
class SubtitleServiceV220CTest {

    @TempDir
    Path tempDir;

    private SubtitleService newService() {
        return new SubtitleService(tempDir.toString());
    }

    private Shot shotWith(String dialogue, String description, Integer durationSeconds) {
        Shot shot = new Shot();
        shot.setDialogue(dialogue);
        shot.setDescription(description);
        shot.setDurationSeconds(durationSeconds);
        return shot;
    }

    private String readSrt(Path file) throws IOException {
        return Files.readString(file, StandardCharsets.UTF_8);
    }

    // ------------------------------------------------------------------
    // buildSrt：durationSeconds == null 走默认 5 秒臂（源码 58-60 行 true 分支）
    // ------------------------------------------------------------------
    @Test
    void buildSrt_durationSecondsNull_usesDefaultFiveSecondsArm() throws IOException {
        Shot shot = shotWith("hello", null, null);
        Path file = newService().buildSrt(1L, List.of(shot));

        assertTrue(Files.exists(file));
        String content = readSrt(file);
        // 默认 5 秒 -> 00:00:00,000 --> 00:00:05,000
        assertTrue(content.contains("00:00:00,000 --> 00:00:05,000"), content);
        assertTrue(content.contains("hello"), content);
    }

    // ------------------------------------------------------------------
    // buildSrt：durationSeconds < 0 归零臂（源码 61-63 行 true 分支）
    // ------------------------------------------------------------------
    @Test
    void buildSrt_durationSecondsNegative_clampsToZeroArm() throws IOException {
        Shot shot = shotWith("neg", null, -3);
        Path file = newService().buildSrt(2L, List.of(shot));

        String content = readSrt(file);
        // 归零 -> 00:00:00,000 --> 00:00:00,000
        assertTrue(content.contains("00:00:00,000 --> 00:00:00,000"), content);
        assertTrue(content.contains("neg"), content);
    }

    // ------------------------------------------------------------------
    // buildSrt：dialogue 为 null 回退 description 臂（源码 71-74 行 true 分支）
    // ------------------------------------------------------------------
    @Test
    void buildSrt_dialogueNull_fallsBackToDescriptionArm() throws IOException {
        Shot shot = shotWith(null, "descText", 5);
        Path file = newService().buildSrt(3L, List.of(shot));

        String content = readSrt(file);
        assertTrue(content.contains("descText"), content);
    }

    // ------------------------------------------------------------------
    // buildSrt：dialogue 为 blank 回退 description 臂（源码 72 行 text.isBlank() true）
    // ------------------------------------------------------------------
    @Test
    void buildSrt_dialogueBlank_fallsBackToDescriptionArm() throws IOException {
        Shot shot = shotWith("   ", "descFromBlank", 5);
        Path file = newService().buildSrt(4L, List.of(shot));

        String content = readSrt(file);
        assertTrue(content.contains("descFromBlank"), content);
    }

    // ------------------------------------------------------------------
    // buildSrt：dialogue 与 description 均为空走 continue 跳过臂（源码 76-78 行 true）
    // ------------------------------------------------------------------
    @Test
    void buildSrt_dialogueAndDescriptionBlank_continueSkipArm() throws IOException {
        Shot blankShot = shotWith("  ", "  ", 5);
        Path file = newService().buildSrt(5L, List.of(blankShot));

        assertTrue(Files.exists(file));
        String content = readSrt(file);
        // 该条被跳过，不产生字幕序号 1
        assertFalse(content.contains("00:00:00,000 --> 00:00:05,000"), content);
        assertEquals("", content.trim(), content);
    }

    // ------------------------------------------------------------------
    // buildSrt：跳过臂后时间轴仍推进，后续字幕起始时间正确
    // （覆盖 continue 臂 + 时间轴推进组合）
    // ------------------------------------------------------------------
    @Test
    void buildSrt_skipAdvancesCursorForFollowingShot() throws IOException {
        Shot skipped = shotWith(null, null, 5);
        Shot kept = shotWith("second", null, 2);
        Path file = newService().buildSrt(6L, List.of(skipped, kept));

        String content = readSrt(file);
        // 第一条被跳过但时间轴推进到 5 秒，第二条从 5 秒开始
        assertTrue(content.contains("00:00:05,000 --> 00:00:07,000"), content);
        assertTrue(content.contains("second"), content);
    }

    // ------------------------------------------------------------------
    // wrapText：text.length() <= 40 直接返回臂（源码 121-123 行 true）
    // ------------------------------------------------------------------
    @Test
    void buildSrt_wrapTextShortText_returnsDirectlyArm() throws IOException {
        String shortText = "1234567890123456789012345678901234567890"; // 恰好 40
        assertEquals(40, shortText.length());
        Shot shot = shotWith(shortText, null, 5);
        Path file = newService().buildSrt(7L, List.of(shot));

        String content = readSrt(file);
        assertTrue(content.contains(shortText), content);
    }

    // ------------------------------------------------------------------
    // wrapText：循环多段换行臂 + i>0 加换行臂（源码 125-131 行）
    // 文本长度 100 -> 三段（40/40/20），触发 i=40 和 i=80 两次 i>0 换行
    // ------------------------------------------------------------------
    @Test
    void buildSrt_wrapTextLongText_multipleSegmentsAndNewlineArm() throws IOException {
        String longText = "A".repeat(100);
        Shot shot = shotWith(longText, null, 5);
        Path file = newService().buildSrt(8L, List.of(shot));

        String content = readSrt(file);
        // 三段：40 + 40 + 20，中间有两个换行符
        String expectedWrapped = "A".repeat(40) + "\r\n" + "A".repeat(40) + "\r\n" + "A".repeat(20);
        assertTrue(content.contains(expectedWrapped), content);
    }

    // ------------------------------------------------------------------
    // wrapText：恰好 41 字符 -> 两段，触发 i=40 处 i>0 换行臂
    // ------------------------------------------------------------------
    @Test
    void buildSrt_wrapTextFortyOneChars_newlineAtSecondSegmentArm() throws IOException {
        String text = "B".repeat(41);
        Shot shot = shotWith(text, null, 5);
        Path file = newService().buildSrt(9L, List.of(shot));

        String content = readSrt(file);
        String expectedWrapped = "B".repeat(40) + "\r\n" + "B";
        assertTrue(content.contains(expectedWrapped), content);
    }

    // ------------------------------------------------------------------
    // buildSrt：空 shots 列表（无循环迭代）仍生成空文件
    // ------------------------------------------------------------------
    @Test
    void buildSrt_emptyShots_generatesEmptyFile() throws IOException {
        Path file = newService().buildSrt(10L, Collections.emptyList());

        assertTrue(Files.exists(file));
        assertEquals("", readSrt(file));
    }

    // ------------------------------------------------------------------
    // buildSrt：多个正常分镜序号递增 + 时间轴连续
    // ------------------------------------------------------------------
    @Test
    void buildSrt_multipleShots_sequentialIndexAndTimeline() throws IOException {
        Shot first = shotWith("first", null, 3);
        Shot second = shotWith("second", null, 4);
        Path file = newService().buildSrt(11L, List.of(first, second));

        String content = readSrt(file);
        assertTrue(content.contains("1\r\n00:00:00,000 --> 00:00:03,000"), content);
        assertTrue(content.contains("2\r\n00:00:03,000 --> 00:00:07,000"), content);
    }
}
