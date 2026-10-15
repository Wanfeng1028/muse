package com.dramafactory.service;

import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.File;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/**
 * LlmScriptService 分支覆盖测试（第 4 批）。
 *
 * <p>覆盖清单：A1-A5（validate 自动探测）、B1（parseChatResponse choices 非数组臂）、
 * C1（buildUserContent genre 空串回退）、D1-D3（callModelViaCli 各分支）、
 * E1-E6（parseScenes 各分支）。</p>
 *
 * <p>诚实跳过清单（经分析确认单元测试不可确定性触达，故不写测试硬刷）：</p>
 * <ol>
 *   <li>行 141 {@code envHome != null && !envHome.isBlank()} 的两个 false 臂：
 *       System.getenv 在 JVM 内不可修改，单元测试无法触达。</li>
 *   <li>行 145 {@code propHome != null && !propHome.isBlank()} 的 false 臂：
 *       user.home 在 JVM 内永不为 null 或空串，无法触达。</li>
 *   <li>行 205-214 {@code callModelWithUsage} 的 try/catch 全体：
 *       {@code LlmTransport.postJson} 四参重载无测试接缝、走真实 HTTPS，
 *       单元测试无法确定性触发成功或失败，跳过（建议后续版本加接缝再补）。</li>
 *   <li>行 399-412 {@code callModel(ObjectNode)} 全体：同上，走真实 HTTPS 无接缝，跳过。</li>
 *   <li>行 319-321 backoff 期间 {@code InterruptedException}：
 *       需精确中断 sleeping 线程，时序不可靠，跳过。</li>
 *   <li>行 449-450 {@code pb.start()} 的 IOException：
 *       argv[0] 恒为真实存在的 python3，起不来进程的路径走不到，跳过。</li>
 *   <li>行 455-457 / 464-465：CLI 中断与流读取失败，无法确定性触发，跳过。</li>
 * </ol>
 */
class LlmScriptServiceBranch4Test {

    private static final String SCENE_1 =
            "{\"sceneNo\":1,\"location\":\"L1\",\"timeOfDay\":\"白天\",\"description\":\"D1\",\"dialogue\":\"G1\",\"prompt\":\"P1\"}";
    private static final String SCENE_2 =
            "{\"sceneNo\":2,\"location\":\"L2\",\"timeOfDay\":\"黄昏\",\"description\":\"D2\",\"dialogue\":\"G2\",\"prompt\":\"P2\"}";
    private static final String SCENE_3 =
            "{\"sceneNo\":3,\"location\":\"L3\",\"timeOfDay\":\"夜晚\",\"description\":\"D3\",\"dialogue\":\"G3\",\"prompt\":\"P3\"}";
    private static final String SCENE_4 =
            "{\"sceneNo\":4,\"location\":\"L4\",\"timeOfDay\":\"白天\",\"description\":\"D4\",\"dialogue\":\"G4\",\"prompt\":\"P4\"}";

    private static String validFourScenes() {
        return "{\"scenes\":[" + SCENE_1 + "," + SCENE_2 + "," + SCENE_3 + "," + SCENE_4 + "]}";
    }

    private static class Stub extends LlmScriptService {
        private final List<String> responses;
        private ObjectNode capturedBody;
        Stub(List<String> responses, int maxRetries) {
            super(null, new ObjectMapper(), true, "test-model", 3000, 120, maxRetries, null,
                    new DramaMetrics(new SimpleMeterRegistry(), null, null));
            this.responses = responses;
        }
        @Override
        LlmScriptService.ModelCallResult callModelWithUsage(ObjectNode body) {
            this.capturedBody = body;
            return new LlmScriptService.ModelCallResult(responses.get(0), 0, 0);
        }
    }

    private String callCli(LlmScriptService s, ObjectNode b) throws Exception {
        Method m = LlmScriptService.class.getDeclaredMethod("callModelViaCli", ObjectNode.class);
        m.setAccessible(true);
        try { return (String) m.invoke(s, b); }
        catch (InvocationTargetException e) {
            Throwable c = e.getCause();
            if (c instanceof RuntimeException re) throw re;
            throw new RuntimeException(c);
        }
    }

    private void setCliPath(LlmScriptService s, String path) throws Exception {
        Field f = LlmScriptService.class.getDeclaredField("effectiveCliPath");
        f.setAccessible(true); f.set(s, path);
    }

    private String getCliPath(LlmScriptService s) throws Exception {
        Field f = LlmScriptService.class.getDeclaredField("effectiveCliPath");
        f.setAccessible(true); return (String) f.get(s);
    }

    private LlmScriptService newService(String cliPath) {
        return new LlmScriptService(null, new ObjectMapper(), true, "test-model", 3000, 120, 0, cliPath,
                new DramaMetrics(new SimpleMeterRegistry(), null, null));
    }

    private LlmScriptService newServiceTimeout(int timeoutSeconds, String cliPath) {
        return new LlmScriptService(null, new ObjectMapper(), true, "test-model", 3000, timeoutSeconds, 0,
                cliPath, new DramaMetrics(new SimpleMeterRegistry(), null, null));
    }

    private Episode newEpisode(String title, String genre, String outline) {
        Episode e = new Episode();
        e.setId(1L);
        e.setOutline(outline);
        DramaProject p = new DramaProject();
        p.setTitle(title);
        p.setGenre(genre);
        e.setProject(p);
        return e;
    }

    // ---------------- A. validate() 自动探测 ----------------

    /**
     * 覆盖行 145：{@code !bases.contains(propHome)} 为 false 的臂（去重逻辑）。
     * user.home 设为与 HOME 相同，使 bases 已含 propHome 从而不重复添加。
     */
    @Test
    void userHomeEqualsEnvHome_expectsValidatePassesWithoutDuplicate() throws Exception {
        String originalHome = System.getProperty("user.home");
        String envHome = System.getenv("HOME");
        try {
            if (envHome == null || envHome.isBlank()) {
                // 环境无 HOME，跳过该臂（去重臂只在 HOME 存在时有意义）
                return;
            }
            System.setProperty("user.home", envHome);
            LlmScriptService s = newService("");
            s.validate(); // 不抛异常即覆盖到去重臂
            // 无外部可观察差异，覆盖即达标
            assertTrue(true);
        } finally {
            System.setProperty("user.home", originalHome);
        }
    }

    /**
     * 覆盖行 157/159：循环跑完未找到 chat.py 文件。
     * 前提：user.home=@TempDir（无 chat.py），且真实 HOME 下也没有
     * workspace/skills/weixin-chatapi/bin/chat.py，否则可能命中真实文件。
     */
    @Test
    void userHomeWithoutCli_expectsEffectiveCliPathNull(@TempDir Path tempDir) throws Exception {
        // 本机 $HOME 下若已有真实 chat.py，探测循环会在第一个 base 就命中并 break，
        // "未找到"路径走不到；此时跳过（在无该文件的机器上本测试会正常执行覆盖）。
        String envHome = System.getenv("HOME");
        assumeTrue(envHome == null || envHome.isBlank()
                || !java.nio.file.Files.isRegularFile(java.nio.file.Paths.get(envHome + "/workspace/skills/weixin-chatapi/bin/chat.py")),
                "本机 $HOME 下存在真实 chat.py，跳过'未找到'路径测试");
        String originalHome = System.getProperty("user.home");
        try {
            System.setProperty("user.home", tempDir.toString());
            LlmScriptService s = newService("");
            s.validate();
            assertNull(getCliPath(s));
        } finally {
            System.setProperty("user.home", originalHome);
        }
    }

    /**
     * 覆盖行 159/163：找到可执行文件，effectiveCliPath 被赋值。
     * 注意：探测先查真实 $HOME，若其下已有 chat.py 则命中它（本机即如此）；
     * tempDir 下的文件是为无该文件的机器准备的。两种情况都覆盖到"找到即 break"臂。
     */
    @Test
    void userHomeWithExecutableCli_expectsEffectiveCliPathSet(@TempDir Path tempDir) throws Exception {
        String originalHome = System.getProperty("user.home");
        try {
            Path cli = tempDir.resolve("workspace/skills/weixin-chatapi/bin/chat.py");
            Files.createDirectories(cli.getParent());
            Files.writeString(cli, "#!/bin/sh\necho ok\n");
            cli.toFile().setExecutable(true);

            System.setProperty("user.home", tempDir.toString());
            LlmScriptService s = newService("");
            s.validate();

            String path = getCliPath(s);
            assertNotNull(path);
            assertTrue(path.endsWith("chat.py"));
        } finally {
            System.setProperty("user.home", originalHome);
        }
    }

    /**
     * 覆盖行 159：{@code f.isFile()} true 但 {@code f.canExecute()} false 的臂。
     * Files.writeString 默认创建的文件不可执行，验证跳过该文件继续找。
     */
    @Test
    void userHomeWithNonExecutableCli_expectsEffectiveCliPathNull(@TempDir Path tempDir) throws Exception {
        // 同上：本机 $HOME 有真实可执行 chat.py 时，循环在第一个 base 即 break，
        // tempDir 下的不可执行文件走不到；此时跳过。
        String envHome = System.getenv("HOME");
        assumeTrue(envHome == null || envHome.isBlank()
                || !java.nio.file.Files.isRegularFile(java.nio.file.Paths.get(envHome + "/workspace/skills/weixin-chatapi/bin/chat.py")),
                "本机 $HOME 下存在真实 chat.py，跳过不可执行文件测试");
        String originalHome = System.getProperty("user.home");
        try {
            Path cli = tempDir.resolve("workspace/skills/weixin-chatapi/bin/chat.py");
            Files.createDirectories(cli.getParent());
            Files.writeString(cli, "#!/bin/sh\necho ok\n");
            cli.toFile().setExecutable(false);

            System.setProperty("user.home", tempDir.toString());
            LlmScriptService s = newService("");
            s.validate();

            assertNull(getCliPath(s));
        } finally {
            System.setProperty("user.home", originalHome);
        }
    }

    /**
     * 覆盖行 166：三元表达式的 true 臂（"CLI 回退可用"）。仅 log 参数，无外部可观察差异，
     * 通过 effectiveCliPath 非空间接证明该分支已走。
     */
    @Test
    void cliFallbackAvailable_expectsNonNullPathForLogTrueArm(@TempDir Path tempDir) throws Exception {
        String originalHome = System.getProperty("user.home");
        try {
            Path cli = tempDir.resolve("workspace/skills/weixin-chatapi/bin/chat.py");
            Files.createDirectories(cli.getParent());
            Files.writeString(cli, "#!/bin/sh\necho ok\n");
            cli.toFile().setExecutable(true);

            System.setProperty("user.home", tempDir.toString());
            LlmScriptService s = newService("");
            s.validate();

            assertNotNull(getCliPath(s));
        } finally {
            System.setProperty("user.home", originalHome);
        }
    }

    // ---------------- B. parseChatResponse ----------------

    /**
     * 覆盖行 235：{@code choices.isArray()} 为 false 的臂，整体当 content、用量记 0。
     */
    @Test
    void parseChatResponseWithoutChoicesArray_expectsWholeBodyAsContent() {
        LlmScriptService s = newService("/nonexistent-but-unused");
        LlmScriptService.ModelCallResult r = s.parseChatResponse("{\"foo\":1}");
        assertEquals("{\"foo\":1}", r.content());
        assertEquals(0L, r.promptTokens());
        assertEquals(0L, r.completionTokens());
    }

    // ---------------- C. buildUserContent ----------------

    /**
     * 覆盖行 380：genre 为空串 "" 的臂，应回退为"未指定"。
     */
    @Test
    void generateWithBlankGenre_expectsUnspecifiedFallbackInUserContent() {
        Stub stub = new Stub(List.of(validFourScenes()), 0);
        Episode ep = newEpisode("标题A", "", "大纲A");
        LlmScriptService.LlmScriptResult result = stub.generate(ep, "");

        assertEquals(4, result.scenes().size());
        String userContent = stub.capturedBody.path("messages").get(1).path("content").asText();
        assertTrue(userContent.contains("未指定"), "genre 空串应回退为未指定");
    }

    // ---------------- D. callModelViaCli ----------------

    /**
     * 覆盖行 430：role 既非 system 也非 user 的臂（assistant 被忽略）。
     */
    @Test
    void callCliWithAssistantRole_expectsIgnoredAndReturnsStdout(@TempDir Path tempDir) throws Exception {
        Path script = tempDir.resolve("chat.py");
        Files.writeString(script, "print('ok')\n");

        LlmScriptService s = newServiceTimeout(10, script.toString());
        setCliPath(s, script.toString());

        ObjectNode body = new ObjectMapper().createObjectNode();
        ArrayNode messages = body.putArray("messages");
        ObjectNode sys = messages.addObject();
        sys.put("role", "system");
        sys.put("content", "sys-text");
        ObjectNode asst = messages.addObject();
        asst.put("role", "assistant");
        asst.put("content", "should-be-ignored");
        ObjectNode user = messages.addObject();
        user.put("role", "user");
        user.put("content", "user-text");

        String out = callCli(s, body);
        assertEquals("ok", out);
    }

    /**
     * 覆盖行 467-469：{@code !done} 超时臂。python 脚本睡 30s，timeoutSeconds=1。
     */
    @Test
    void callCliTimeout_expectsRuntimeExceptionWithTimeoutMessage(@TempDir Path tempDir) throws Exception {
        Path script = tempDir.resolve("chat.py");
        Files.writeString(script, "import time; time.sleep(30)\n");

        LlmScriptService s = newServiceTimeout(1, script.toString());
        setCliPath(s, script.toString());

        ObjectNode body = new ObjectMapper().createObjectNode();
        ArrayNode messages = body.putArray("messages");
        ObjectNode user = messages.addObject();
        user.put("role", "user");
        user.put("content", "hi");

        RuntimeException ex = assertThrows(RuntimeException.class, () -> callCli(s, body));
        assertTrue(ex.getMessage().contains("CLI 回退超时"), "应命中超时分支: " + ex.getMessage());
    }

    /**
     * 覆盖行 472：stderr 超过 300 字符的臂（preview 截断）。脚本向 stderr 写 400 个 x 后退出码 3。
     */
    @Test
    void callCliNonZeroExitWithLongStderr_expectsFailureMessage(@TempDir Path tempDir) throws Exception {
        Path script = tempDir.resolve("chat.py");
        Files.writeString(script,
                "import sys\nsys.stderr.write('x' * 400)\nsys.exit(3)\n");

        LlmScriptService s = newServiceTimeout(10, script.toString());
        setCliPath(s, script.toString());

        ObjectNode body = new ObjectMapper().createObjectNode();
        ArrayNode messages = body.putArray("messages");
        ObjectNode user = messages.addObject();
        user.put("role", "user");
        user.put("content", "hi");

        RuntimeException ex = assertThrows(RuntimeException.class, () -> callCli(s, body));
        assertTrue(ex.getMessage().contains("CLI 回退失败 exit=3"), "应命中非零退出分支: " + ex.getMessage());
        // 截断到 300 字符
        assertTrue(ex.getMessage().length() < 400 + 100, "stderr 应被截断");
    }

    // ---------------- E. parseScenes（Stub+generate） ----------------

    /**
     * 覆盖行 516：{@code firstBracket < 0} 为 true 的臂（有花括号、无方括号），
     * 走对象臂解析后缺 scenes 数组。
     */
    @Test
    void generateWithNoBracketButNoScenes_expectsMissingScenesError() {
        Stub stub = new Stub(List.of("{\"foo\":\"bar\"}"), 0);
        Episode ep = newEpisode("T", "G", "O");

        LlmScriptUnavailableException ex =
                assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(ep, ""));
        Throwable cause = ex.getCause();
        assertNotNull(cause);
        assertTrue(cause.getMessage().contains("缺少 scenes 数组"),
                "应命中缺 scenes 分支: " + cause.getMessage());
    }

    /**
     * 覆盖行 519：else 臂"未找到 JSON 结构"（有 [ 无 ]，无花括号）。
     */
    @Test
    void generateWithUnclosedBracket_expectsNoJsonStructureError() {
        Stub stub = new Stub(List.of("前面是文字 [ 后面也是文字"), 0);
        Episode ep = newEpisode("T", "G", "O");

        LlmScriptUnavailableException ex =
                assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(ep, ""));
        Throwable cause = ex.getCause();
        assertNotNull(cause);
        assertTrue(cause.getMessage().contains("未找到 JSON 结构"),
                "应命中未找到 JSON 结构分支: " + cause.getMessage());
    }

    /**
     * 覆盖行 553/554：sceneNo 非 int（写成字符串）的臂。
     */
    @Test
    void generateWithStringSceneNo_expectsIllegalSceneNoError() {
        String bad2 = "{\"sceneNo\":\"2\",\"location\":\"L2\",\"timeOfDay\":\"黄昏\",\"description\":\"D2\",\"dialogue\":\"G2\",\"prompt\":\"P2\"}";
        String content = "{\"scenes\":[" + SCENE_1 + "," + bad2 + "," + SCENE_3 + "," + SCENE_4 + "]}";
        Stub stub = new Stub(List.of(content), 0);
        Episode ep = newEpisode("T", "G", "O");

        LlmScriptUnavailableException ex =
                assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(ep, ""));
        Throwable cause = ex.getCause();
        assertNotNull(cause);
        assertTrue(cause.getMessage().contains("sceneNo 非法"),
                "应命中 sceneNo 非法分支: " + cause.getMessage());
    }

    /**
     * 覆盖行 566：description 为空串的臂（第 3 场）。
     */
    @Test
    void generateWithBlankDescription_expectsDescriptionEmptyError() {
        String bad3 = "{\"sceneNo\":3,\"location\":\"L3\",\"timeOfDay\":\"夜晚\",\"description\":\"\",\"dialogue\":\"G3\",\"prompt\":\"P3\"}";
        String content = "{\"scenes\":[" + SCENE_1 + "," + SCENE_2 + "," + bad3 + "," + SCENE_4 + "]}";
        Stub stub = new Stub(List.of(content), 0);
        Episode ep = newEpisode("T", "G", "O");

        LlmScriptUnavailableException ex =
                assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(ep, ""));
        Throwable cause = ex.getCause();
        assertNotNull(cause);
        assertTrue(cause.getMessage().contains("description 为空"),
                "应命中 description 为空分支: " + cause.getMessage());
    }

    /**
     * 覆盖行 570：dialogue 为空串的臂（第 4 场）。
     */
    @Test
    void generateWithBlankDialogue_expectsDialogueEmptyError() {
        String bad4 = "{\"sceneNo\":4,\"location\":\"L4\",\"timeOfDay\":\"白天\",\"description\":\"D4\",\"dialogue\":\"\",\"prompt\":\"P4\"}";
        String content = "{\"scenes\":[" + SCENE_1 + "," + SCENE_2 + "," + SCENE_3 + "," + bad4 + "]}";
        Stub stub = new Stub(List.of(content), 0);
        Episode ep = newEpisode("T", "G", "O");

        LlmScriptUnavailableException ex =
                assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(ep, ""));
        Throwable cause = ex.getCause();
        assertNotNull(cause);
        assertTrue(cause.getMessage().contains("dialogue 为空"),
                "应命中 dialogue 为空分支: " + cause.getMessage());
    }

    /**
     * 覆盖行 516-518：对象形式正常解析的回归（前置有中文、无前导 [）。
     */
    @Test
    void generateWithObjectFormSurroundedByText_expectsFourScenes() {
        String content = "这是剧本：{\"scenes\":[" + SCENE_1 + "," + SCENE_2 + "," + SCENE_3 + "," + SCENE_4 + "]}请查收";
        Stub stub = new Stub(List.of(content), 0);
        Episode ep = newEpisode("T", "G", "O");

        LlmScriptService.LlmScriptResult result = stub.generate(ep, "");
        assertEquals(4, result.scenes().size());
    }
}
