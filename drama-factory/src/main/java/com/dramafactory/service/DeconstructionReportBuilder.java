package com.dramafactory.service;

import org.springframework.stereotype.Component;
import java.util.List;
import java.util.Map;

@Component
public class DeconstructionReportBuilder {

    public String buildReport(String sourceName, DeconstructionAnalyzer.Analysis a, List<String> keyframePaths) {
        StringBuilder sb = new StringBuilder();

        // 1. 标题
        sb.append("# 视频拆解报告：").append(sourceName).append("\n\n");

        // 2. 概览（实测数据）
        sb.append("## 概览（实测数据）\n\n");
        sb.append("- 源视频：").append(sourceName).append("\n");
        sb.append("- 时长：").append(fmt(a.meta().durationSec())).append(" 秒\n");
        sb.append("- 分辨率：")
          .append(a.meta().width() == null ? "未知" : a.meta().width() + "×" + a.meta().height())
          .append("\n");
        sb.append("- 帧率：")
          .append(a.meta().fps() == null ? "未知" : String.valueOf(a.meta().fps()))
          .append("\n");
        sb.append("- 码率：")
          .append(a.meta().bitRate() == null ? "未知" : a.meta().bitRate() + " bps")
          .append("\n");
        sb.append("- 镜数：").append(a.shots().size()).append("\n");
        sb.append("- 平均镜长：").append(fmt(a.avgShotDurationSec())).append(" 秒\n");
        sb.append("- 每分钟切数：").append(fmt(a.cutsPerMinute())).append("\n\n");

        // 3. 节奏与结构（规则推断）
        sb.append("## 节奏与结构（规则推断）\n\n");
        sb.append("- 节奏分类：").append(a.rhythmClass()).append("\n");
        sb.append("- 钩子段结束：").append(fmt(a.hookEndSec())).append(" 秒\n");
        sb.append("- 结构模板：").append(a.formula().get("structureTemplate")).append("\n");
        for (DeconstructionAnalyzer.StructureSegment seg : a.structure()) {
            sb.append("- ")
              .append(seg.kind())
              .append("：")
              .append(fmt(seg.startSec()))
              .append("s–")
              .append(fmt(seg.endSec()))
              .append("s，")
              .append(seg.note())
              .append("\n");
        }
        sb.append("\n");

        // 4. 爆款公式提炼（规则推断）
        sb.append("## 爆款公式提炼（规则推断）\n\n");
        @SuppressWarnings("unchecked")
        List<String> notes = (List<String>) a.formula().get("notes");
        for (String note : notes) {
            sb.append("- ").append(note).append("\n");
        }
        sb.append("\n");

        // 5. 逐镜表
        sb.append("## 逐镜表\n\n");
        sb.append("| 镜号 | 起止（秒） | 时长（秒） | 关键帧 | 结构角色 | 时长类别 | 景别 | 运镜 |\n");
        sb.append("| --- | --- | --- | --- | --- | --- | --- | --- |\n");
        for (int i = 0; i < a.shots().size(); i++) {
            DeconstructionAnalyzer.AnalyzedShot shot = a.shots().get(i);
            String keyframePath = keyframePaths.get(i);
            sb.append("| ")
              .append(shot.segment().shotNo())
              .append(" | ")
              .append(fmt(shot.segment().startSec()))
              .append("–")
              .append(fmt(shot.segment().endSec()))
              .append(" | ")
              .append(fmt(shot.segment().duration()))
              .append(" | ")
              .append(keyframePath == null ? "抽帧失败" : fileName(keyframePath))
              .append(" | ")
              .append(shot.role())
              .append(" | ")
              .append(shot.durationClass())
              .append(" | 待AI增强 | 待AI增强 |\n");
        }
        sb.append("\n");

        // 6. 逐镜反推提示词
        sb.append("## 逐镜反推提示词\n");
        for (DeconstructionAnalyzer.AnalyzedShot shot : a.shots()) {
            sb.append("\n### 第 ")
              .append(shot.segment().shotNo())
              .append(" 镜（")
              .append(fmt(shot.segment().startSec()))
              .append("–")
              .append(fmt(shot.segment().endSec()))
              .append("s）\n");
            sb.append("- 通用版：").append(shot.genericPrompt()).append("\n");
            sb.append("- Seedance 版：").append(shot.seedancePrompt()).append("\n");
        }
        sb.append("\n");

        // 7. 创作剧本模板
        sb.append("## 创作剧本模板\n\n")
          .append(a.scriptTemplate())
          .append("\n\n");

        // 8. 数据口径说明
        sb.append("## 数据口径说明\n\n");
        sb.append("- 实测数据：ffprobe 元数据、场景切分点、关键帧与时长指标（真实测量）。\n");
        sb.append("- 规则推断：节奏分类、结构段划分、镜头构成与公式提炼（确定性规则）。\n");
        sb.append("- 待 AI 增强：主体、画面描述、景别、运镜、光线、调色（需视觉模型，当前以占位标注）。\n");
        sb.append("- 未覆盖：逐字稿/屏幕文案（ASR/OCR 未接入）、链接导入（抖音/TikTok/小红书未接入）。\n");

        return sb.toString();
    }

    private String fmt(double v) {
        return String.format(java.util.Locale.ROOT, "%.1f", v);
    }

    private String fileName(String path) {
        if (path == null) return "";
        String[] parts = path.split("/");
        return parts.length > 0 ? parts[parts.length - 1] : "";
    }
}
