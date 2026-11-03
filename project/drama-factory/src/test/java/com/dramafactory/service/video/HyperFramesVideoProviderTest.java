package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.dramafactory.service.video.HyperFramesVideoProvider.CommandRunner;
import com.dramafactory.service.video.HyperFramesVideoProvider.CommandRunner.ExecResult;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * HyperFramesVideoProvider 单元测试。零真实进程，全部通过 fake CommandRunner 注入。
 */
class HyperFramesVideoProviderTest {

    @TempDir
    Path tempDir;

    private HyperFramesVideoProvider provider;

    private void setField(Object target, String name, Object value) throws Exception {
        Field f = target.getClass().getDeclaredField(name);
        f.setAccessible(true);
        f.set(target, value);
    }

    private Object getField(Object target, String name) throws Exception {
        Field f = target.getClass().getDeclaredField(name);
        f.setAccessible(true);
        return f.get(target);
    }

    @BeforeEach
    void setUp() throws Exception {
        provider = new HyperFramesVideoProvider(null);
        setField(provider, "workDirBase", tempDir.toString());
        setField(provider, "enabled", true);
    }

    private Shot shotWith(String description) {
        Shot shot = new Shot();
        shot.setDescription(description);
        return shot;
    }

    @Test
    void submit_成功返回任务ID并写composition() throws Exception {
        CountDownLatch renderLatch = new CountDownLatch(1);
        AtomicReference<List<String>> capturedRenderCommand = new AtomicReference<>();

        CommandRunner runner = (command, workDir, timeout) -> {
            if (command.size() >= 2 && "--version".equals(command.get(1))) {
                return new ExecResult(0, "hyperframes 0.1.0");
            }
            if (command.size() >= 2 && "render".equals(command.get(1))) {
                capturedRenderCommand.set(new ArrayList<>(command));
                renderLatch.countDown();
                return new ExecResult(0, "ok");
            }
            return new ExecResult(0, "");
        };

        provider = new HyperFramesVideoProvider(runner);
        setField(provider, "workDirBase", tempDir.toString());
        setField(provider, "enabled", true);

        Shot shot = shotWith("A<B>&\"C\"");
        String taskId = provider.submit(shot, 8);

        assertThat(taskId).startsWith("hyperframes:");

        Path taskDir = Path.of(taskId.substring("hyperframes:".length()));
        Path composition = taskDir.resolve("composition.html");
        assertThat(composition).exists();

        String html = Files.readString(composition, StandardCharsets.UTF_8);
        assertThat(html).contains("&lt;");
        assertThat(html).doesNotContain("<B>");

        boolean rendered = renderLatch.await(5, TimeUnit.SECONDS);
        assertThat(rendered).isTrue();

        List<String> cmd = capturedRenderCommand.get();
        assertThat(cmd).isNotNull();
        assertThat(cmd).containsExactly(
                "hyperframes", "render",
                "-c", "composition.html",
                "-o", "out/video.mp4",
                "--resolution", "1080p",
                "--fps", "24",
                "--workers", "2",
                "--no-browser-gpu");
    }

    @Test
    void submit_CLI不可用抛清晰错误() throws Exception {
        CommandRunner runner = (command, workDir, timeout) -> new ExecResult(1, "not found");

        provider = new HyperFramesVideoProvider(runner);
        setField(provider, "workDirBase", tempDir.toString());
        setField(provider, "enabled", true);

        assertThatThrownBy(() -> provider.submit(shotWith("hello"), 5))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("hyperframes CLI 不可用");
    }

    @Test
    void submit_未启用抛IllegalStateException() throws Exception {
        CommandRunner runner = (command, workDir, timeout) -> new ExecResult(0, "hyperframes 0.1.0");

        provider = new HyperFramesVideoProvider(runner);
        setField(provider, "workDirBase", tempDir.toString());
        setField(provider, "enabled", false);

        assertThatThrownBy(() -> provider.submit(shotWith("hello"), 5))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("未启用");
    }

    @Test
    void submit_seconds非法抛IllegalArgumentException() throws Exception {
        CommandRunner runner = (command, workDir, timeout) -> new ExecResult(0, "hyperframes 0.1.0");

        provider = new HyperFramesVideoProvider(runner);
        setField(provider, "workDirBase", tempDir.toString());
        setField(provider, "enabled", true);

        assertThatThrownBy(() -> provider.submit(shotWith("hello"), 0))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> provider.submit(shotWith("hello"), -1))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void poll_三态() throws Exception {
        CommandRunner runner = (command, workDir, timeout) -> new ExecResult(0, "hyperframes 0.1.0");

        provider = new HyperFramesVideoProvider(runner);
        setField(provider, "workDirBase", tempDir.toString());
        setField(provider, "enabled", true);

        Path taskDir = tempDir.resolve("hyperframes-xxx");
        String taskId = "hyperframes:" + taskDir.toAbsolutePath();
        Path outDir = taskDir.resolve("out");
        Files.createDirectories(outDir);

        // COMPLETED
        Files.writeString(outDir.resolve("video.mp4"), "fake-video");
        VideoProvider.ProbeResult completed = provider.poll(taskId);
        assertThat(completed.status()).isEqualTo(VideoProvider.RemoteStatus.COMPLETED);
        assertThat(completed.progress()).isEqualTo(100);
        assertThat(completed.videoUrl()).isNotBlank();

        // FAILED via FAILED file
        Files.delete(outDir.resolve("video.mp4"));
        Files.writeString(outDir.resolve("FAILED"), "boom");
        VideoProvider.ProbeResult failed = provider.poll(taskId);
        assertThat(failed.status()).isEqualTo(VideoProvider.RemoteStatus.FAILED);
        assertThat(failed.errorMessage()).isNotBlank();

        // PROCESSING
        Files.delete(outDir.resolve("FAILED"));
        VideoProvider.ProbeResult processing = provider.poll(taskId);
        assertThat(processing.status()).isEqualTo(VideoProvider.RemoteStatus.PROCESSING);

        // painted: -> FAILED
        VideoProvider.ProbeResult painted = provider.poll("painted:/x");
        assertThat(painted.status()).isEqualTo(VideoProvider.RemoteStatus.FAILED);
    }

    @Test
    void probeConnectivity_OK与UNREACHABLE() throws Exception {
        CommandRunner okRunner = (command, workDir, timeout) -> new ExecResult(0, "hyperframes 0.1.0");
        HyperFramesVideoProvider okProvider = new HyperFramesVideoProvider(okRunner);
        setField(okProvider, "workDirBase", tempDir.toString());
        setField(okProvider, "enabled", true);

        assertThat(okProvider.probeConnectivity().status())
                .isEqualTo(VideoProvider.ConnectivityStatus.OK);

        CommandRunner ioRunner = (command, workDir, timeout) -> {
            throw new IOException("network down");
        };
        HyperFramesVideoProvider badProvider = new HyperFramesVideoProvider(ioRunner);
        setField(badProvider, "workDirBase", tempDir.toString());
        setField(badProvider, "enabled", true);

        assertThat(badProvider.probeConnectivity().status())
                .isEqualTo(VideoProvider.ConnectivityStatus.UNREACHABLE);
    }

    @Test
    void render_失败写FAILED标记() throws Exception {
        CountDownLatch renderLatch = new CountDownLatch(1);

        CommandRunner runner = (command, workDir, timeout) -> {
            if (command.size() >= 2 && "--version".equals(command.get(1))) {
                return new ExecResult(0, "hyperframes 0.1.0");
            }
            if (command.size() >= 2 && "render".equals(command.get(1))) {
                renderLatch.countDown();
                return new ExecResult(3, "render failed");
            }
            return new ExecResult(0, "");
        };

        provider = new HyperFramesVideoProvider(runner);
        setField(provider, "workDirBase", tempDir.toString());
        setField(provider, "enabled", true);

        String taskId = provider.submit(shotWith("hello"), 5);

        assertThat(renderLatch.await(5, TimeUnit.SECONDS)).isTrue();

        Path outDir = Path.of(taskId.substring("hyperframes:".length())).resolve("out");
        Path failedFile = outDir.resolve("FAILED");

        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < deadline && !Files.exists(failedFile)) {
            Thread.sleep(20);
        }

        assertThat(failedFile).exists();
        assertThat(provider.poll(taskId).status())
                .isEqualTo(VideoProvider.RemoteStatus.FAILED);
    }

    @Test
    void composition_不含外部资源() throws Exception {
        CountDownLatch renderLatch = new CountDownLatch(1);

        CommandRunner runner = (command, workDir, timeout) -> {
            if (command.size() >= 2 && "--version".equals(command.get(1))) {
                return new ExecResult(0, "hyperframes 0.1.0");
            }
            if (command.size() >= 2 && "render".equals(command.get(1))) {
                renderLatch.countDown();
                return new ExecResult(0, "ok");
            }
            return new ExecResult(0, "");
        };

        provider = new HyperFramesVideoProvider(runner);
        setField(provider, "workDirBase", tempDir.toString());
        setField(provider, "enabled", true);

        String taskId = provider.submit(shotWith("hello"), 5);
        assertThat(renderLatch.await(5, TimeUnit.SECONDS)).isTrue();

        Path composition = Path.of(taskId.substring("hyperframes:".length())).resolve("composition.html");
        String html = Files.readString(composition, StandardCharsets.UTF_8);
        assertThat(html).doesNotContain("http://");
        assertThat(html).doesNotContain("https://");
    }
}
