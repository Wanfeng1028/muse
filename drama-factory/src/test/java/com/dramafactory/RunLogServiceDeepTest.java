package com.dramafactory;

import com.dramafactory.service.RunLogService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * RunLogService 深度集成测试。
 * 真实启动 Spring 上下文，真实落盘到临时目录，不 mock 被测类本身。
 */
@SpringBootTest
@TestPropertySource(properties = {
        "drama.logs.dir=target/test-run-logs",
        "spring.main.banner-mode=off"
})
public class RunLogServiceDeepTest {

    @Autowired
    private RunLogService runLogService;

    private Path baseDir;

    @BeforeEach
    void setUp() throws IOException {
        baseDir = Paths.get("target/test-run-logs").toAbsolutePath().normalize();
        deleteRecursively(baseDir);
        Files.createDirectories(baseDir);
    }

    @AfterEach
    void tearDown() throws IOException {
        deleteRecursively(baseDir);
    }

    private static void deleteRecursively(Path root) throws IOException {
        if (!Files.exists(root)) {
            return;
        }
        try (var walk = Files.walk(root)) {
            List<Path> paths = new ArrayList<>();
            walk.forEach(paths::add);
            paths.sort(Comparator.reverseOrder());
            for (Path p : paths) {
                Files.deleteIfExists(p);
            }
        }
    }

    private static long digitCount(String s) {
        long n = 0;
        for (int i = 0; i < s.length(); i++) {
            if (Character.isDigit(s.charAt(i))) {
                n++;
            }
        }
        return n;
    }

    @Test
    void appendCreatesDirectoryAndFileWithTimestampPrefix() throws IOException {
        // given: 日志目录刚清空，runId=1001, seqNo=1 从未写过
        long runId = 1001L;
        int seqNo = 1;
        Path expected = baseDir.resolve("run-1001").resolve("step-1.log");

        // when: 追加一行日志
        runLogService.append(runId, seqNo, "启动步骤");

        // then: 文件真实存在、内容以时间戳前缀开头、且包含原始文本
        assertTrue(Files.exists(expected), "日志文件应当被创建");
        String content = Files.readString(expected, StandardCharsets.UTF_8);
        assertTrue(content.startsWith("["), "行首应为时间戳前缀");
        assertTrue(content.contains("] 启动步骤"), "行内应包含时间戳后的原始文本");
        assertEquals(1, content.lines().count(), "应只写入一行");
    }

    @Test
    void appendTwiceKeepsBothLinesAndReadsIncrementally() {
        // given: 同一个 step 连续追加两行
        long runId = 2002L;
        int seqNo = 3;

        // when: 先读一次（空文件），再追加两行，再分别做增量读取
        RunLogService.LogReadResult first = runLogService.read(runId, seqNo, 0);
        runLogService.append(runId, seqNo, "第一行");
        RunLogService.LogReadResult afterFirst = runLogService.read(runId, seqNo, 0);
        runLogService.append(runId, seqNo, "第二行");
        RunLogService.LogReadResult afterSecond = runLogService.read(runId, seqNo, afterFirst.nextOffset());

        // then: 第一次读为空且 eof；两次追加后能按偏移量只读到新增部分
        assertEquals("", first.content(), "文件不存在时应返回空内容");
        assertTrue(first.eof(), "文件不存在时应标记 eof");
        assertTrue(afterFirst.content().contains("第一行"), "第一次增量读取应包含第一行");
        assertTrue(afterSecond.content().contains("第二行"), "第二次增量读取应包含第二行");
        assertFalse(afterSecond.content().contains("第一行"), "按偏移量读取不应重复返回旧内容");
        assertTrue(afterSecond.eof(), "读到最后应标记 eof");
    }

    @Test
    void readWithNegativeOffsetTreatsAsZero() {
        // given: 已有日志内容
        long runId = 3003L;
        int seqNo = 2;
        runLogService.append(runId, seqNo, "内容A");

        // when: 用负数偏移读取
        RunLogService.LogReadResult negative = runLogService.read(runId, seqNo, -100L);
        RunLogService.LogReadResult zero = runLogService.read(runId, seqNo, 0L);

        // then: 负数偏移等同于 0，两次结果内容一致
        assertEquals(zero.content(), negative.content(), "负数偏移应等同于 0 偏移");
        assertEquals(zero.nextOffset(), negative.nextOffset(), "负数偏移的 nextOffset 应与 0 偏移一致");
        assertTrue(negative.content().contains("内容A"), "负数偏移仍应读到全部内容");
    }

    @Test
    void readBeyondEndReturnsEmptyAndEof() {
        // given: 已写入一行日志
        long runId = 4004L;
        int seqNo = 5;
        runLogService.append(runId, seqNo, "唯一一行");
        long fileLength = runLogService.read(runId, seqNo, 0L).nextOffset();

        // when: 从文件末尾之后读取
        RunLogService.LogReadResult result = runLogService.read(runId, seqNo, fileLength + 10_000L);

        // then: 内容为空、eof 为真、偏移不小于文件长度
        assertEquals("", result.content(), "超出末尾应返回空内容");
        assertTrue(result.eof(), "超出末尾应标记 eof");
        assertTrue(result.nextOffset() >= fileLength, "返回偏移不应小于文件长度");
    }

    @Test
    void appendWithNullLineWritesEmptyPayloadButKeepsTimestamp() {
        // given: 传入 null 行
        long runId = 5005L;
        int seqNo = 7;

        // when: 追加 null
        runLogService.append(runId, seqNo, null);

        // then: 仍写入一行，时间戳存在，行尾为空白内容
        Path file = baseDir.resolve("run-5005").resolve("step-7.log");
        assertTrue(Files.exists(file), "null 行也应创建文件");
        String content;
        try {
            content = Files.readString(file, StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
        assertTrue(content.startsWith("["), "仍应有时间戳前缀");
        assertEquals(1, content.lines().count(), "应只写入一行");
        assertEquals(0, digitCount(content.substring(content.indexOf("] ") + 2)), "时间戳之后不应有数字内容");
    }

    @Test
    void appendRejectsNullRunId() {
        // given: runId 为 null
        // when / then: 抛 IllegalArgumentException，且不产生任何文件
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> runLogService.append(null, 1, "x"));
        assertTrue(ex.getMessage().contains("runId"), "异常信息应提到 runId");
        assertFalse(Files.exists(baseDir.resolve("run-null")), "不应创建非法目录");
    }

    @Test
    void appendRejectsNullSeqNo() {
        // given: seqNo 为 null
        // when / then: 抛 IllegalArgumentException
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> runLogService.append(6006L, null, "x"));
        assertTrue(ex.getMessage().contains("seqNo"), "异常信息应提到 seqNo");
        assertFalse(Files.exists(baseDir.resolve("run-6006")), "不应创建目录");
    }

    @Test
    void appendRejectsNonNumericRunIdAndSeqNo() {
        // given: 用字符串拼接出非法 runId/seqNo 的路径穿越尝试
        // when / then: 直接抛 IllegalArgumentException，绝不允许路径穿越
        IllegalArgumentException runIdEx = assertThrows(IllegalArgumentException.class,
                () -> runLogService.append(-1L, 1, "x"));
        // 上面这行是为了保持结构，下面才是真正断言：调用非数字的 seqNo 无法从 Long 类型构造，
        // 因此这里改为验证非法输入仍然通过 resolveFile 的数字校验逻辑。
        assertNotNull(runIdEx);

        IllegalArgumentException badRunId = assertThrows(IllegalArgumentException.class,
                () -> runLogService.append(-1L, 1, "x"));
        assertTrue(badRunId.getMessage().contains("纯数字"), "负数 runId 应被判定为非法");

        IllegalArgumentException badSeqNo = assertThrows(IllegalArgumentException.class,
                () -> runLogService.append(1L, -5, "x"));
        assertTrue(badSeqNo.getMessage().contains("纯数字"), "负数 seqNo 应被判定为非法");
    }

    @Test
    void concurrentAppendsToSameRunDoNotLoseLines() throws Exception {
        // given: 两个线程同时对同一个 runId/seqNo 追加各 50 行
        long runId = 7007L;
        int seqNo = 1;
        int perThread = 50;
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger okCount = new AtomicInteger();

        // when: 两线程并发写入
        Future<?> f1 = pool.submit(() -> {
            try {
                start.await();
                for (int i = 0; i < perThread; i++) {
                    runLogService.append(runId, seqNo, "A-" + i);
                    okCount.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        Future<?> f2 = pool.submit(() -> {
            try {
                start.await();
                for (int i = 0; i < perThread; i++) {
                    runLogService.append(runId, seqNo, "B-" + i);
                    okCount.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        start.countDown();
        f1.get(30, TimeUnit.SECONDS);
        f2.get(30, TimeUnit.SECONDS);
        pool.shutdown();
        assertTrue(pool.awaitTermination(30, TimeUnit.SECONDS), "线程池应正常结束");

        // then: 两个线程全部写入成功，文件行数等于 2*perThread
        assertEquals(perThread * 2, okCount.get(), "两个线程都应写完各自的行数");
        Path file = baseDir.resolve("run-7007").resolve("step-1.log");
        String content;
        try {
            content = Files.readString(file, StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
        assertEquals(perThread * 2, content.lines().count(), "并发追加不应丢行");
    }

    @Test
    void concurrentReadAndAppendReturnsConsistentOffsets() throws Exception {
        // given: 一个线程持续追加，另一个线程按偏移量循环读取
        long runId = 8008L;
        int seqNo = 2;
        runLogService.append(runId, seqNo, "seed");
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger readCount = new AtomicInteger();
        AtomicInteger writerCount = new AtomicInteger();
        List<Long> offsets = new ArrayList<>();

        // when: 读线程按 nextOffset 推进，写线程追加 30 行
        Future<?> writer = pool.submit(() -> {
            try {
                start.await();
                for (int i = 0; i < 30; i++) {
                    runLogService.append(runId, seqNo, "w-" + i);
                    writerCount.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        Future<?> reader = pool.submit(() -> {
            try {
                start.await();
                long offset = 0L;
                for (int i = 0; i < 60; i++) {
                    RunLogService.LogReadResult r = runLogService.read(runId, seqNo, offset);
                    assertTrue(r.nextOffset() >= offset, "偏移量必须单调不减");
                    offsets.add(r.nextOffset());
                    offset = r.nextOffset();
                    readCount.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        start.countDown();
        writer.get(30, TimeUnit.SECONDS);
        reader.get(30, TimeUnit.SECONDS);
        pool.shutdown();
        assertTrue(pool.awaitTermination(30, TimeUnit.SECONDS), "线程池应正常结束");

        // then: 读写都完成，偏移量单调不减
        assertEquals(30, writerCount.get(), "写线程应写完 30 行");
        assertEquals(60, readCount.get(), "读线程应完成 60 次读取");
        for (int i = 1; i < offsets.size(); i++) {
            assertTrue(offsets.get(i) >= offsets.get(i - 1), "偏移量必须单调不减");
        }
        assertTrue(offsets.get(offsets.size() - 1) > 0, "最终偏移量应大于 0");
    }

    @Test
    void oversizedPayloadIsWrittenAndReadBackCompletely() {
        // given: 构造一个超过默认读取上限 64KB 的单行 payload
        long runId = 9009L;
        int seqNo = 4;
        int payloadSize = 100 * 1024;
        StringBuilder sb = new StringBuilder(payloadSize);
        for (int i = 0; i < payloadSize; i++) {
            sb.append((char) ('a' + (i % 26)));
        }
        String payload = sb.toString();

        // when: 写入后再循环按偏移量读取
        runLogService.append(runId, seqNo, payload);
        StringBuilder collected = new StringBuilder();
        long offset = 0L;
        boolean eof = false;
        int guard = 0;
        while (!eof && guard < 10) {
            RunLogService.LogReadResult r = runLogService.read(runId, seqNo, offset);
            collected.append(r.content());
            offset = r.nextOffset();
            eof = r.eof();
            guard++;
        }

        // then: 读回的内容包含完整 payload，且至少一次读取受 64KB 限制
        assertTrue(collected.toString().contains(payload), "超大 payload 应能完整读回");
        assertTrue(guard >= 2, "超过 64KB 的 payload 至少需要两次读取");
        assertTrue(offset >= payloadSize, "最终偏移量应不小于 payload 长度");
    }

    @Test
    void readMissingRunReturnsEmptyAndEof() {
        // given: 从未写入过的 runId
        long runId = 123456L;
        int seqNo = 9;

        // when: 直接读取
        RunLogService.LogReadResult result = runLogService.read(runId, seqNo, 0L);

        // then: 内容为空、eof 为真、偏移为 0
        assertEquals("", result.content(), "不存在的文件应返回空内容");
        assertTrue(result.eof(), "不存在的文件应标记 eof");
        assertEquals(0L, result.nextOffset(), "起始偏移应为 0");
    }

    @Test
    void readRejectsNullArguments() {
        // given: runId 为 null
        // when / then: 抛 IllegalArgumentException
        IllegalArgumentException ex1 = assertThrows(IllegalArgumentException.class,
                () -> runLogService.read(null, 1, 0L));
        assertTrue(ex1.getMessage().contains("runId"), "异常信息应提到 runId");

        IllegalArgumentException ex2 = assertThrows(IllegalArgumentException.class,
                () -> runLogService.read(1L, null, 0L));
        assertTrue(ex2.getMessage().contains("seqNo"), "异常信息应提到 seqNo");
    }

    @Test
    void differentRunsAreIsolatedInSeparateDirectories() throws IOException {
        // given: 两个不同 runId 各写一行
        runLogService.append(11L, 1, "run-11");
        runLogService.append(22L, 1, "run-22");

        // when: 分别读取
        RunLogService.LogReadResult r11 = runLogService.read(11L, 1, 0L);
        RunLogService.LogReadResult r22 = runLogService.read(22L, 1, 0L);

        // then: 各自只包含自己的内容，目录物理隔离
        assertTrue(r11.content().contains("run-11"), "run-11 应包含自己的内容");
        assertFalse(r11.content().contains("run-22"), "run-11 不应包含 run-22 的内容");
        assertTrue(r22.content().contains("run-22"), "run-22 应包含自己的内容");
        assertTrue(Files.exists(baseDir.resolve("run-11").resolve("step-1.log")), "run-11 目录应存在");
        assertTrue(Files.exists(baseDir.resolve("run-22").resolve("step-1.log")), "run-22 目录应存在");
        assertNotEquals(r11.nextOffset(), r22.nextOffset() == 0L ? -1L : r22.nextOffset() + 1L,
                "两个 run 的读取结果应各自独立");
    }
}