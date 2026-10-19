package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

class HtmlRenderEngineSelectionTest {

    static class FakeRunner implements HtmlRenderVideoProvider.CommandRunner {
        final List<List<String>> commands = new ArrayList<>();
        volatile int exitCode = 0;
        volatile boolean throwOnRun = false;
        volatile CountDownLatch renderLatch = new CountDownLatch(1);

        @Override
        public ExecResult run(List<String> command, Path workDir, long timeoutSeconds) throws IOException {
            List<String> copy = new ArrayList<>(command);
            synchronized (commands) {
                commands.add(copy);
            }
            if (copy.size() > 1 && "render".equals(copy.get(1))) {
                renderLatch.countDown();
            }
            if (throwOnRun) {
                throw new IOException("cli not found");
            }
            return new ExecResult(exitCode, "");
        }
    }

    @Test
    void defaultEngineIsChromiumWithoutProbing() {
        FakeRunner fake = new FakeRunner();
        HtmlRenderVideoProvider provider = new HtmlRenderVideoProvider(fake);

        assertEquals(HtmlRenderVideoProvider.RenderEngine.CHROMIUM, provider.resolveEngine());
        assertTrue(fake.commands.isEmpty(), "默认路径不应触发探活命令");
    }

    @Test
    void hyperframesEngineWhenCliAvailable() {
        FakeRunner fake = new FakeRunner();
        fake.exitCode = 0;
        HtmlRenderVideoProvider provider = new HtmlRenderVideoProvider(fake);
        provider.setEngineConfig("hyperframes");

        assertEquals(HtmlRenderVideoProvider.RenderEngine.HYPERFRAMES, provider.resolveEngine());
        assertEquals(1, fake.commands.size());
        assertEquals(List.of("hyperframes", "--version"), fake.commands.get(0));
    }

    @Test
    void degradesToChromiumWhenCliThrows() {
        FakeRunner fake = new FakeRunner();
        fake.throwOnRun = true;
        HtmlRenderVideoProvider provider = new HtmlRenderVideoProvider(fake);
        provider.setEngineConfig("hyperframes");

        assertEquals(HtmlRenderVideoProvider.RenderEngine.CHROMIUM, provider.resolveEngine());
    }

    @Test
    void degradesToChromiumOnNonZeroExit() {
        FakeRunner fake = new FakeRunner();
        fake.exitCode = 3;
        HtmlRenderVideoProvider provider = new HtmlRenderVideoProvider(fake);
        provider.setEngineConfig("hyperframes");

        assertEquals(HtmlRenderVideoProvider.RenderEngine.CHROMIUM, provider.resolveEngine());
    }

    @Test
    void engineNameIsCaseInsensitive() {
        FakeRunner fake = new FakeRunner();
        fake.exitCode = 0;
        HtmlRenderVideoProvider provider = new HtmlRenderVideoProvider(fake);
        provider.setEngineConfig("HyperFrames");

        assertEquals(HtmlRenderVideoProvider.RenderEngine.HYPERFRAMES, provider.resolveEngine());
    }

    @Test
    void unknownEngineFallsBackToChromium() {
        FakeRunner fake = new FakeRunner();
        HtmlRenderVideoProvider provider = new HtmlRenderVideoProvider(fake);
        provider.setEngineConfig("bogus-value");

        assertEquals(HtmlRenderVideoProvider.RenderEngine.CHROMIUM, provider.resolveEngine());
        assertTrue(fake.commands.isEmpty(), "未知引擎不应触发探活命令");
    }

    @Test
    void submitRunsHyperframesRenderCommand(@TempDir Path tmp) throws Exception {
        FakeRunner fake = new FakeRunner();
        fake.exitCode = 0;
        fake.renderLatch = new CountDownLatch(1);
        HtmlRenderVideoProvider provider = new HtmlRenderVideoProvider(fake);
        provider.setWorkDirBase(tmp.toString());
        provider.setEngineConfig("hyperframes");

        Shot shot = new Shot();
        shot.setDescription("测试镜头");

        String id = provider.submit(shot, 5);
        assertTrue(id.startsWith("htmlrender:"), "submit 返回 id 应以 htmlrender: 开头");

        assertTrue(fake.renderLatch.await(10, TimeUnit.SECONDS), "应在 10 秒内观察到 render 命令");

        List<String> renderCmd = null;
        synchronized (fake.commands) {
            for (List<String> cmd : fake.commands) {
                if (cmd.size() > 1 && "render".equals(cmd.get(1))) {
                    renderCmd = cmd;
                    break;
                }
            }
        }
        assertNotNull(renderCmd, "应记录到一条 render 命令");
        assertTrue(renderCmd.contains("-c"));
        assertTrue(renderCmd.contains("composition.html"));
        assertTrue(renderCmd.contains("--no-browser-gpu"));

        boolean found = false;
        try (var stream = Files.walk(tmp)) {
            List<Path> compositionFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> "composition.html".equals(p.getFileName().toString()))
                    .toList();
            for (Path p : compositionFiles) {
                String content = Files.readString(p);
                if (content.contains("测试镜头")) {
                    found = true;
                    break;
                }
            }
        }
        assertTrue(found, "应存在包含镜头描述的 composition.html");
    }
}
