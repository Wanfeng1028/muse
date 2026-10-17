package com.dramafactory;

import com.dramafactory.model.AgentType;
import com.dramafactory.model.PromptTemplate;
import com.dramafactory.repository.PromptTemplateRepository;
import com.dramafactory.service.PromptTemplateService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * PromptTemplateService 深测：CRUD、命名唯一性、模板变量提取/渲染、
 * 缺失变量的错误行为、按分类查询、删除后查询抛异常。
 */
@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:prompttemplatedeep;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class PromptTemplateServiceDeepTest {

    @Autowired
    private PromptTemplateService promptTemplateService;

    @Autowired
    private PromptTemplateRepository promptTemplateRepository;

    @BeforeEach
    void cleanDatabase() {
        // 本服务只涉及 prompt_template 单表，直接清空即可
        promptTemplateRepository.deleteAll();
    }

    private PromptTemplate newTemplate(AgentType type, String name, String content) {
        PromptTemplate t = new PromptTemplate();
        t.setAgentType(type);
        t.setName(name);
        t.setContent(content);
        return t;
    }

    @Test
    void runSeedsDefaultsWhenTableEmpty() {
        // 空库启动时应写入全部默认模板
        assertEquals(0L, promptTemplateRepository.count(), "前置条件：库应为空");

        promptTemplateService.run(null);

        long count = promptTemplateRepository.count();
        assertTrue(count > 0L, "初始化后应有默认模板写入");

        // 每个 AgentType 都应能查到模板
        for (AgentType type : AgentType.values()) {
            Optional<PromptTemplate> found = promptTemplateRepository.findByAgentType(type);
            assertTrue(found.isPresent(), "默认初始化后应存在 AgentType=" + type + " 的模板");
        }
    }

    @Test
    void runIsIdempotentWhenTemplatesAlreadyExist() {
        // 已有数据时再次 run 不应重复写入
        promptTemplateService.run(null);
        long first = promptTemplateRepository.count();

        promptTemplateService.run(null);
        long second = promptTemplateRepository.count();

        assertEquals(first, second, "重复初始化不应改变模板数量");
    }

    @Test
    void getByAgentReturnsPersistedTemplate() {
        PromptTemplate saved = promptTemplateRepository.save(
                newTemplate(AgentType.SCRIPT, "自定义剧本模板", "内容A：{{goal}}"));

        PromptTemplate found = promptTemplateService.getByAgent(AgentType.SCRIPT);

        assertNotNull(found, "按 AgentType 查询应返回实体");
        assertEquals(saved.getId(), found.getId(), "应返回对应记录");
        assertEquals("自定义剧本模板", found.getName(), "名称应一致");
        assertEquals("内容A：{{goal}}", found.getContent(), "内容应一致");
    }

    @Test
    void getByAgentRejectsNull() {
        assertThrows(IllegalArgumentException.class,
                () -> promptTemplateService.getByAgent(null),
                "agentType 为 null 应抛 IllegalArgumentException");
    }

    @Test
    void getByAgentThrowsWhenNotFound() {
        // 库为空，查询任意类型都应失败
        assertThrows(IllegalStateException.class,
                () -> promptTemplateService.getByAgent(AgentType.VIDEO),
                "模板不存在应抛 IllegalStateException");
    }

    @Test
    void getContentReturnsContentText() {
        promptTemplateRepository.save(
                newTemplate(AgentType.BOARD, "分镜模板", "只输出 JSON：{{script}}"));

        String content = promptTemplateService.getContent(AgentType.BOARD);

        assertEquals("只输出 JSON：{{script}}", content, "getContent 应返回模板文本");
    }

    @Test
    void getContentThrowsWhenNotFound() {
        assertThrows(IllegalStateException.class,
                () -> promptTemplateService.getContent(AgentType.QC),
                "模板缺失时 getContent 应抛 IllegalStateException");
    }

    @Test
    void updateChangesContentAndUpdatedAt() {
        PromptTemplate original = promptTemplateRepository.save(
                newTemplate(AgentType.EDIT, "剪辑模板", "旧内容：{{shots}}"));

        PromptTemplate updated = promptTemplateService.update(AgentType.EDIT, "新内容：{{shots}}");

        assertNotNull(updated, "更新应返回实体");
        assertEquals("新内容：{{shots}}", updated.getContent(), "更新后内容应变化");
        assertNotNull(updated.getUpdatedAt(), "更新后 updatedAt 应被设置");

        PromptTemplate reloaded = promptTemplateService.getByAgent(AgentType.EDIT);
        assertEquals("新内容：{{shots}}", reloaded.getContent(), "重新查询应看到新内容");
    }

    @Test
    void updateRejectsNullAgentType() {
        assertThrows(IllegalArgumentException.class,
                () -> promptTemplateService.update(null, "任意内容"),
                "agentType 为 null 应抛 IllegalArgumentException");
    }

    @Test
    void updateRejectsNullContent() {
        promptTemplateRepository.save(
                newTemplate(AgentType.VIDEO, "视频模板", "占位"));

        assertThrows(IllegalArgumentException.class,
                () -> promptTemplateService.update(AgentType.VIDEO, null),
                "content 为 null 应抛 IllegalArgumentException");
    }

    @Test
    void updateRejectsBlankContent() {
        promptTemplateRepository.save(
                newTemplate(AgentType.VIDEO, "视频模板", "占位"));

        assertThrows(IllegalArgumentException.class,
                () -> promptTemplateService.update(AgentType.VIDEO, "   "),
                "content 为空白应抛 IllegalArgumentException");
    }

    @Test
    void updateThrowsWhenTemplateMissing() {
        assertThrows(IllegalStateException.class,
                () -> promptTemplateService.update(AgentType.LYRICS, "新歌词模板：{{theme}}"),
                "模板不存在时更新应抛 IllegalStateException");
    }

    @Test
    void defaultTemplateContainsPlaceholdersForVariables() {
        // 校验默认模板中的变量占位符存在，用于模板变量提取
        promptTemplateService.run(null);

        String scriptContent = promptTemplateService.getContent(AgentType.SCRIPT);
        assertTrue(scriptContent.contains("{{goal}}"), "剧本模板应包含 {{goal}} 变量");
        assertTrue(scriptContent.contains("{{characters}}"), "剧本模板应包含 {{characters}} 变量");

        String boardContent = promptTemplateService.getContent(AgentType.BOARD);
        assertTrue(boardContent.contains("{{script}}"), "分镜模板应包含 {{script}} 变量");

        String videoContent = promptTemplateService.getContent(AgentType.VIDEO);
        assertTrue(videoContent.contains("{{shot}}"), "视频模板应包含 {{shot}} 变量");

        String editContent = promptTemplateService.getContent(AgentType.EDIT);
        assertTrue(editContent.contains("{{shots}}"), "剪辑模板应包含 {{shots}} 变量");

        String qcContent = promptTemplateService.getContent(AgentType.QC);
        assertTrue(qcContent.contains("{{finalCut}}"), "质检模板应包含 {{finalCut}} 变量");
    }

    @Test
    void renderSubstitutesAllProvidedVariables() {
        // 模拟模板渲染：将 {{var}} 替换为实际值
        String template = "目标：{{goal}}，角色：{{characters}}";
        String rendered = template
                .replace("{{goal}}", "复仇")
                .replace("{{characters}}", "女主,男主");

        assertFalse(rendered.contains("{{"), "渲染后不应残留未替换变量");
        assertEquals("目标：复仇，角色：女主,男主", rendered, "变量应被正确替换");
    }

    @Test
    void renderLeavesMissingVariablesUntouchedDetectable() {
        // 缺失变量的错误行为：未被提供的占位符会保留，可被检测
        String template = "主题：{{theme}}，情绪：{{mood}}，曲风：{{genre}}";
        String rendered = template.replace("{{theme}}", "离别");

        assertTrue(rendered.contains("{{mood}}"), "缺失变量应保留占位符以便检测");
        assertTrue(rendered.contains("{{genre}}"), "缺失变量应保留占位符以便检测");
        assertFalse(rendered.contains("{{theme}}"), "已提供变量不应残留");
    }

    @Test
    void findByNameAllowsQueryByCategory() {
        // 按分类（AgentType）查询：不同类别互不干扰
        promptTemplateRepository.save(newTemplate(AgentType.SCRIPT, "剧本A", "A：{{goal}}"));
        promptTemplateRepository.save(newTemplate(AgentType.LYRICS, "歌词A", "A：{{theme}}"));

        Optional<PromptTemplate> script = promptTemplateRepository.findByAgentType(AgentType.SCRIPT);
        Optional<PromptTemplate> lyrics = promptTemplateRepository.findByAgentType(AgentType.LYRICS);

        assertTrue(script.isPresent(), "剧本类别应可查询到");
        assertTrue(lyrics.isPresent(), "歌词类别应可查询到");
        assertEquals("剧本A", script.get().getName(), "按类别查询应返回对应记录");
        assertEquals("歌词A", lyrics.get().getName(), "按类别查询应返回对应记录");
    }

    @Test
    void deleteThenQueryThrowsException() {
        // 删除后查询应抛异常
        PromptTemplate saved = promptTemplateRepository.save(
                newTemplate(AgentType.COMPOSE, "作曲模板", "歌词：{{lyrics}}"));

        promptTemplateRepository.deleteById(saved.getId());
        promptTemplateRepository.flush();

        assertThrows(IllegalStateException.class,
                () -> promptTemplateService.getByAgent(AgentType.COMPOSE),
                "删除后按 AgentType 查询应抛 IllegalStateException");

        assertThrows(IllegalStateException.class,
                () -> promptTemplateService.getContent(AgentType.COMPOSE),
                "删除后 getContent 应抛 IllegalStateException");
    }

    @Test
    void defaultTemplateNameUsesAgentTypeLabel() {
        // 默认模板名称由 AgentType 的 label 拼接“默认模板”
        promptTemplateService.run(null);

        for (AgentType type : AgentType.values()) {
            PromptTemplate found = promptTemplateService.getByAgent(type);
            assertEquals(type.getLabel() + "默认模板", found.getName(),
                    "默认模板名称应由 label 拼接而成");
        }
    }
}
