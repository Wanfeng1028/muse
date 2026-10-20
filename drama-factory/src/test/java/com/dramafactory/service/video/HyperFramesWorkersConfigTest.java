package com.dramafactory.service.video;

import com.dramafactory.service.video.HyperFramesVideoProvider.CommandRunner;
import com.dramafactory.service.video.HyperFramesVideoProvider.CommandRunner.ExecResult;
import java.lang.reflect.Field;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.fail;

class HyperFramesWorkersConfigTest {

    private HyperFramesVideoProvider provider;
    private final AtomicReference<List<String>> captured = new AtomicReference<>();

    @TempDir
    private Path tempDir;

    @BeforeEach
    void setUp() throws Exception {
        captured.set(null);
        CommandRunner runner = (command, workDir, timeout) -> {
            if (command.size() >= 2 && "render".equals(command.get(1))) {
                captured.set(new ArrayList<>(command));
                return new ExecResult(0, "ok");
            }
            return new ExecResult(0, "");
        };
        provider = new HyperFramesVideoProvider(runner);
        setField(provider, "workDirBase", tempDir.toString());
        setField(provider, "enabled", true);
    }

    @Test
    void workersConfigurableAndPassedToCli() throws Exception {
        setField(provider, "workers", 8);
        com.dramafactory.model.Shot shot = new com.dramafactory.model.Shot();
        shot.setDescription("hello");
        provider.submit(shot, 6);

        long deadline = System.currentTimeMillis() + 5000;
        while (captured.get() == null) {
            if (System.currentTimeMillis() >= deadline) {
                fail("render command was not captured within 5 seconds");
            }
            Thread.sleep(100);
        }

        List<String> cmd = captured.get();
        int i = cmd.indexOf("--workers");
        assertThat(i).isGreaterThanOrEqualTo(0);
        assertThat(cmd.get(i + 1)).isEqualTo("8");
    }

    @Test
    void workersDefaultIsTwo() throws Exception {
        HyperFramesVideoProvider p2 = new HyperFramesVideoProvider(null);
        assertThat(getField(p2, "workers")).isEqualTo(2);
    }

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
}
