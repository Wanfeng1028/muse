package com.dramafactory.service;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import java.util.Map;
import java.util.stream.IntStream;
import java.util.stream.Collectors;
import java.util.Collections;

class DeconstructionAnalyzerTest {
    private static final DeconstructionAnalyzer.Config CFG = new DeconstructionAnalyzer.Config(0.4, 120, 2.5);
    private static final DeconstructionAnalyzer analyzer = new DeconstructionAnalyzer();
    private static final DeconstructionReportBuilder reportBuilder = new DeconstructionReportBuilder();

    // 验证根据切分点生成精确的镜头段
    @Test
    void segmentsFromCuts() {
        List<DeconstructionAnalyzer.ShotSegment> segments = analyzer.buildSegments(6.0, List.of(2.0, 4.0), CFG);
        assertEquals(3, segments.size());
        assertEquals(1, segments.get(0).shotNo());
        assertEquals(0.0, segments.get(0).startSec(), 0.001);
        assertEquals(2.0, segments.get(0).endSec(), 0.001);
        assertEquals(2.0, segments.get(1).startSec(), 0.001);
        assertEquals(4.0, segments.get(1).endSec(), 0.001);
        assertEquals(3.0, segments.get(2).shotNo());
        assertEquals(4.0, segments.get(2).startSec(), 0.001);
        assertEquals(6.0, segments.get(2).endSec(), 0.001);
    }

    // 验证无切分点时按回退时长均匀分割
    @Test
    void fallbackUniformSampling() {
        List<DeconstructionAnalyzer.ShotSegment> segments = analyzer.buildSegments(10.0, List.of(), CFG);
        assertEquals(4, segments.size());
        assertEquals(0.0, segments.get(0).startSec(), 0.001);
        assertEquals(2.5, segments.get(0).endSec(), 0.001);
        assertEquals(2.5, segments.get(1).startSec(), 0.001);
        assertEquals(5.0, segments.get(1).endSec(), 0.001);
        assertEquals(5.0, segments.get(2).startSec(), 0.001);
        assertEquals(7.5, segments.get(2).endSec(), 0.001);
        assertEquals(7.5, segments.get(3).startSec(), 0.001);
        assertEquals(10.0, segments.get(3).endSec(), 0.001);
    }

    // 验证短片段与前一片段合并逻辑
    @Test
    void shortSegmentMergedIntoPrevious() {
        List<DeconstructionAnalyzer.ShotSegment> segments = analyzer.buildSegments(6.0, List.of(0.2, 3.0), CFG);
        assertEquals(2, segments.size());
        assertEquals(0.0, segments.get(0).startSec(), 0.001);
        assertEquals(3.0, segments.get(0).endSec(), 0.001);
        assertEquals(3.0, segments.get(1).startSec(), 0.001);
        assertEquals(6.0, segments.get(1).endSec(), 0.001);
    }

    // 验证最大镜头数限制导致合并
    @Test
    void maxShotsCapMerges() {
        List<Double> cuts = IntStream.rangeClosed(1, 99).asDoubleStream().boxed().collect(Collectors.toList());
        List<DeconstructionAnalyzer.ShotSegment> segments = analyzer.buildSegments(
            100.0, cuts, new DeconstructionAnalyzer.Config(0.4, 10, 2.5));
        assertEquals(10, segments.size());
        assertEquals(0.0, segments.get(0).startSec(), 0.001);
        assertEquals(100.0, segments.get(9).endSec(), 0.001);
        for (int i = 1; i < 10; i++) {
            assertEquals(segments.get(i-1).endSec(), segments.get(i).startSec(), 0.001);
        }
    }

    // 验证无效时长抛出异常
    @Test
    void invalidDurationThrows() {
        assertThrows(IllegalArgumentException.class, () -> 
            analyzer.buildSegments(0.0, List.of(), CFG));
    }

    // 验证节奏和时长分类逻辑
    @Test
    void rhythmAndDurationClasses() {
        assertEquals("快节奏", DeconstructionAnalyzer.classifyRhythm(1.5));
        assertEquals("中节奏", DeconstructionAnalyzer.classifyRhythm(2.0));
        assertEquals("慢节奏", DeconstructionAnalyzer.classifyRhythm(6.0));
        assertEquals("短切", DeconstructionAnalyzer.durationClass(1.0));
        assertEquals("常规", DeconstructionAnalyzer.durationClass(3.0));
        assertEquals("长镜", DeconstructionAnalyzer.durationClass(7.0));
    }

    // 验证宽高比标签生成
    @Test
    void ratioLabels() {
        assertEquals("16:9", DeconstructionAnalyzer.ratioLabel(1920, 1080));
        assertEquals("9:16", DeconstructionAnalyzer.ratioLabel(1080, 1920));
        assertEquals("4:3", DeconstructionAnalyzer.ratioLabel(320, 240));
        assertEquals("未知", DeconstructionAnalyzer.ratioLabel(null, 100));
    }

    // 验证短视频完整分析结果
    @Test
    void analyzeShortVideo() {
        DeconstructionAnalyzer.VideoMeta meta = new DeconstructionAnalyzer.VideoMeta(
            6.0, 320, 240, 25.0, 800000L);
        DeconstructionAnalyzer.Analysis analysis = analyzer.analyze(meta, List.of(2.0, 4.0), CFG);
        assertEquals(3, analysis.shots().size());
        assertEquals(2.0, analysis.avgShotDurationSec(), 0.001);
        assertEquals(20.0, analysis.cutsPerMinute(), 0.001);
        assertEquals("中节奏", analysis.rhythmClass());
        assertEquals(2.0, analysis.hookEndSec(), 0.001);
        assertEquals(2, analysis.structure().size());
        assertEquals("钩子", analysis.structure().get(0).kind());
        assertEquals("主体", analysis.structure().get(1).kind());
        assertEquals("钩子", analysis.shots().get(0).role());
        assertEquals("主体", analysis.shots().get(1).role());
        assertEquals("主体", analysis.shots().get(2).role());
        assertEquals("钩子→主体", analysis.formula().get("structureTemplate"));
        assertEquals(100.0, ((Map<String, Object>)analysis.formula().get("composition")).get("常规占比"));
        assertEquals(0.0, ((Map<String, Object>)analysis.formula().get("composition")).get("短切占比"));
        assertTrue(analysis.shots().get(0).genericPrompt().contains("[待AI增强]"));
        assertTrue(analysis.shots().get(0).genericPrompt().contains("画幅：4:3"));
        assertTrue(analysis.shots().get(0).seedancePrompt().contains("时长：2.0 秒"));
        assertTrue(analysis.shots().get(0).seedancePrompt().contains("画幅：4:3"));
        assertEquals("4:3", analysis.ratioLabel());
        assertTrue(analysis.scriptTemplate().contains("主体/台词"));
    }

    // 验证长视频结构识别
    @Test
    void analyzeLongVideoStructure() {
        DeconstructionAnalyzer.VideoMeta meta = new DeconstructionAnalyzer.VideoMeta(
            20.0, 1080, 1920, 30.0, 2000000L);
        DeconstructionAnalyzer.Analysis analysis = analyzer.analyze(
            meta, List.of(2.0, 5.0, 9.0, 14.0, 16.0, 18.0), CFG);
        assertEquals(7, analysis.shots().size());
        assertEquals(5, analysis.structure().size());
        assertEquals("钩子", analysis.structure().get(0).kind());
        assertEquals("主体", analysis.structure().get(1).kind());
        assertEquals("转折", analysis.structure().get(2).kind());
        assertEquals("主体", analysis.structure().get(3).kind());
        assertEquals("收尾", analysis.structure().get(4).kind());
        assertEquals("钩子→主体→转折→主体→收尾", analysis.formula().get("structureTemplate"));
        assertEquals(List.of(4), analysis.structure().get(2).shotNos());
        assertEquals("转折", analysis.shots().get(3).role());
        assertEquals("收尾", analysis.shots().get(6).role());
        assertEquals("9:16", analysis.ratioLabel());
    }

    // 验证报告生成完整章节
    @Test
    void reportContainsAllSections() {
        DeconstructionAnalyzer.VideoMeta meta = new DeconstructionAnalyzer.VideoMeta(
            6.0, 320, 240, 25.0, 800000L);
        DeconstructionAnalyzer.Analysis analysis = analyzer.analyze(meta, List.of(2.0, 4.0), CFG);
        String report = reportBuilder.buildReport(
            "sample.mp4", analysis, 
            List.of("deconstruction/1/frames/shot-001.jpg", 
                   "deconstruction/1/frames/shot-002.jpg", 
                   "deconstruction/1/frames/shot-003.jpg"));
        assertTrue(report.contains("# 视频拆解报告：sample.mp4"));
        assertTrue(report.contains("## 概览（实测数据）"));
        assertTrue(report.contains("## 节奏与结构（规则推断）"));
        assertTrue(report.contains("## 爆款公式提炼（规则推断）"));
        assertTrue(report.contains("## 逐镜表"));
        assertTrue(report.contains("## 逐镜反推提示词"));
        assertTrue(report.contains("Seedance 版"));
        assertTrue(report.contains("## 创作剧本模板"));
        assertTrue(report.contains("## 数据口径说明"));
        assertTrue(report.contains("未覆盖：逐字稿"));
        assertTrue(report.contains("shot-001.jpg"));
        assertTrue(report.contains("| 待AI增强 |"));
    }
}
