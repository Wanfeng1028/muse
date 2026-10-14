
// LlmScriptService.callModelViaCli 分支覆盖（v2.14）。
package com.dramafactory.service;

import com.dramafactory.metrics.DramaMetrics;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class LlmScriptServiceCliBranchTest {

    @TempDir
    Path tempDir;

    private final ObjectMapper objectMapper = new ObjectMapper();

    private LlmScriptService svc(int timeoutSeconds) {
        return new LlmScriptService(null, objectMapper, true, "test-model", 3000, timeoutSeconds, 2, null,
                new DramaMetrics(new SimpleMeterRegistry(), null, null));
    }

    private Path script(String name, String pythonCode) throws Exception {
        Path p = tempDir.resolve(name);
        Files.writeString(p, pythonCode);
        return p;
    }

    private void setCliPath(LlmScriptService s, String path) throws Exception {
        Field f = LlmScriptService.class.getDeclaredField("effectiveCliPath");
        f.setAccessible(true);
        f.set(s, path);
    }

    private ObjectNode body(String system, String user) {
        ObjectNode root = objectMapper.createObjectNode();
        var messages = root.putArray("messages");
        ObjectNode sm = messages.addObject();
        sm.put("role", "system");
        sm.put("content", system);
        ObjectNode um = messages.addObject();
        um.put("role", "user");
        um.put("content", user);
        return root;
    }

    private String callCli(LlmScriptService s, ObjectNode b) throws Exception {
        Method m = LlmScriptService.class.getDeclaredMethod("callModelViaCli", ObjectNode.class);
        m.setAccessible(true);
        try {
            return (String) m.invoke(s, b);
        } catch (InvocationTargetException e) {
            Throwable c = e.getCause();
            if (c instanceof RuntimeException re) {
                throw re;
            }
            throw new RuntimeException(c);
        }
    }

    @Test
    void cli_happy_returnsStdout() throws Exception {
        Path p = script("happy.py", "print(\"cli-ok\")\n");
        LlmScriptService s = svc(30);
        setCliPath(s, p.toString());

        String out = callCli(s, body("sys", "hello"));

        assertEquals("cli-ok", out);
    }

    @Test
    void cli_exitNonZero_throws() throws Exception {
        Path p = script("fail.py", "import sys\nsys.stderr.write(\"bad\")\nsys.exit(3)\n");
        LlmScriptService s = svc(30);
        setCliPath(s, p.toString());

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> callCli(s, body("sys", "hello")));

        assertTrue(ex.getMessage().contains("CLI 回退失败 exit=3"),
                "实际消息: " + ex.getMessage());
    }

    @Test
    void cli_emptyStdout_throws() throws Exception {
        Path p = script("empty.py", "pass\n");
        LlmScriptService s = svc(30);
        setCliPath(s, p.toString());

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> callCli(s, body("sys", "hello")));

        assertTrue(ex.getMessage().contains("CLI 回退返回为空"),
                "实际消息: " + ex.getMessage());
    }

    @Test
    void cli_timeout_throws() throws Exception {
        Path p = script("slow.py", "import time\ntime.sleep(5)\n");
        LlmScriptService s = svc(1);
        setCliPath(s, p.toString());

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> callCli(s, body("sys", "hello")));

        assertTrue(ex.getMessage().contains("CLI 回退超时"),
                "实际消息: " + ex.getMessage());
    }

    @Test
    void cli_startFailure_throws() throws Exception {
        LlmScriptService s = svc(30);
        setCliPath(s, tempDir.resolve("nonexistent-xyz.py").toString());

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> callCli(s, body("sys", "hello")));

        assertTrue(ex.getMessage().contains("CLI 回退失败 exit=2"),
                "实际消息: " + ex.getMessage());
    }

    @Test
    void cli_userTextPassedAsLastArg() throws Exception {
        Path p = script("argv.py", "import sys\nprint(sys.argv[-1])\n");
        LlmScriptService s = svc(30);
        setCliPath(s, p.toString());

        String out = callCli(s, body("", "hello-user"));

        assertEquals("hello-user", out);
    }
}
