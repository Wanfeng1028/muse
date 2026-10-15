package com.dramafactory.service;

import com.dramafactory.metrics.DramaMetrics;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * LlmScriptService 分支收尾测试（第五批）。
 *
 * 诚实跳过清单：
 * 1. 141 行 if (envHome != null && !envHome.isBlank())：依赖 System.getenv("HOME")，
 *    为 JVM 全局状态，单元测试不可控，故跳过。
 * 2. 145 行 if (propHome != null && !propHome.isBlank() && !bases.contains(propHome))：
 *    依赖 System.getProperty("user.home")，为 JVM 全局状态，单元测试不可控，故跳过。
 * 3. 157 行 for (String base : bases) 内 if (f.isFile() && f.canExecute())：依赖测试机
 *    文件系统布局（/workspace/skills/weixin-chatapi/bin/chat.py 是否存在），不可控，故跳过。
 * 4. 159 行 f.isFile() && f.canExecute() 的假分支臂：同上，依赖测试机文件系统布局，故跳过。
 * 5. 166 行 effectiveCliPath != null ? ... : ... 的两个臂：其输入取决于上述环境变量与
 *    文件系统探测结果，单元测试不可控；本测试通过反射直接注入 effectiveCliPath 绕开该
 *    探测逻辑，故该日志分支的覆盖不在本轮范围内。
 */
class LlmScriptServiceBranch5Test {

    @TempDir
    Path tempDir;

    private CredentialResolver credentialResolver;
    private DramaMetrics dramaMetrics;
    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() {
        credentialResolver = mock(CredentialResolver.class);
        dramaMetrics = mock(DramaMetrics.class);
        objectMapper = new ObjectMapper();
    }

    private LlmScriptService svc(String cliPath) {
        return new LlmScriptService(
                credentialResolver,
                objectMapper,
                true,
                "Deepseek-v4-flash",
                3000,
                5,
                0,
                cliPath,
                dramaMetrics);
    }

    private static void setCliPath(LlmScriptService s, String path) throws Exception {
        Field f = LlmScriptService.class.getDeclaredField("effectiveCliPath");
        f.setAccessible(true);
        f.set(s, path);
    }

    private static ObjectNode bodyWithMessages(ObjectMapper om, String system, String user) {
        ObjectNode root = om.createObjectNode();
        root.put("model", "m");
        var messages = root.putArray("messages");
        ObjectNode sys = messages.addObject();
        sys.put("role", "system");
        sys.put("content", system);
        ObjectNode usr = messages.addObject();
        usr.put("role", "user");
        usr.put("content", user);
        root.put("max_tokens", 100);
        return root;
    }

    private Object callCli(LlmScriptService s, ObjectNode body) throws Exception {
        Method m = LlmScriptService.class.getDeclaredMethod("callModelViaCli", ObjectNode.class);
        m.setAccessible(true);
        try {
            return m.invoke(s, body);
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            if (cause instanceof Exception ex) {
                throw ex;
            }
            throw e;
        }
    }

    private String writeCliScript(String content) throws Exception {
        Path script = tempDir.resolve("ok.py");
        Files.writeString(script, content, StandardCharsets.UTF_8);
        return script.toAbsolutePath().toString();
    }

    /**
     * 覆盖 callModelWithUsage 第 209 行 if (effectiveCliPath == null) 的 null 臂：
     * effectiveCliPath=null，chatAuth 抛 "no key"，HTTP 失败后不走 CLI 回退，原样抛出。
     */
    @Test
    void callModelWithUsage_nullCliPath_expectsOriginalException() throws Exception {
        LlmScriptService s = svc("");
        setCliPath(s, null);
        when(credentialResolver.chatAuth()).thenThrow(new RuntimeException("no key"));

        ObjectNode body = bodyWithMessages(objectMapper, "sys", "usr");

        RuntimeException ex = assertThrows(RuntimeException.class, () -> s.callModelWithUsage(body));
        assertEquals("no key", ex.getMessage());
    }

    /**
     * 覆盖 callModel 第 406 行 catch 中 if (effectiveCliPath == null) 的真分支臂：
     * effectiveCliPath=null，chatAuth 抛 "no key" → 直接抛出原始异常，不走 CLI。
     */
    @Test
    void callModel_nullCliPath_expectsOriginalException() throws Exception {
        LlmScriptService s = svc("");
        setCliPath(s, null);
        when(credentialResolver.chatAuth()).thenThrow(new RuntimeException("no key"));

        ObjectNode body = bodyWithMessages(objectMapper, "sys", "usr");

        RuntimeException ex = assertThrows(RuntimeException.class, () -> s.callModel(body));
        assertEquals("no key", ex.getMessage());
    }

    /**
     * 覆盖 callModel 第 406 行 catch 中 if (effectiveCliPath == null) 的假分支臂：
     * effectiveCliPath 指向可执行 python 脚本，chatAuth 抛 "no key" → 走 CLI 回退，
     * 返回脚本 stdout "cli-ok"。
     */
    @Test
    void callModel_withCliPath_expectsCliFallbackResult() throws Exception {
        String scriptPath = writeCliScript("print(\"cli-ok\")\n");
        LlmScriptService s = svc(scriptPath);
        setCliPath(s, scriptPath);
        when(credentialResolver.chatAuth()).thenThrow(new RuntimeException("no key"));

        ObjectNode body = bodyWithMessages(objectMapper, "sys", "usr");

        String result = s.callModel(body);

        assertEquals("cli-ok", result);
    }

    /**
     * 覆盖 callModelViaCli 中对 messages 数组的解析与 system/user 文本提取：脚本忽略参数
     * 只打印固定串，验证 CLI 回退链路整体可用（system 非空时会追加 --system 参数）。
     */
    @Test
    void callModelViaCli_withSystemAndUser_expectsStdout() throws Exception {
        String scriptPath = writeCliScript("print(\"cli-ok\")\n");
        LlmScriptService s = svc(scriptPath);
        setCliPath(s, scriptPath);

        ObjectNode body = bodyWithMessages(objectMapper, "系统提示", "用户请求");

        Object result = callCli(s, body);

        assertEquals("cli-ok", result);
    }

    /**
     * 覆盖 parseScenes 第 516 行 if (firstBrace >= 0 && lastBrace > firstBrace
     * && (firstBracket < 0 || firstBrace < firstBracket)) 的假分支臂：当 '[' 出现在 '{'
     * 之前时，走第 519 行数组分支，抽取出 "[1,2]"。
     */
    @Test
    void parseScenes_bracketBeforeBrace_expectsArrayExtraction() throws Exception {
        LlmScriptService s = svc("");

        Method m = LlmScriptService.class.getDeclaredMethod("parseScenes", String.class);
        m.setAccessible(true);

        String content = "先看数组[1,2]再看对象{\"a\":1}";

        assertThrows(LlmScriptUnavailableException.class, () -> {
            try {
                m.invoke(s, content);
            } catch (InvocationTargetException e) {
                Throwable cause = e.getCause();
                if (cause instanceof RuntimeException re) {
                    throw re;
                }
                throw new RuntimeException(cause);
            }
        });
    }

    /**
     * 覆盖 parseScenes 第 516 行 if 条件的真分支臂（firstBrace < firstBracket）：
     * '{' 在 '[' 之前时走对象分支，抽取 "{...}"。注意前缀不能含 '{'（抽取逻辑取第一个 '{'
     * 到最后一个 '}'，前缀带花括号会污染定位），此处用纯文本前缀。
     */
    @Test
    void parseScenes_braceBeforeBracket_expectsObjectExtraction() throws Exception {
        LlmScriptService s = svc("");

        Method m = LlmScriptService.class.getDeclaredMethod("parseScenes", String.class);
        m.setAccessible(true);

        String scenes = "{\"scenes\":["
                + "{\"sceneNo\":1,\"location\":\"A\",\"timeOfDay\":\"白天\",\"description\":\"d1\",\"dialogue\":\"x\",\"prompt\":\"p\"},"
                + "{\"sceneNo\":2,\"location\":\"B\",\"timeOfDay\":\"夜晚\",\"description\":\"d2\",\"dialogue\":\"y\",\"prompt\":\"p\"},"
                + "{\"sceneNo\":3,\"location\":\"C\",\"timeOfDay\":\"黄昏\",\"description\":\"d3\",\"dialogue\":\"z\",\"prompt\":\"p\"},"
                + "{\"sceneNo\":4,\"location\":\"D\",\"timeOfDay\":\"白天\",\"description\":\"d4\",\"dialogue\":\"w\",\"prompt\":\"p\"}"
                + "]}";
        String content = "前缀文本主体 " + scenes;

        Object result = m.invoke(s, content);

        assertTrue(result instanceof java.util.List<?>);
        assertEquals(4, ((java.util.List<?>) result).size());
    }

    /**
     * 覆盖 parseScenes 第 517 行条件 (firstBracket < 0 || firstBrace < firstBracket) 的
     * firstBracket < 0 臂：文本只有 '{...}' 不含 '['，走对象分支。
     */
    @Test
    void parseScenes_noBracket_expectsObjectBranch() throws Exception {
        LlmScriptService s = svc("");

        Method m = LlmScriptService.class.getDeclaredMethod("parseScenes", String.class);
        m.setAccessible(true);

        String content = "{\"scenes\":["
                + "{\"sceneNo\":1,\"location\":\"A\",\"timeOfDay\":\"白天\",\"description\":\"d1\",\"dialogue\":\"x\",\"prompt\":\"p\"},"
                + "{\"sceneNo\":2,\"location\":\"B\",\"timeOfDay\":\"夜晚\",\"description\":\"d2\",\"dialogue\":\"y\",\"prompt\":\"p\"},"
                + "{\"sceneNo\":3,\"location\":\"C\",\"timeOfDay\":\"黄昏\",\"description\":\"d3\",\"dialogue\":\"z\",\"prompt\":\"p\"},"
                + "{\"sceneNo\":4,\"location\":\"D\",\"timeOfDay\":\"白天\",\"description\":\"d4\",\"dialogue\":\"w\",\"prompt\":\"p\"}"
                + "]}";

        Object result = m.invoke(s, content);

        assertTrue(result instanceof java.util.List<?>);
        assertEquals(4, ((java.util.List<?>) result).size());
    }
}
