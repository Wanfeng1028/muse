package com.dramafactory.service;

import java.util.List;

/**
 * 章节事件图谱中的单条结构化事件，供后续"事件表 → 剧本 → 分镜"链路使用。
 *
 * <p>字段语义与 chapter-events 提示词的输出约定保持一致。</p>
 */
public record ChapterEvent(
        /**
         * 从 1 开始的章节序号。
         */
        int chapterIndex,
        /**
         * 章节标题；原文无标题时使用 "第 N 章" 形式。
         */
        String chapterTitle,
        /**
         * 涉及角色，使用规范称呼。
         */
        List<String> characters,
        /**
         * 核心事件：谁采取什么行动、造成什么结果。
         */
        String coreEvent,
        /**
         * 主线关系，以 强/中/弱 开头并附简短理由。
         */
        String mainlineRelation,
        /**
         * 信息密度，取值 高/中/低。
         */
        String infoDensity,
        /**
         * 预计可改编时长，单位秒。
         */
        int estimatedSeconds,
        /**
         * 情绪标签，多个以 + 连接。
         */
        String emotions
) {
    public ChapterEvent {
        characters = characters == null ? List.of() : List.copyOf(characters);
    }
}

