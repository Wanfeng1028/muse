package com.dramafactory;

import com.dramafactory.controller.AgentController;
import com.dramafactory.dto.Records;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.PromptTemplate;
import com.dramafactory.service.PromptTemplateService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class AgentControllerDeepTest {

    @Autowired
    private AgentController agentController;

    @Autowired
    private PromptTemplateService promptTemplateService;

    @Autowired
    private Environment environment;

    @Test
    void list_returnsAllAgentTypesInEnumOrder() {
        // given: 上下文已启动，控制器就绪
        int expectedSize = AgentType.values().length;

        // when: 调用 list 拉取全部 Agent 信息
        List<Records.AgentInfo> result = agentController.list();

        // then: 数量与枚举一致，且每一项 agentType 字段能被 AgentType 解析
        assertEquals(expectedSize, result.size(), "返回数量必须等于 AgentType 枚举数量");
        for (Records.AgentInfo info : result) {
            assertNotNull(info.type(), "agentType 不能为空");
            assertNotNull(AgentType.valueOf(info.type()), "agentType 必须是合法枚举名");
        }
        assertEquals(AgentType.SCRIPT.name(), result.get(0).type(), "顺序必须与枚举声明顺序一致");
        assertEquals(AgentType.COMPOSE.name(), result.get(result.size() - 1).type(), "最后一项必须是 COMPOSE");
    }

    @Test
    void list_returnsNonNullLabelAndModelForEveryAgent() {
        // given: 上下文就绪
        // when: 拉取列表
        List<Records.AgentInfo> result = agentController.list();

        // then: 每个 Agent 的 label 与 model 均非空非空白
        assertFalse(result.isEmpty(), "列表不能为空");
        for (Records.AgentInfo info : result) {
            assertNotNull(info.label(), info.type() + " 的 label 不能为空");
            assertFalse(info.label().isBlank(), info.type() + " 的 label 不能为空白");
            assertNotNull(info.model(), info.type() + " 的 model 不能为空");
            assertFalse(info.model().isBlank(), info.type() + " 的 model 不能为空白");
        }
    }

    @Test
    void list_reflectsQcManualApprovalEnvironmentProperty() {
        // given: 读取当前环境属性，作为期望值的来源
        boolean manualApproval = Boolean.parseBoolean(
                environment.getProperty("harness.qc.manual-approval", "true"));
        String expectedQcModel = manualApproval ? "人工终审" : "自动检查";

        // when: 拉取列表并定位 QC
        List<Records.AgentInfo> result = agentController.list();
        Records.AgentInfo qcInfo = result.stream()
                .filter(i -> AgentType.QC.name().equals(i.type()))
                .findFirst()
                .orElseThrow();

        // then: QC 的 model 必须与配置一致
        assertEquals(expectedQcModel, qcInfo.model(), "QC model 必须跟随 harness.qc.manual-approval");
        assertEquals("人工审批门兜底", qcInfo.fallback(), "QC fallback 必须是人工审批门兜底");
    }

    @Test
    void list_videoAgentModelContainsCurrentProvider() {
        // given: 读取当前视频通道配置
        String provider = environment.getProperty("drama.video.provider", "mock");
        String expectedModel = "当前通道：" + provider;

        // when: 拉取列表并定位 VIDEO
        List<Records.AgentInfo> result = agentController.list();
        Records.AgentInfo videoInfo = result.stream()
                .filter(i -> AgentType.VIDEO.name().equals(i.type()))
                .findFirst()
                .orElseThrow();

        // then: VIDEO 的 model 拼接了当前通道，fallback 固定
        assertEquals(expectedModel, videoInfo.model(), "VIDEO model 必须拼接当前通道");
        assertEquals("Resilience4j 熔断 agnes + 失败重试", videoInfo.fallback(), "VIDEO fallback 固定值校验");
    }

    @Test
    void updateTemplate_withValidTypeAndContent_persistsAndReturnsUpdatedInfo() {
        // given: 合法的 Agent 类型与一段唯一内容
        String uniqueContent = "deep-test-" + System.nanoTime() + "-content";
        Map<String, String> body = new HashMap<>();
        body.put("content", uniqueContent);

        // when: 调用 updateTemplate
        ResponseEntity<Records.AgentInfo> response =
                agentController.updateTemplate(AgentType.SCRIPT.name().toLowerCase(), body);

        // then: 返回 200，且返回体 agentType 正确，并且服务端已持久化该内容
        assertEquals(HttpStatus.OK, response.getStatusCode(), "合法更新必须返回 200");
        Records.AgentInfo info = response.getBody();
        assertNotNull(info, "返回体不能为空");
        assertEquals(AgentType.SCRIPT.name(), info.type(), "返回的 agentType 必须是 SCRIPT");
        PromptTemplate persisted = promptTemplateService.getByAgent(AgentType.SCRIPT);
        assertNotNull(persisted, "更新后必须能查到模板");
        assertEquals(uniqueContent, persisted.getContent(), "持久化内容必须与请求一致");
    }

    @Test
    void updateTemplate_isIdempotent_whenCalledTwiceWithSameContent() {
        // given: 同一份内容，先更新一次
        String sameContent = "idempotent-" + System.nanoTime();
        Map<String, String> body = new HashMap<>();
        body.put("content", sameContent);
        agentController.updateTemplate(AgentType.BOARD.name(), body);

        // when: 用完全相同的内容再更新一次
        ResponseEntity<Records.AgentInfo> second =
                agentController.updateTemplate(AgentType.BOARD.name(), body);

        // then: 状态码仍为 200，持久化内容不变，updatedAt 非空
        assertEquals(HttpStatus.OK, second.getStatusCode(), "重复更新仍应返回 200");
        PromptTemplate after = promptTemplateService.getByAgent(AgentType.BOARD);
        assertNotNull(after, "模板仍必须存在");
        assertEquals(sameContent, after.getContent(), "幂等更新后内容必须保持一致");
        assertNotNull(after.getUpdatedAt(), "updatedAt 必须被刷新");
    }

    @Test
    void updateTemplate_withIllegalType_returnsBadRequestAndDoesNotPersist() {
        // given: 一个不存在的类型名
        Map<String, String> body = new HashMap<>();
        body.put("content", "whatever-content");
        PromptTemplate before = promptTemplateService.getByAgent(AgentType.EDIT);

        // when: 用非法类型调用
        ResponseEntity<Records.AgentInfo> response =
                agentController.updateTemplate("NOT_A_REAL_TYPE", body);

        // then: 400，且返回体为空，EDIT 的模板内容未被这次非法调用改动
        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode(), "非法类型必须 400");
        assertNull(response.getBody(), "非法请求返回体必须为空");
        PromptTemplate after = promptTemplateService.getByAgent(AgentType.EDIT);
        if (before == null) {
            assertNull(after, "非法调用不应创建 EDIT 模板");
        } else {
            assertEquals(before.getContent(), after.getContent(), "非法调用不应改动 EDIT 内容");
        }
    }

    @Test
    void updateTemplate_withNullBody_returnsBadRequest() {
        // given: body 为 null
        // when: 调用 updateTemplate
        ResponseEntity<Records.AgentInfo> response =
                agentController.updateTemplate(AgentType.QC.name(), null);

        // then: 400 且无 body
        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode(), "null body 必须 400");
        assertNull(response.getBody(), "null body 请求返回体必须为空");
    }

    @Test
    void updateTemplate_withBlankContent_returnsBadRequest() {
        // given: content 是空白字符串
        Map<String, String> body = new HashMap<>();
        body.put("content", "   ");

        // when: 调用 updateTemplate
        ResponseEntity<Records.AgentInfo> response =
                agentController.updateTemplate(AgentType.LYRICS.name(), body);

        // then: 400，并且 LYRICS 的模板内容不是这段空白
        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode(), "空白 content 必须 400");
        PromptTemplate after = promptTemplateService.getByAgent(AgentType.LYRICS);
        if (after != null) {
            assertFalse("   ".equals(after.getContent()), "空白内容不得写入模板");
        } else {
            assertNull(after, "空白 content 不应创建模板");
        }
    }

    @Test
    void updateTemplate_withWhitespaceAndLowercaseType_isAccepted() {
        // given: 带前后空格且小写的类型字符串
        Map<String, String> body = new HashMap<>();
        String content = "trim-test-" + System.nanoTime();
        body.put("content", content);

        // when: 调用 updateTemplate
        ResponseEntity<Records.AgentInfo> response =
                agentController.updateTemplate("  compose  ", body);

        // then: 200，并且返回的 agentType 是 COMPOSE，内容已写入
        assertEquals(HttpStatus.OK, response.getStatusCode(), "带空格小写类型必须被规范化接受");
        assertNotNull(response.getBody(), "返回体不能为空");
        assertEquals(AgentType.COMPOSE.name(), response.getBody().type(), "必须解析为 COMPOSE");
        PromptTemplate persisted = promptTemplateService.getByAgent(AgentType.COMPOSE);
        assertNotNull(persisted, "COMPOSE 模板必须存在");
        assertEquals(content, persisted.getContent(), "内容必须已写入");
    }

    @Test
    void updateTemplate_withVeryLargeContent_isPersistedIntact() {
        // given: 一个 200000 字符的超大 payload
        int size = 200_000;
        StringBuilder sb = new StringBuilder(size);
        for (int i = 0; i < size; i++) {
            sb.append((char) ('a' + (i % 26)));
        }
        String huge = sb.toString();
        Map<String, String> body = new HashMap<>();
        body.put("content", huge);

        // when: 更新 COMPOSE 模板
        ResponseEntity<Records.AgentInfo> response =
                agentController.updateTemplate(AgentType.COMPOSE.name(), body);

        // then: 200，且写入的字符串长度和内容完整一致
        assertEquals(HttpStatus.OK, response.getStatusCode(), "超大 payload 必须被接受");
        PromptTemplate persisted = promptTemplateService.getByAgent(AgentType.COMPOSE);
        assertNotNull(persisted, "超大 payload 更新后模板必须存在");
        assertEquals(size, persisted.getContent().length(), "内容长度必须与请求一致");
        assertEquals(huge, persisted.getContent(), "内容必须逐字符一致");
    }

    @Test
    void updateTemplate_twoThreadsUpdatingDifferentAgents_doNotInterfere() throws Exception {
        // given: 两个线程分别更新不同 Agent
        String scriptContent = "concurrent-script-" + System.nanoTime();
        String qcContent = "concurrent-qc-" + System.nanoTime();
        Map<String, String> scriptBody = new HashMap<>();
        scriptBody.put("content", scriptContent);
        Map<String, String> qcBody = new HashMap<>();
        qcBody.put("content", qcContent);

        // when: 并发执行两个更新
        Thread t1 = new Thread(() ->
                agentController.updateTemplate(AgentType.SCRIPT.name(), scriptBody));
        Thread t2 = new Thread(() ->
                agentController.updateTemplate(AgentType.QC.name(), qcBody));
        t1.start();
        t2.start();
        t1.join();
        t2.join();

        // then: 两个 Agent 的模板各自被正确写入，互不覆盖
        PromptTemplate scriptAfter = promptTemplateService.getByAgent(AgentType.SCRIPT);
        PromptTemplate qcAfter = promptTemplateService.getByAgent(AgentType.QC);
        assertNotNull(scriptAfter, "SCRIPT 模板必须存在");
        assertNotNull(qcAfter, "QC 模板必须存在");
        assertEquals(scriptContent, scriptAfter.getContent(), "SCRIPT 内容必须为 t1 写入值");
        assertEquals(qcContent, qcAfter.getContent(), "QC 内容必须为 t2 写入值");
    }

    @Test
    void updateTemplate_twoThreadsUpdatingSameAgent_lastWriteWinsAndContentIsOneOfTheTwo() throws Exception {
        // given: 两个线程对同一 Agent 写入不同内容
        String contentA = "same-agent-A-" + System.nanoTime();
        String contentB = "same-agent-B-" + System.nanoTime();
        Map<String, String> bodyA = new HashMap<>();
        bodyA.put("content", contentA);
        Map<String, String> bodyB = new HashMap<>();
        bodyB.put("content", contentB);

        // when: 并发写入同一 Agent
        Thread t1 = new Thread(() ->
                agentController.updateTemplate(AgentType.VIDEO.name(), bodyA));
        Thread t2 = new Thread(() ->
                agentController.updateTemplate(AgentType.VIDEO.name(), bodyB));
        t1.start();
        t2.start();
        t1.join();
        t2.join();

        // then: 最终内容必须是两者之一（数据未被写坏），且模板仍可读
        PromptTemplate after = promptTemplateService.getByAgent(AgentType.VIDEO);
        assertNotNull(after, "并发写入后模板必须存在");
        String finalContent = after.getContent();
        assertTrue(contentA.equals(finalContent) || contentB.equals(finalContent),
                "最终内容必须是两个写入值之一，不能出现混合/损坏数据");
        assertNotNull(after.getUpdatedAt(), "并发写入后 updatedAt 必须非空");
    }

    @Test
    void updateTemplate_whenServiceThrows_propagatesAndDoesNotReturnOk() {
        // given: 用一个会抛异常的 PromptTemplateService 构造控制器
        PromptTemplateService throwingService = new PromptTemplateService(null) {
            @Override
            public PromptTemplate getByAgent(AgentType type) {
                return null;
            }

            @Override
            public PromptTemplate update(AgentType type, String content) {
                throw new IllegalStateException("injected-failure");
            }
        };
        AgentController failingController = new AgentController(throwingService, environment);
        Map<String, String> body = new HashMap<>();
        body.put("content", "will-trigger-failure");

        // when / then: 调用必须把异常抛出来，不能吞掉后假装 200
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> failingController.updateTemplate(AgentType.EDIT.name(), body),
                "依赖抛异常时必须向上传播");
        assertEquals("injected-failure", ex.getMessage(), "异常消息必须与注入值一致");
    }

    @Test
    void channels_returnsCurrentProviderAndAvailableListAndNote() {
        // given: 读取期望的当前通道
        String expectedCurrent = environment.getProperty("drama.video.provider", "mock");

        // when: 调用 channels
        Records.ChannelInfo info = agentController.channels();

        // then: current 与配置一致，可选通道包含 mock/qwen/agnes，note 非空
        assertNotNull(info, "通道信息不能为空");
        assertEquals(expectedCurrent, info.current(), "current 必须跟随配置");
        List<String> available = info.available();
        assertNotNull(available, "可选通道列表不能为空");
        assertTrue(available.contains("mock"), "可选通道必须包含 mock");
        assertTrue(available.contains("qwen"), "可选通道必须包含 qwen");
        assertTrue(available.contains("agnes"), "可选通道必须包含 agnes");
        assertNotNull(info.note(), "note 不能为空");
        assertFalse(info.note().isBlank(), "note 不能为空白");
    }

    @Test
    void channels_isStableAcrossRepeatedCalls() {
        // given: 连续两次调用
        // when: 第一次与第二次调用
        Records.ChannelInfo first = agentController.channels();
        Records.ChannelInfo second = agentController.channels();

        // then: 两次结果的 current / available / note 必须一致
        assertNotNull(first, "第一次返回不能为空");
        assertNotNull(second, "第二次返回不能为空");
        assertEquals(first.current(), second.current(), "current 在重复调用间必须稳定");
        assertEquals(first.available(), second.available(), "available 在重复调用间必须稳定");
        assertEquals(first.note(), second.note(), "note 在重复调用间必须稳定");
    }

    @Test
    void list_includesUpdatedAtFromTemplateWhenPresent() {
        // given: 先给 EDIT 写一个模板，确保其有 updatedAt
        String content = "updated-at-test-" + System.nanoTime();
        Map<String, String> body = new HashMap<>();
        body.put("content", content);
        agentController.updateTemplate(AgentType.EDIT.name(), body);
        PromptTemplate persisted = promptTemplateService.getByAgent(AgentType.EDIT);
        assertNotNull(persisted, "EDIT 模板必须已存在");
        LocalDateTime expectedUpdatedAt = persisted.getUpdatedAt();

        // when: 拉取列表并定位 EDIT
        List<Records.AgentInfo> result = agentController.list();
        Records.AgentInfo editInfo = result.stream()
                .filter(i -> AgentType.EDIT.name().equals(i.type()))
                .findFirst()
                .orElseThrow();

        // then: 列表中的 updatedAt 必须与持久化模板一致
        assertNotNull(editInfo.templateUpdatedAt(), "EDIT 的 updatedAt 不能为空");
        assertEquals(expectedUpdatedAt, editInfo.templateUpdatedAt(), "updatedAt 必须来自模板");
    }

    @Test
    void list_scriptAndLyricsUseSameLlmModelProperty() {
        // given: 读取 SCRIPT/LYRICS 共用的 LLM 模型属性
        String expectedModel = environment.getProperty("drama.script.llm.model", "Deepseek-v4-flash");

        // when: 拉取列表并定位 SCRIPT 与 LYRICS
        List<Records.AgentInfo> result = agentController.list();
        Records.AgentInfo scriptInfo = result.stream()
                .filter(i -> AgentType.SCRIPT.name().equals(i.type()))
                .findFirst()
                .orElseThrow();
        Records.AgentInfo lyricsInfo = result.stream()
                .filter(i -> AgentType.LYRICS.name().equals(i.type()))
                .findFirst()
                .orElseThrow();

        // then: 二者 model 都等于同一属性值
        assertEquals(expectedModel, scriptInfo.model(), "SCRIPT model 必须来自 drama.script.llm.model");
        assertEquals(expectedModel, lyricsInfo.model(), "LYRICS model 必须来自 drama.script.llm.model");
    }

    @Test
    void list_composeAgentModelContainsMusicProvider() {
        // given: 读取作曲通道配置
        String musicProvider = environment.getProperty("drama.music.provider", "minimax");
        String expectedModel = "当前通道：" + musicProvider;

        // when: 拉取列表并定位 COMPOSE
        List<Records.AgentInfo> result = agentController.list();
        Records.AgentInfo composeInfo = result.stream()
                .filter(i -> AgentType.COMPOSE.name().equals(i.type()))
                .findFirst()
                .orElseThrow();

        // then: COMPOSE 的 model 拼接了当前作曲通道，fallback 固定
        assertEquals(expectedModel, composeInfo.model(), "COMPOSE model 必须拼接当前作曲通道");
        assertEquals("作曲渠道失败可切换供应商重试", composeInfo.fallback(), "COMPOSE fallback 固定值校验");
    }

    @Test
    void list_boardAndEditAgentHaveFixedFallbacks() {
        // given: 固定 fallback 的两个 Agent
        // when: 拉取列表
        List<Records.AgentInfo> result = agentController.list();
        Records.AgentInfo boardInfo = result.stream()
                .filter(i -> AgentType.BOARD.name().equals(i.type()))
                .findFirst()
                .orElseThrow();
        Records.AgentInfo editInfo = result.stream()
                .filter(i -> AgentType.EDIT.name().equals(i.type()))
                .findFirst()
                .orElseThrow();

        // then: BOARD/EDIT 的 fallback 与源码常量一致
        assertEquals("无降级，失败抛错由 Run 重试", boardInfo.fallback(), "BOARD fallback 固定值校验");
        assertEquals("本地 ffmpeg，无降级", editInfo.fallback(), "EDIT fallback 固定值校验");
        assertEquals("ffmpeg（本地执行）", editInfo.model(), "EDIT model 固定为 ffmpeg 描述");
    }
}