package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.model.PromptTemplate;
import com.dramafactory.model.AgentType;
import com.dramafactory.service.PromptTemplateService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Agent 机队 API：展示各 Agent 的模型、降级策略与 Prompt 模板，并支持模板更新与视频通道查询。
 */
@RestController
@RequestMapping("/api/agents")
@Tag(name = "Agents", description = "Agent 信息、Prompt 模板更新与视频通道查询接口")
public class AgentController {

    private static final List<String> AVAILABLE_CHANNELS = List.of("mock", "qwen", "agnes");

    private final PromptTemplateService promptTemplateService;
    private final Environment environment;

    public AgentController(PromptTemplateService promptTemplateService, Environment environment) {
        this.promptTemplateService = promptTemplateService;
        this.environment = environment;
    }

    /**
     * 列出全部 5 个 Agent 的实时信息。
     *
     * @return Agent 信息列表
     */
    @GetMapping("")
    @Operation(summary = "查询全部 Agent 信息")
    public List<Records.AgentInfo> list() {
        List<Records.AgentInfo> result = new ArrayList<>();
        for (AgentType type : AgentType.values()) {
            result.add(toAgentInfo(type));
        }
        return result;
    }

    /**
     * 更新指定 Agent 的 Prompt 模板。
     *
     * @param type    Agent 类型字符串
     * @param body    请求体，含 content 字段
     * @return 更新后的 Agent 信息
     */
    @PutMapping("/{type}/template")
    @Operation(summary = "更新 Agent 的 Prompt 模板")
    @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "400", description = "type 非法或 content 为空时返回 400")
    public ResponseEntity<Records.AgentInfo> updateTemplate(@PathVariable("type") String type,
                                                            @RequestBody Map<String, String> body) {

        AgentType agentType = parseType(type);
        if (agentType == null) {
            return ResponseEntity.badRequest().build();
        }
        String content = body == null ? null : body.get("content");
        if (content == null || content.isBlank()) {
            return ResponseEntity.badRequest().build();
        }
        promptTemplateService.update(agentType, content);
        return ResponseEntity.ok(toAgentInfo(agentType));
    }

    /**
     * 查询当前视频通道与可选通道列表。
     *
     * @return 通道信息
     */
    @GetMapping("/channels")
    @Operation(summary = "查询视频通道信息")
    public Records.ChannelInfo channels() {
        String current = environment.getProperty("drama.video.provider", "mock");
        String note = "修改 settings.json 中 drama.video.provider 即可运行时切换；环境变量优先级更高。";
        return new Records.ChannelInfo(current, AVAILABLE_CHANNELS, note);
    }

    /**
     * 将 AgentType 转换为响应对象。
     *
     * @param type Agent 类型
     * @return Agent 信息
     */
    private Records.AgentInfo toAgentInfo(AgentType type) {
        PromptTemplate template = promptTemplateService.getByAgent(type);
        String templateName = template == null ? null : template.getName();
        java.time.LocalDateTime updatedAt = template == null ? null : template.getUpdatedAt();
        return new Records.AgentInfo(
                type.name(),
                type.getLabel(),
                templateName,
                updatedAt,
                modelFor(type),
                fallbackFor(type)
        );
    }

    /**
     * 读取指定 Agent 当前生效的模型/通道描述。
     *
     * @param type Agent 类型
     * @return 模型描述
     */
    private String modelFor(AgentType type) {
        return switch (type) {
            case SCRIPT -> environment.getProperty("drama.script.llm.model", "Deepseek-v4-flash");
            case BOARD -> environment.getProperty("drama.script-splitter.model", "Deepseek-v4-flash");
            case VIDEO -> "当前通道：" + environment.getProperty("drama.video.provider", "mock");
            case EDIT -> "ffmpeg（本地执行）";
            case QC -> Boolean.parseBoolean(environment.getProperty("harness.qc.manual-approval", "true"))
                    ? "人工终审" : "自动检查";
            case LYRICS -> environment.getProperty("drama.script.llm.model", "Deepseek-v4-flash");
            case COMPOSE -> "当前通道：" + environment.getProperty("drama.music.provider", "minimax");
        };
    }

    /**
     * 返回指定 Agent 的降级策略描述。
     *
     * @param type Agent 类型
     * @return 降级策略
     */
    private String fallbackFor(AgentType type) {
        return switch (type) {
            case SCRIPT -> "LLM 失败降级模板生成（ScriptService 内建）";
            case BOARD -> "无降级，失败抛错由 Run 重试";
            case VIDEO -> "Resilience4j 熔断 agnes + 失败重试";
            case EDIT -> "本地 ffmpeg，无降级";
            case QC -> "人工审批门兜底";
            case LYRICS -> "LLM 失败则作词步骤标记失败，可重试";
            case COMPOSE -> "作曲渠道失败可切换供应商重试";
        };
    }

    /**
     * 解析 Agent 类型字符串。
     *
     * @param type 类型字符串
     * @return AgentType，非法时返回 null
     */
    private AgentType parseType(String type) {
        if (type == null) {
            return null;
        }
        try {
            return AgentType.valueOf(type.trim().toUpperCase());
        } catch (IllegalArgumentException ex) {
            return null;
        }
    }
}
