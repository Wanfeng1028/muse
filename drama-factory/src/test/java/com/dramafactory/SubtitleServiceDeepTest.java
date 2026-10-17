package com.dramafactory;

import com.dramafactory.model.Shot;
import com.dramafactory.service.SubtitleService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * SubtitleService 深度集成测试。
 * 真实启动 Spring 上下文，使用真实文件系统落地 SRT 文件，不做任何 mock。
 */
@SpringBootTest
@TestPropertySource(properties = "drama.storage=./target/test-subs-deep")
class SubtitleServiceDeepTest {

    private static final Path STORAGE_ROOT = Paths.get("./target/test-subs-deep");

    @Autowired
    private SubtitleService subtitleService;

    private Long episodeId;

    @BeforeEach
    void setUp() throws IOException {
        // 每个用例用独立 episodeId，避免相互覆盖
        episodeId = System.nanoTime();
        Files.createDirectories(STORAGE_ROOT.resolve("subs"));
    }

    @AfterEach
    void tearDown() throws IOException {
        Path subsDir = STORAGE_ROOT.resolve("subs");
        if (Files.exists(subsDir)) {
            try (var stream = Files.list(subsDir)) {
                stream.filter(p -> p.getFileName().toString().startsWith("episode_"))
                        .forEach(p -> {
                            try {
                                Files.deleteIfExists(p);
                            } catch (IOException ignored) {
                                // 清理失败不影响断言结果
                            }
                        });
            }
        }
    }

    private Shot shot(int no, String dialogue, String description, Integer durationSeconds) {
        Shot s = new Shot();
        s.setShotNo(no);
        s.setDialogue(dialogue);
        s.setDescription(description);
        s.setDurationSeconds(durationSeconds);
        return s;
    }

    private String read(Path file) throws IOException {
        return Files.readString(file, StandardCharsets.UTF_8);
    }

    // 1. 正常生命周期：空分镜列表生成空字幕文件
    @Test
    void buildSrt_emptyShots_producesEmptyFile() throws IOException {
        // given: 一个空的分镜列表
        List<Shot> shots = Collections.emptyList();

        // when: 调用 buildSrt
        Path file = subtitleService.buildSrt(episodeId, shots);

        // then: 文件存在且内容为空字符串
        assertNotNull(file);
        assertTrue(Files.exists(file));
        assertEquals("", read(file));
    }

    // 2. 正常生命周期：对白与描述按优先级选取，空文本跳过但时间轴推进
    @Test
    void buildSrt_textPriorityAndSkip_advancesTimeline() throws IOException {
        // given: 第1条有对白，第2条无对白有描述，第3条两者皆空，第4条有对白
        List<Shot> shots = Arrays.asList(
                shot(1, "第一句对白", "第一句描述", 2),
                shot(2, "  ", "第二句描述", 3),
                shot(3, null, null, 4),
                shot(4, "第四句对白", null, 1)
        );

        // when: 生成字幕
        Path file = subtitleService.buildSrt(episodeId, shots);
        String content = read(file);

        // then: 序号跳过空条目后连续编号，时间轴对齐到 10 秒
        assertTrue(content.contains("1\r\n00:00:00,000 --> 00:00:02,000\r\n第一句对白"));
        assertTrue(content.contains("2\r\n00:00:02,000 --> 00:00:05,000\r\n第二句描述"));
        assertTrue(content.contains("3\r\n00:00:09,000 --> 00:00:10,000\r\n第四句对白"));
        assertFalse(content.contains("第三句"));
    }

    // 3. 边界：durationSeconds 为 null 时使用默认 5 秒，负数按 0 处理
    @Test
    void buildSrt_nullAndNegativeDuration_usesDefaults() throws IOException {
        // given: 一个 null 时长、一个负数时长、一个正常时长
        List<Shot> shots = Arrays.asList(
                shot(1, "默认时长", null, null),
                shot(2, "零时长", null, -3),
                shot(3, "正常时长", null, 2)
        );

        // when: 生成字幕
        Path file = subtitleService.buildSrt(episodeId, shots);
        String content = read(file);

        // then: null 使用 5 秒，负数变为 0 秒，时间轴累计到 7 秒
        assertTrue(content.contains("00:00:00,000 --> 00:00:05,000\r\n默认时长"));
        assertTrue(content.contains("00:00:05,000 --> 00:00:05,000\r\n零时长"));
        assertTrue(content.contains("00:00:05,000 --> 00:00:07,000\r\n正常时长"));
    }

    // 4. 边界：超大 payload 文本按 40 字符切分换行
    @Test
    void buildSrt_oversizeText_wrapsAtMaxLineLength() throws IOException {
        // given: 一段 100 字符的对白
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 100; i++) {
            sb.append((char) ('a' + (i % 26)));
        }
        String longText = sb.toString();
        List<Shot> shots = Collections.singletonList(shot(1, longText, null, 1));

        // when: 生成字幕
        Path file = subtitleService.buildSrt(episodeId, shots);
        String content = read(file);

        // then: 文本按 40 字符被切成 3 段，且不含原 100 字符整段
        String expectedFirstLine = longText.substring(0, 40);
        String expectedSecondLine = longText.substring(40, 80);
        String expectedThirdLine = longText.substring(80, 100);
        assertTrue(content.contains(expectedFirstLine + "\r\n" + expectedSecondLine));
        assertTrue(content.contains(expectedSecondLine + "\r\n" + expectedThirdLine));
        assertFalse(content.contains(longText));
    }

    // 5. 幂等性：同一 Run 重复调用结果一致，文件内容完全相同
    @Test
    void buildSrt_repeatedCall_isIdempotent() throws IOException {
        // given: 一组分镜
        List<Shot> shots = Arrays.asList(
                shot(1, "对白一", null, 2),
                shot(2, null, "描述二", 3)
        );

        // when: 连续调用两次
        Path first = subtitleService.buildSrt(episodeId, shots);
        String firstContent = read(first);
        Path second = subtitleService.buildSrt(episodeId, shots);
        String secondContent = read(second);

        // then: 路径相同、内容逐字节相同
        assertEquals(first, second);
        assertEquals(firstContent, secondContent);
        assertTrue(secondContent.contains("00:00:00,000 --> 00:00:02,000\r\n对白一"));
    }

    // 6. 幂等性：重复调用不会残留旧内容（覆盖写而非追加）
    @Test
    void buildSrt_secondCallOverwrites_notAppends() throws IOException {
        // given: 第一次有两条字幕，第二次只有一条
        List<Shot> firstShots = Arrays.asList(
                shot(1, "旧一", null, 1),
                shot(2, "旧二", null, 1)
        );
        List<Shot> secondShots = Collections.singletonList(shot(1, "新一", null, 1));

        // when: 两次生成同一 episodeId
        subtitleService.buildSrt(episodeId, firstShots);
        Path file = subtitleService.buildSrt(episodeId, secondShots);
        String content = read(file);

        // then: 只剩第二次的内容，旧内容不残留
        assertTrue(content.contains("新一"));
        assertFalse(content.contains("旧一"));
        assertFalse(content.contains("旧二"));
    }

    // 7. 失败注入：目标路径被目录占用时抛出 UncheckedIOException，错误消息带路径
    @Test
    void buildSrt_writeFailure_throwsUncheckedIOException() throws IOException {
        // given: 把目标 srt 路径预先创建为目录，让 Files.writeString 失败
        Path subsDir = STORAGE_ROOT.resolve("subs");
        Files.createDirectories(subsDir);
        Path target = subsDir.resolve("episode_" + episodeId + ".srt");
        Files.createDirectories(target);
        List<Shot> shots = Collections.singletonList(shot(1, "对白", null, 1));

        // when: 调用生成字幕
        UncheckedIOException ex = assertThrows(UncheckedIOException.class,
                () -> subtitleService.buildSrt(episodeId, shots));

        // then: 异常消息包含目标路径，且根因为 IOException
        assertNotNull(ex.getMessage());
        assertTrue(ex.getMessage().contains(target.toString()));
        assertNotNull(ex.getCause());
        assertTrue(ex.getCause() instanceof IOException);
    }

    // 8. 失败注入：抛异常后再次以正常路径调用成功，说明无脏状态残留
    @Test
    void buildSrt_afterFailure_recoverySucceeds() throws IOException {
        // given: 先制造一次写失败（路径被目录占用），随后删除占位目录
        Path subsDir = STORAGE_ROOT.resolve("subs");
        Files.createDirectories(subsDir);
        Path target = subsDir.resolve("episode_" + episodeId + ".srt");
        Files.createDirectories(target);
        List<Shot> shots = Collections.singletonList(shot(1, "恢复对白", null, 2));
        assertThrows(UncheckedIOException.class, () -> subtitleService.buildSrt(episodeId, shots));
        Files.delete(target);

        // when: 再次正常调用
        Path file = subtitleService.buildSrt(episodeId, shots);
        String content = read(file);

        // then: 恢复成功，内容正确
        assertTrue(Files.exists(file));
        assertTrue(content.contains("恢复对白"));
        assertTrue(content.contains("00:00:00,000 --> 00:00:02,000"));
    }

    // 9. 并发：两线程同时推进同一 Run，最终文件内容为其中之一，不出现半截内容
    @Test
    void buildSrt_concurrentTwoThreads_noCorruptedData() throws Exception {
        // given: 两个不同的分镜列表，同 episodeId 并发写入
        List<Shot> shotsA = Collections.singletonList(shot(1, "并发A", null, 1));
        List<Shot> shotsB = Collections.singletonList(shot(1, "并发B", null, 2));

        int rounds = 30;
        AtomicInteger mismatches = new AtomicInteger(0);
        AtomicReference<Throwable> unexpected = new AtomicReference<>();

        for (int i = 0; i < rounds; i++) {
            Path target = STORAGE_ROOT.resolve("subs").resolve("episode_" + episodeId + ".srt");
            Files.deleteIfExists(target);
            ExecutorService pool = Executors.newFixedThreadPool(2);
            CountDownLatch start = new CountDownLatch(1);
            try {
                pool.submit(() -> {
                    try {
                        start.await();
                        subtitleService.buildSrt(episodeId, shotsA);
                    } catch (Throwable t) {
                        unexpected.compareAndSet(null, t);
                    }
                });
                pool.submit(() -> {
                    try {
                        start.await();
                        subtitleService.buildSrt(episodeId, shotsB);
                    } catch (Throwable t) {
                        unexpected.compareAndSet(null, t);
                    }
                });
                start.countDown();
                pool.shutdown();
                boolean finished = pool.awaitTermination(20, TimeUnit.SECONDS);

                // then(每轮): 线程池正常结束
                assertTrue(finished, "并发写入未在超时内完成");

                String content = read(target);
                boolean isA = content.contains("并发A") && content.contains("00:00:00,000 --> 00:00:01,000");
                boolean isB = content.contains("并发B") && content.contains("00:00:00,000 --> 00:00:02,000");
                boolean isAOnly = content.contains("并发A") && !content.contains("并发B");
                boolean isBOnly = content.contains("并发B") && !content.contains("并发A");
                // 文件内容必须完整等于 A 或完整等于 B，不能是两个内容拼接
                if (!((isA && isAOnly) || (isB && isBOnly))) {
                    mismatches.incrementAndGet();
                }
            } finally {
                pool.shutdownNow();
            }
        }

        // then: 所有轮次均未出现脏数据，且无意外异常
        assertNull(unexpected.get(), () -> "并发执行出现异常: " + unexpected.get());
        assertEquals(0, mismatches.get(), "存在并发写入导致的半截/拼接内容");
    }

    // 10. 并发：多线程生成不同 episodeId，互不覆盖
    @Test
    void buildSrt_concurrentDifferentEpisodes_isolated() throws Exception {
        // given: 4 个不同 episodeId，各自并发写入
        int threadCount = 4;
        List<Long> ids = new ArrayList<>();
        for (int i = 0; i < threadCount; i++) {
            ids.add(System.nanoTime() + i * 7919L);
        }
        ExecutorService pool = Executors.newFixedThreadPool(threadCount);
        CountDownLatch start = new CountDownLatch(1);
        AtomicReference<Throwable> unexpected = new AtomicReference<>();

        try {
            for (int i = 0; i < threadCount; i++) {
                final Long id = ids.get(i);
                final String text = "EP" + i;
                final int shotIndex = i + 1;
                pool.submit(() -> {
                    try {
                        start.await();
                        subtitleService.buildSrt(id, Collections.singletonList(shot(1, text, null, shotIndex)));
                    } catch (Throwable t) {
                        unexpected.compareAndSet(null, t);
                    }
                });
            }
            start.countDown();
            pool.shutdown();
            boolean finished = pool.awaitTermination(20, TimeUnit.SECONDS);

            // then: 全部完成，每个文件独立且内容正确
            assertTrue(finished, "不同 episode 并发写入未在超时内完成");
            assertNull(unexpected.get(), () -> "并发执行出现异常: " + unexpected.get());
            for (int i = 0; i < threadCount; i++) {
                Path file = STORAGE_ROOT.resolve("subs").resolve("episode_" + ids.get(i) + ".srt");
                assertTrue(Files.exists(file), "缺少 episode " + ids.get(i) + " 的字幕文件");
                String content = read(file);
                assertTrue(content.contains("EP" + i));
                assertEquals(1, countOccurrences(content, "EP"), "每个文件只应包含自身内容");
                Files.deleteIfExists(file);
            }
        } finally {
            pool.shutdownNow();
        }
    }

    // 11. 边界：单条分镜时序号为 1，起止时间为 0 到 duration
    @Test
    void buildSrt_singleShot_producesSingleBlock() throws IOException {
        // given: 单条分镜
        List<Shot> shots = Collections.singletonList(shot(1, "唯一一句", null, 3));

        // when: 生成字幕
        Path file = subtitleService.buildSrt(episodeId, shots);
        String content = read(file);

        // then: 只有一块字幕，序号为 1，时间轴正确
        assertEquals(1, countOccurrences(content, " --> "));
        assertTrue(content.startsWith("1\r\n"));
        assertTrue(content.contains("00:00:00,000 --> 00:00:03,000"));
        assertTrue(content.contains("唯一一句"));
    }

    // 12. 边界：文本首尾空白被 trim 后再写入
    @Test
    void buildSrt_whitespaceOnlyDialogue_fallsBackToDescription() throws IOException {
        // given: 对白为纯空白，描述有效
        List<Shot> shots = Collections.singletonList(shot(1, "   \t  ", "  有效描述  ", 2));

        // when: 生成字幕
        Path file = subtitleService.buildSrt(episodeId, shots);
        String content = read(file);

        // then: 使用 trim 后的描述，空白对白不写入
        assertTrue(content.contains("有效描述"));
        assertFalse(content.contains("  有效描述  "));
        assertTrue(content.contains("00:00:00,000 --> 00:00:02,000"));
    }

    // 13. 失败注入：storageDir 指向一个已存在的普通文件，创建目录失败抛 UncheckedIOException
    @Test
    void buildSrt_storageDirIsFile_throwsUncheckedIOException() throws IOException {
        // given: 构造一个把 storage 根指向普通文件的 SubtitleService
        Path blockedRoot = STORAGE_ROOT.resolve("blocked-" + System.nanoTime());
        Files.writeString(blockedRoot, "x", StandardCharsets.UTF_8);
        SubtitleService broken = new SubtitleService(blockedRoot.toString());
        List<Shot> shots = Collections.singletonList(shot(1, "对白", null, 1));

        // when: 调用生成字幕
        UncheckedIOException ex = assertThrows(UncheckedIOException.class,
                () -> broken.buildSrt(episodeId, shots));

        // then: 异常信息包含失败路径，根因为 IOException
        assertTrue(ex.getMessage().contains(blockedRoot.resolve("subs").toString()));
        assertNotNull(ex.getCause());
        assertTrue(ex.getCause() instanceof IOException);
        assertFalse(Files.isDirectory(blockedRoot));
    }

    // 14. 边界：时间轴跨分钟与跨小时的格式化正确
    @Test
    void buildSrt_crossHour_formattingIsCorrect() throws IOException {
        // given: 分镜累计时长超过 1 小时
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, "第0秒", null, 59));
        shots.add(shot(2, "第59秒", null, 1));
        shots.add(shot(3, "第60秒", null, 3600));
        shots.add(shot(4, "第3660秒", null, 1));

        // when: 生成字幕
        Path file = subtitleService.buildSrt(episodeId, shots);
        String content = read(file);

        // then: 分钟进位与小时进位都正确
        assertTrue(content.contains("00:00:59,000 --> 00:01:00,000\r\n第59秒"));
        assertTrue(content.contains("00:01:00,000 --> 01:01:00,000\r\n第60秒"));
        assertTrue(content.contains("01:01:00,000 --> 01:01:01,000\r\n第3660秒"));
    }

    // 15. 幂等性：不同 episodeId 生成到不同文件，互不影响
    @Test
    void buildSrt_differentEpisodeIds_produceDistinctFiles() throws IOException {
        // given: 两个不同 episodeId
        Long otherEpisodeId = episodeId + 1L;
        List<Shot> shots = Collections.singletonList(shot(1, "共享对白", null, 1));

        // when: 分别生成
        Path first = subtitleService.buildSrt(episodeId, shots);
        Path second = subtitleService.buildSrt(otherEpisodeId, shots);

        // then: 路径不同，内容各自独立且一致
        assertNotEquals(first, second);
        assertTrue(first.getFileName().toString().equals("episode_" + episodeId + ".srt"));
        assertTrue(second.getFileName().toString().equals("episode_" + otherEpisodeId + ".srt"));
        assertEquals(read(first), read(second));
        Files.deleteIfExists(second);
    }

    // 16. 边界：超多分镜（1000 条）稳定生成且序号连续
    @Test
    void buildSrt_largeShotList_sequenceIsContinuous() throws IOException {
        // given: 1000 条有效分镜
        List<Shot> shots = new ArrayList<>();
        for (int i = 1; i <= 1000; i++) {
            shots.add(shot(i, "第" + i + "句", null, 1));
        }

        // when: 生成字幕
        Path file = subtitleService.buildSrt(episodeId, shots);
        String content = read(file);

        // then: 共 1000 块，序号首尾正确，总时长 1000 秒
        assertEquals(1000, countOccurrences(content, " --> "));
        assertTrue(content.contains("1\r\n00:00:00,000 --> 00:00:01,000\r\n第1句"));
        assertTrue(content.contains("1000\r\n00:16:39,000 --> 00:16:40,000\r\n第1000句"));
    }

    private static int countOccurrences(String haystack, String needle) {
        int count = 0;
        int idx = 0;
        while ((idx = haystack.indexOf(needle, idx)) >= 0) {
            count++;
            idx += needle.length();
        }
        return count;
    }

    private static void assertNull(Object actual, java.util.function.Supplier<String> messageSupplier) {
        if (actual != null) {
            throw new AssertionError(messageSupplier.get());
        }
    }
}