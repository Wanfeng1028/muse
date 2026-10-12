package com.dramafactory.service;

import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;

import java.util.ArrayList;
import java.util.List;

/**
 * 剧本生成器：纯逻辑类，根据剧集及其所属项目信息确定性地生成恰好 4 场剧本草稿。
 * 不依赖 Spring 容器，不引入随机数，方便单元测试。
 */
public class ScriptGenerator {

    /** 单场剧本草稿 */
    public record SceneDraft(int sceneNo,
                             String location,
                             String timeOfDay,
                             String description,
                             String dialogue,
                             String prompt) {
    }

    /**
     * 根据剧集生成 4 场剧本草稿：开场钩子、冲突升级、反转、高潮收尾。
     * 输出确定性，引用大纲关键词；大纲为空时使用默认剧情句。
     */
    public List<SceneDraft> generate(Episode episode) {
        // 提取基础信息
        DramaProject project = episode.getProject();
        String projectTitle = (project != null && project.getTitle() != null && !project.getTitle().isBlank())
                ? project.getTitle().trim() : "无题短剧";
        String genre = (project != null && project.getGenre() != null && !project.getGenre().isBlank())
                ? project.getGenre().trim() : "都市";
        String outline = (episode.getOutline() != null && !episode.getOutline().isBlank())
                ? episode.getOutline().trim() : "主角在平静日常中卷入一场无法回避的风波";

        // 取大纲中的关键词片段，保证输出引用大纲
        String keyword = extractKeyword(outline);

        List<SceneDraft> drafts = new ArrayList<>(4);

        // 第 1 场：开场钩子
        drafts.add(new SceneDraft(
                1,
                genre + "风格的城市街道",
                "黄昏",
                "开场以" + genre + "《" + projectTitle + "》切入：" + outline + "。镜头先给主角一个特写，随即将线索" + keyword
                        + "抛入画面，制造悬念与不安。",
                "主角（低声自语）：又是" + keyword + "……这一次，我不能再当作没看见。\n路人（画外）：你还敢留在这里？事情已经闹大了。",
                "opening hook scene, urban street at dusk, close-up on protagonist, cinematic lighting, " + genre
                        + " genre, tense atmosphere, shallow depth of field, 35mm film look"
        ));

        // 第 2 场：冲突升级
        drafts.add(new SceneDraft(
                2,
                "狭窄的室内走廊",
                "夜晚",
                "冲突升级：围绕" + keyword + "，对立双方在走廊中正面交锋，言语与动作逐步逼近临界点，" + genre
                        + "《" + projectTitle + "》的紧张感被推到第一个高点。",
                "对手（冷笑）：你以为握住" + keyword + "就能改变结局？\n主角（逼近一步）：至少我不会再后退。",
                "conflict escalation scene, narrow indoor corridor at night, medium shot, over-the-shoulder angle, "
                        + "cinematic lighting, dramatic shadows, high tension, " + genre + " genre"
        ));

        // 第 3 场：反转
        drafts.add(new SceneDraft(
                3,
                "光线骤暗的旧仓库",
                "深夜",
                "反转：主角发现" + keyword + "背后隐藏的真相，原有认知被彻底颠覆，剧情走向意料之外的方向，" + genre
                        + "《" + projectTitle + "》迎来关键转折。",
                "主角（震惊）：原来" + keyword + "从一开始就是……\n神秘人（背对镜头）：你终于看懂了。可惜，太迟了。",
                "plot twist scene, dim old warehouse, deep focus, low-key lighting, sudden reveal, extreme close-up "
                        + "on shocked face, cinematic mood, " + genre + " genre"
        ));

        // 第 4 场：高潮收尾
        drafts.add(new SceneDraft(
                4,
                "天台边缘",
                "凌晨",
                "高潮收尾：所有围绕" + keyword + "的矛盾在天台迎来正面解决，主角做出决定性选择，" + genre
                        + "《" + projectTitle + "》以一个有力而克制的画面结束本集。",
                "主角（坚定）：不管代价是什么，这一次由我来结束。\n对手（沉默片刻）：那就别怪我了。",
                "climax finale scene, rooftop at dawn, wide shot then close-up, backlight rim lighting, cinematic "
                        + "lighting, emotional resolution, slow motion, " + genre + " genre"
        ));

        return drafts;
    }

    /**
     * 从大纲中提取一个关键词片段（取前若干字符），确保生成内容引用大纲。
     */
    private String extractKeyword(String outline) {
        String cleaned = outline.replaceAll("\\s+", "");
        if (cleaned.isEmpty()) {
            return "秘密";
        }
        // 关键词长度：不超过 12 个字符，避免过长
        int end = Math.min(cleaned.length(), 12);
        return cleaned.substring(0, end);
    }
}
