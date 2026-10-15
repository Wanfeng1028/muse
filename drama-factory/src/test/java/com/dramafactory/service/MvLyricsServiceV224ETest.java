package com.dramafactory.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * 分支覆盖补充测试：MvLyricsService。
 *
 * 目标未覆盖分支（源码原文行号）：
 *  - 35 行 theme == null 臂
 *  - 36 行 mood != null && !mood.isBlank() 的 null / blank 臂
 *  - 39 行 style != null && !style.isBlank() 的 null / blank 臂
 *  - 78 行 lyrics == null || lyrics.isBlank() 的 isBlank -> true 臂
 *  - 111 行 content == null 臂
 *  - 117 行 firstNewline >= 0 的 true / false 臂
 *  - 121 行 lastFence >= 0 的 true / false 臂
 *
 * 纯 JUnit5 + Mockito，无 Spring 上下文。@TempDir 保留以遵守"文件操作一律用 @TempDir"约定
 * （本类实际不做文件操作，字段仅为合规占位，不会被读写）。
 */
class MvLyricsServiceV224ETest {

    /** 合规占位：本类无文件操作，保留 @TempDir 以遵守约束 3。 */
    @TempDir
    java.nio.file.Path tempDir;

    private ObjectMapper objectMapper;
    private LlmScriptService llm;

    private static final String VALID_JSON =
            "{\"title\":\"歌\",\"sections\":[{\"name\":\"verse1\",\"lyrics\":\"第一段歌词\",\"mood\":\"情绪\",\"estSeconds\":20}]}";

    @BeforeEach
    void setUp() {
        objectMapper = new ObjectMapper();
        llm = mock(LlmScriptService.class);
        // 大多数用例会走到；个别用例（如 stripFence 反射直接调用）走不到，用 lenient 包裹。
        lenient().when(llm.callModelWithUsage(any()))
                .thenReturn(new LlmScriptService.ModelCallResult(VALID_JSON, 1L, 1L));
    }

    private String captureUserPrompt(String theme, String mood, String style) {
        MvLyricsService service = new MvLyricsService(objectMapper, llm);
        service.generate(theme, mood, style);
        ArgumentCaptor<ObjectNode> captor = ArgumentCaptor.forClass(ObjectNode.class);
        org.mockito.Mockito.verify(llm).callModelWithUsage(captor.capture());
        ObjectNode body = captor.getValue();
        return body.get("messages").get(1).get("content").asText();
    }

    // ------------------------------------------------------------------
    // 1. 第 35 行 theme == null 臂
    // ------------------------------------------------------------------
    @Test
    void generate_themeNull_userPromptHasEmptyThemeLine() {
        String prompt = captureUserPrompt(null, "欢快", "流行");
        assertTrue(prompt.contains("主题：\n"),
                "theme==null 时应输出空主题文本，主题行后紧跟换行；实际 prompt=" + prompt);
        assertTrue(prompt.contains("情绪：欢快\n"), "mood 非空时应包含情绪行");
        assertTrue(prompt.contains("曲风：流行\n"), "style 非空时应包含曲风行");
    }

    // ------------------------------------------------------------------
    // 2. 第 36 行 mood != null && !mood.isBlank() 的 null / blank 臂
    // ------------------------------------------------------------------
    @Test
    void generate_moodNull_userPromptOmitsMoodLine() {
        String prompt = captureUserPrompt("t", null, "流行");
        assertFalse(prompt.contains("情绪："), "mood==null 时不应包含情绪行；实际 prompt=" + prompt);
        assertTrue(prompt.contains("主题：t\n"), "主题行应正常输出");
        assertTrue(prompt.contains("曲风：流行\n"), "曲风行应正常输出");
    }

    @Test
    void generate_moodBlank_userPromptOmitsMoodLine() {
        String prompt = captureUserPrompt("t", " ", "流行");
        assertFalse(prompt.contains("情绪："), "mood 为空白时不应包含情绪行；实际 prompt=" + prompt);
        assertTrue(prompt.contains("主题：t\n"), "主题行应正常输出");
        assertTrue(prompt.contains("曲风：流行\n"), "曲风行应正常输出");
    }

    // ------------------------------------------------------------------
    // 3. 第 39 行 style != null && !style.isBlank() 的 null / blank 臂
    // ------------------------------------------------------------------
    @Test
    void generate_styleNull_userPromptOmitsStyleLine() {
        String prompt = captureUserPrompt("t", "欢快", null);
        assertFalse(prompt.contains("曲风："), "style==null 时不应包含曲风行；实际 prompt=" + prompt);
        assertTrue(prompt.contains("主题：t\n"), "主题行应正常输出");
        assertTrue(prompt.contains("情绪：欢快\n"), "情绪行应正常输出");
    }

    @Test
    void generate_styleEmpty_userPromptOmitsStyleLine() {
        String prompt = captureUserPrompt("t", "欢快", "");
        assertFalse(prompt.contains("曲风："), "style 为空串时不应包含曲风行；实际 prompt=" + prompt);
        assertTrue(prompt.contains("主题：t\n"), "主题行应正常输出");
        assertTrue(prompt.contains("情绪：欢快\n"), "情绪行应正常输出");
    }

    // ------------------------------------------------------------------
    // 4. 第 78 行 lyrics == null || lyrics.isBlank() 的 isBlank -> true 臂
    //    （lyrics 从 path().asText("") 取，永远不会为 null，故触发的是 isBlank 臂）
    // ------------------------------------------------------------------
    @Test
    void generate_sectionLyricsBlank_throwsIllegalState() {
        String json = "{\"title\":\"歌\",\"sections\":[{\"name\":\"verse1\",\"lyrics\":\"\",\"mood\":\"\",\"estSeconds\":20}]}";
        when(llm.callModelWithUsage(any()))
                .thenReturn(new LlmScriptService.ModelCallResult(json, 1L, 1L));

        MvLyricsService service = new MvLyricsService(objectMapper, llm);
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> service.generate("t", "m", "s"));
        assertEquals("作词结果解析失败", ex.getMessage());
    }

    // ------------------------------------------------------------------
    // 5. stripFence 私有方法反射调用
    // ------------------------------------------------------------------
    private String invokeStripFence(MvLyricsService service, String content) throws Exception {
        Method m = MvLyricsService.class.getDeclaredMethod("stripFence", String.class);
        m.setAccessible(true);
        return (String) m.invoke(service, content);
    }

    /**
     * (a) content = "```json\n{\"a\":1}\n```"
     * 推导（源码 111-125 行）：
     *  - 111 行：content != null，跳过
     *  - 113 行：trimmed = "```json\n{\"a\":1}\n```"
     *  - 114 行：startsWith("```") -> true
     *  - 116 行：firstNewline = indexOf('\n') = 7 -> >= 0
     *  - 117 行：trimmed = trimmed.substring(8) = "{\"a\":1}\n```"
     *  - 120 行：lastFence = lastIndexOf("```") = 9 -> >= 0
     *  - 121 行：trimmed = substring(0, 9) = "{\"a\":1}\n"
     *  - 125 行：return trimmed.trim() = "{\"a\":1}"
     */
    @Test
    void stripFence_fencedWithNewline_truncatesBothEnds() throws Exception {
        MvLyricsService service = new MvLyricsService(objectMapper, llm);
        String result = invokeStripFence(service, "```json\n{\"a\":1}\n```");
        assertEquals("{\"a\":1}", result);
    }

    /**
     * (b) content = "```{\"a\":1}"（fence 后无换行）
     * 逐行推导（源码 111-125 行）：
     *  - 111 行：content != null，跳过
     *  - 113 行：trimmed = "```{\"a\":1}"
     *  - 114 行：startsWith("```") -> true
     *  - 116 行：firstNewline = indexOf('\n') = -1 -> < 0，跳过 117 行截首行
     *  - 120 行：lastFence = lastIndexOf("```") = 0 -> >= 0
     *  - 121 行：trimmed = substring(0, 0) = ""
     *  - 125 行：return "".trim() = ""
     *  期望为 ""，与"fence 头保留"的直觉不符，但按源码即为空串。
     */
    @Test
    void stripFence_fenceWithoutNewline_returnsEmptyPerSource() throws Exception {
        MvLyricsService service = new MvLyricsService(objectMapper, llm);
        String result = invokeStripFence(service, "```{\"a\":1}");
        assertEquals("", result);
    }

    /**
     * (c) content = null
     *  - 111 行：content == null -> return ""
     */
    @Test
    void stripFence_nullContent_returnsEmpty() throws Exception {
        MvLyricsService service = new MvLyricsService(objectMapper, llm);
        String result = invokeStripFence(service, null);
        assertEquals("", result);
    }

    // ------------------------------------------------------------------
    // 诚实跳过清单
    // ------------------------------------------------------------------
    // 1) 第 35 行 "theme != null" 臂：已被本类 generate_themeNull_* 之外的所有用例隐式覆盖
    //    （任何非 null theme 用例），且为既有覆盖，无需专门新增。
    // 2) 第 36/39 行 if 的 true 臂：已由既有测试覆盖，本轮只补 false 臂（null / blank）。
    // 3) 第 78 行 "lyrics == null" 臂：lyrics 由 n.path("lyrics").asText("") 得到，Jackson 的
    //    asText(default) 在缺失或 null 节点时返回 ""，永不为 null；因此 "== null" 分支在真实
    //    执行路径上不可达，属编译器保留的死分支，按约束 11（无业务意义硬造分支不许写）跳过。
    // 4) 第 114 行 startsWith("```") 的 false 臂：已由既有测试覆盖（普通 JSON 输入），本轮不重复。
}
