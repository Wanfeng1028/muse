package com.dramafactory.service;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PromptFileServiceDeepTest {

    private static String md(String name, String body) {
        return "---\n"
                + "name: " + name + "\n"
                + "version: 1.0.0\n"
                + "description: 测试用\n"
                + "---\n"
                + "\n"
                + body;
    }

    @Test
    void 路径穿越攻击_使用上级目录名读取抛出未找到异常(@TempDir Path tmp) throws Exception {
        Files.writeString(tmp.resolve("hello.md"), md("hello", "你好"));

        PromptFileService service = new PromptFileService(tmp.toString());
        service.reloadIfChanged();

        assertThatThrownBy(() -> service.body("../hello"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("../hello");
        assertThat(service.names()).containsExactly("hello");
    }

    @Test
    void 路径穿越攻击_绝对路径读取抛出未找到异常(@TempDir Path tmp) throws Exception {
        Files.writeString(tmp.resolve("hello.md"), md("hello", "你好"));

        PromptFileService service = new PromptFileService(tmp.toString());
        service.reloadIfChanged();

        assertThatThrownBy(() -> service.body("/etc/passwd"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(service.names()).containsExactly("hello");
    }

    @Test
    void 非法文件名不被识别_不进入缓存(@TempDir Path tmp) throws Exception {
        Files.writeString(tmp.resolve("-bad.md"), md("-bad", "横杠开头（首字符不在 [a-zA-Z0-9]）"));
        Files.writeString(tmp.resolve("bad name.md"), md("bad name", "空格"));
        Files.writeString(tmp.resolve("noext"), md("noext", "无扩展名"));
        Files.writeString(tmp.resolve("valid.md"), md("valid", "合法"));

        PromptFileService service = new PromptFileService(tmp.toString());
        service.reloadIfChanged();

        Set<String> names = service.names();
        assertThat(names).contains("valid");
        assertThat(names).doesNotContain("-bad", "bad name", "noext");
    }

    @Test
    void 点开头文件被跳过_不进入缓存(@TempDir Path tmp) throws Exception {
        Files.writeString(tmp.resolve(".hidden.md"), md("hidden", "隐藏文件"));
        Files.writeString(tmp.resolve("visible.md"), md("visible", "可见文件"));

        PromptFileService service = new PromptFileService(tmp.toString());
        service.reloadIfChanged();

        assertThat(service.names()).contains("visible");
        assertThat(service.names()).doesNotContain("hidden");
    }

    @Test
    void 并发写同一文件后读取_内容与最后一次写入一致(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("concurrent.md");
        Files.writeString(file, md("concurrent", "初始内容"));

        PromptFileService service = new PromptFileService(tmp.toString());
        service.reloadIfChanged();
        assertThat(service.body("concurrent")).isEqualTo("初始内容");

        int threads = 8;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicInteger failures = new AtomicInteger();
        List<Future<?>> futures = new ArrayList<>();
        try {
            for (int i = 0; i < threads; i++) {
                final int idx = i;
                futures.add(pool.submit(() -> {
                    try {
                        start.await();
                        String content = md("concurrent", "内容-" + idx);
                        Files.writeString(file, content, StandardCharsets.UTF_8);
                    } catch (IOException | InterruptedException e) {
                        failures.incrementAndGet();
                        Thread.currentThread().interrupt();
                    } finally {
                        done.countDown();
                    }
                }));
            }
            start.countDown();
            assertThat(done.await(30, TimeUnit.SECONDS)).isTrue();
            for (Future<?> f : futures) {
                f.get(30, TimeUnit.SECONDS);
            }
        } finally {
            pool.shutdownNow();
        }
        assertThat(failures.get()).isZero();

        service.reloadIfChanged();
        assertThat(service.body("concurrent")).startsWith("内容-");
    }

    @Test
    void 并发读取同一提示词_多线程结果一致且无异常(@TempDir Path tmp) throws Exception {
        Files.writeString(tmp.resolve("shared.md"), md("shared", "共享内容-{{k}}"));

        PromptFileService service = new PromptFileService(tmp.toString());
        service.reloadIfChanged();

        int threads = 16;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<String>> futures = new ArrayList<>();
        try {
            for (int i = 0; i < threads; i++) {
                futures.add(pool.submit(() -> {
                    start.await();
                    return service.render("shared", Map.of("k", "v"));
                }));
            }
            start.countDown();
            for (Future<String> f : futures) {
                assertThat(f.get(30, TimeUnit.SECONDS)).isEqualTo("共享内容-v");
            }
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void 并发reloadIfChanged_多线程启动无异常且缓存稳定(@TempDir Path tmp) throws Exception {
        for (int i = 0; i < 5; i++) {
            Files.writeString(tmp.resolve("p" + i + ".md"), md("p" + i, "正文" + i));
        }

        PromptFileService service = new PromptFileService(tmp.toString());
        int threads = 12;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicInteger failures = new AtomicInteger();
        try {
            for (int i = 0; i < threads; i++) {
                pool.submit(() -> {
                    try {
                        start.await();
                        service.reloadIfChanged();
                        Set<String> names = service.names();
                        if (names.size() != 5) {
                            failures.incrementAndGet();
                        }
                    } catch (InterruptedException e) {
                        failures.incrementAndGet();
                        Thread.currentThread().interrupt();
                    } finally {
                        done.countDown();
                    }
                });
            }
            start.countDown();
            assertThat(done.await(30, TimeUnit.SECONDS)).isTrue();
        } finally {
            pool.shutdownNow();
        }
        assertThat(failures.get()).isZero();
        assertThat(service.names()).containsExactlyInAnyOrder("p0", "p1", "p2", "p3", "p4");
    }

    @Test
    void 文件不存在读取抛出异常(@TempDir Path tmp) {
        PromptFileService service = new PromptFileService(tmp.toString());

        assertThatThrownBy(() -> service.body("nope"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("nope");
    }

    @Test
    void 目录不存在时reloadIfChanged直接返回且names为空(@TempDir Path tmp) {
        Path missing = tmp.resolve("not-exist-dir");
        PromptFileService service = new PromptFileService(missing.toString());

        service.reloadIfChanged();

        assertThat(service.names()).isEmpty();
        assertThatThrownBy(() -> service.body("anything"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void 超大文件读取_正文完整保留(@TempDir Path tmp) throws Exception {
        StringBuilder sb = new StringBuilder();
        int lines = 20000;
        for (int i = 0; i < lines; i++) {
            sb.append("行-").append(i).append('\n');
        }
        String body = sb.toString();
        Files.writeString(tmp.resolve("big.md"), md("big", body));

        PromptFileService service = new PromptFileService(tmp.toString());

        String loaded = service.body("big");
        assertThat(loaded).startsWith("行-0\n");
        assertThat(loaded).endsWith("行-" + (lines - 1));
        assertThat(loaded).contains("行-12345");
    }

    @Test
    void 超大文件render占位符_全部替换(@TempDir Path tmp) throws Exception {
        StringBuilder sb = new StringBuilder();
        int lines = 5000;
        for (int i = 0; i < lines; i++) {
            sb.append("x={{v}}\n");
        }
        Files.writeString(tmp.resolve("bigvar.md"), md("bigvar", sb.toString()));

        PromptFileService service = new PromptFileService(tmp.toString());

        String rendered = service.render("bigvar", Map.of("v", "OK"));
        assertThat(rendered).doesNotContain("{{v}}");
        assertThat(rendered.split("\n", -1).length).isEqualTo(lines); // parse 已 strip 结尾空白，无尾随换行
        assertThat(rendered).startsWith("x=OK\n");
    }

    @Test
    void render缺失key替换为空串(@TempDir Path tmp) throws Exception {
        Files.writeString(tmp.resolve("tpl.md"), md("tpl", "A={{a}},B={{b}}"));

        PromptFileService service = new PromptFileService(tmp.toString());

        assertThat(service.render("tpl", Map.of("a", "1"))).isEqualTo("A=1,B=");
        assertThat(service.render("tpl", Map.of())).isEqualTo("A=,B=");
        assertThat(service.render("tpl", null)).isEqualTo("A=,B=");
    }

    @Test
    void render替换值含美元符号与反斜杠_不发生正则回溯(@TempDir Path tmp) throws Exception {
        Files.writeString(tmp.resolve("special.md"), md("special", "值={{v}}"));

        PromptFileService service = new PromptFileService(tmp.toString());

        String result = service.render("special", Map.of("v", "$1\\d"));
        assertThat(result).isEqualTo("值=$1\\d");
    }

    @Test
    void mtime未变时不重新解析_内容修改但mtime保持则读到旧值(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("stable.md");
        Files.writeString(file, md("stable", "旧内容"));

        PromptFileService service = new PromptFileService(tmp.toString());
        assertThat(service.body("stable")).isEqualTo("旧内容");

        long fixed = Files.getLastModifiedTime(file).toMillis();
        Files.writeString(file, md("stable", "新内容"));
        Files.setLastModifiedTime(file, java.nio.file.attribute.FileTime.fromMillis(fixed));

        assertThat(service.body("stable")).isEqualTo("旧内容");
    }

    @Test
    void 解析失败文件被跳过_不污染其他提示词(@TempDir Path tmp) throws Exception {
        Files.writeString(tmp.resolve("ok.md"), md("ok", "正常"));
        Files.writeString(tmp.resolve("nofront.md"), "没有 frontmatter\n");
        Files.writeString(tmp.resolve("unclosed.md"), "---\nname: unclosed\n正文无闭合\n");
        Files.writeString(tmp.resolve("noname.md"), "---\nversion: 1.0.0\n---\n\n无 name\n");

        PromptFileService service = new PromptFileService(tmp.toString());
        service.reloadIfChanged();

        assertThat(service.names()).containsExactly("ok");
        assertThat(service.body("ok")).isEqualTo("正常");
        assertThatThrownBy(() -> service.body("nofront"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> service.body("unclosed"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> service.body("noname"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void 删除文件后缓存被移除(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("temp.md");
        Files.writeString(file, md("temp", "临时"));

        PromptFileService service = new PromptFileService(tmp.toString());
        assertThat(service.names()).contains("temp");

        Files.delete(file);
        service.reloadIfChanged();

        assertThat(service.names()).doesNotContain("temp");
        assertThatThrownBy(() -> service.body("temp"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
