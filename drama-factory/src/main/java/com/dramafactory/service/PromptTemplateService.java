package com.dramafactory.service;

import com.dramafactory.model.AgentType;
import com.dramafactory.model.PromptTemplate;
import com.dramafactory.repository.PromptTemplateRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.EnumMap;
import java.util.Map;
import java.util.Optional;

/**
 * Prompt 模板服务。
 * 启动时补种缺失的默认模板，已有模板保持不动；提供按 AgentType 查询与更新能力。
 * 更新后的模板仅对之后新建的 Run 生效（已开始的 Run 在规划阶段即固化模板内容）。
 */
@Service
public class PromptTemplateService implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(PromptTemplateService.class);

    private final PromptTemplateRepository promptTemplateRepository;

    public PromptTemplateService(PromptTemplateRepository promptTemplateRepository) {
        this.promptTemplateRepository = promptTemplateRepository;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        int seeded = 0;
        Map<AgentType, String> defaults = defaultTemplates();
        for (Map.Entry<AgentType, String> e : defaults.entrySet()) {
            Optional<PromptTemplate> existing = promptTemplateRepository.findByAgentType(e.getKey());
            if (existing.isPresent()) {
                continue;
            }
            PromptTemplate t = new PromptTemplate();
            t.setAgentType(e.getKey());
            t.setName(e.getKey().getLabel() + "默认模板");
            t.setContent(e.getValue());
            t.setUpdatedAt(LocalDateTime.now());
            promptTemplateRepository.save(t);
            seeded++;
        }
        if (seeded > 0) {
            log.info("已补种 {} 条缺失的默认 Prompt 模板", seeded);
        } else {
            log.info("所有默认 Prompt 模板已存在，无需补种");
        }
    }

    /**
     * 按 AgentType 获取模板。找不到时抛出明确异常，避免 NPE 穿透。
     */
    @Transactional(readOnly = true)
    public PromptTemplate getByAgent(AgentType agentType) {
        if (agentType == null) {
            throw new IllegalArgumentException("agentType 不能为空");
        }
        return promptTemplateRepository.findByAgentType(agentType)
                .orElseThrow(() -> new IllegalStateException("未找到 AgentType=" + agentType + " 的 Prompt 模板"));
    }

    /**
     * 获取模板内容文本；找不到时抛出明确异常。
     */
    @Transactional(readOnly = true)
    public String getContent(AgentType agentType) {
        return getByAgent(agentType).getContent();
    }

    /**
     * 更新指定 AgentType 的模板内容，仅对之后新建的 Run 生效。
     */
    @Transactional
    public PromptTemplate update(AgentType agentType, String content) {
        if (agentType == null) {
            throw new IllegalArgumentException("agentType 不能为空");
        }
        if (content == null || content.isBlank()) {
            throw new IllegalArgumentException("模板内容不能为空");
        }
        PromptTemplate t = getByAgent(agentType);
        t.setContent(content);
        t.setUpdatedAt(LocalDateTime.now());
        return promptTemplateRepository.save(t);
    }

    private Map<AgentType, String> defaultTemplates() {
        Map<AgentType, String> map = new EnumMap<>(AgentType.class);

        map.put(AgentType.SCRIPT, """
                你是资深短剧编剧。根据用户给出的目标与角色设定，产出一份可直接拍摄的短剧剧本。
                要求：
                1) 先给出分集大纲（每集一句核心冲突）；
                2) 每集拆分为 4 场戏，每场戏包含：场景地点、出场角色、动作描述、关键台词；
                3) 全剧总集数不超过 6 集，若目标要求的集数超过 6，则截断为 6 集并在开头注明“已按上限截断为 6 集”；
                4) 输出必须结构清晰，先大纲后分场，禁止输出与剧本无关的寒暄。
                目标：{{goal}}
                角色：{{characters}}
                """);

        map.put(AgentType.BOARD, """
                你是短剧分镜师，只输出 JSON 数组，不要输出任何解释文字。
                数组元素字段：shotNo（从 1 递增的整数）、shotSize（景别：远景/全景/中景/近景/特写）、
                cameraMove（运镜，如 推/拉/摇/移/固定）、durationSec（整数秒）、
                description（中文画面描述）、dialogue（该镜头台词，可为空字符串）、
                videoPrompt（英文 cinematic 提示词，须包含 16:9 画幅描述）。
                约束：数组元素个数为 2 到 8 个之间；videoPrompt 必须是英文；不要输出 Markdown 代码块标记。
                剧本内容：{{script}}
                """);

        map.put(AgentType.VIDEO, """
                你是短剧视频生成提示词工程师。基于分镜信息生成视频模型提示词。
                要求：
                1) 强调 cinematic 短剧质感（真实光影、浅景深、电影级调色）；
                2) 画幅固定 16:9；
                3) 时长 3 到 8 秒；
                4) 画面中避免出现任何文字、字幕、水印；
                5) 只输出英文提示词文本，不要输出解释。
                分镜信息：{{shot}}
                """);

        map.put(AgentType.EDIT, """
                你是短剧剪辑师，负责将多个分镜片段拼接为成片。
                要求：
                1) 使用 ffmpeg 按 shotNo 顺序拼接；
                2) 转场克制，仅在必要处使用，默认硬切；
                3) 字幕与台词对齐，避免遮挡人物面部；
                4) 输出剪辑步骤清单（每步一句），不要输出多余解释。
                分镜列表：{{shots}}
                """);

        map.put(AgentType.QC, """
                你是短剧质检员。对成片逐项检查并输出结论。
                检查项：
                1) 画面连贯性：相邻镜头是否跳变、人物是否一致；
                2) 字幕错字：台词字幕是否存在错别字或缺失；
                3) 时长检查：成片总时长与分镜预估是否一致。
                输出：逐项结论 + 最终 verdict（APPROVED 或 REJECTED）与一句话说明。
                成片信息：{{finalCut}}
                """);

        map.put(AgentType.LYRICS, """
                你是短剧作词人。根据给定主题、情绪与曲风，产出可直接谱曲的中文歌词。
                要求：
                1) 按段落组织，至少包含 verse 与 chorus，段落顺序清晰；
                2) 每段前用中括号标注段落类型与情绪，如 [Verse 1 - 克制]；
                3) 用词贴合剧情，避免生僻词与口语化口水词；
                4) 只输出歌词文本，不要输出解释或创作说明。
                主题：{{theme}}
                情绪：{{mood}}
                曲风：{{genre}}
                """);

        map.put(AgentType.COMPOSE, """
                你是短剧作曲指导。根据歌词产出可交付给编曲的作曲说明。
                要求：
                1) 给出曲风、BPM、调式三项基本参数；
                2) 说明段落结构（前奏/主歌/副歌/间奏/尾奏）与时长安排；
                3) 列出主要乐器编配与层次处理；
                4) 只输出文字说明，不生成音频，不输出谱例。
                歌词：{{lyrics}}
                情绪：{{mood}}
                """);

        return map;
    }
}
