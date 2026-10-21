package com.dramafactory.service;

import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Shot;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SlideshowRiskScorerDeepTest {

    private final SlideshowRiskScorer scorer = new SlideshowRiskScorer();

    @Test
    void score_nullScenes_fail() {
        SlideshowRiskScorer.SlideshowRiskReport report = scorer.score(null, "ffmpeg", "remotion");
        assertEquals("fail", report.verdict());
        assertEquals(5.0, report.average());
        assertEquals(0, report.scenesChecked());
        assertTrue(report.dimensions().isEmpty());
        assertEquals("remotion", report.renderRuntime());
    }

    @Test
    void score_emptyScenes_fail() {
        SlideshowRiskScorer.SlideshowRiskReport report = scorer.score(List.of(), "x", "y");
        assertEquals("fail", report.verdict());
        assertEquals(5.0, report.average());
    }

    @Test
    void scoreShots_null_fail() {
        SlideshowRiskScorer.SlideshowRiskReport report = scorer.scoreShots(null, "ffmpeg");
        assertEquals("fail", report.verdict());
        assertEquals(0, report.scenesChecked());
        assertNull(report.renderRuntime());
    }

    @Test
    void score_threeTextCards_revise() {
        List<SlideshowRiskScorer.SceneFeatures> scenes = List.of(
                new SlideshowRiskScorer.SceneFeatures("text_card", "文字卡一", "none", "static", false, false, false),
                new SlideshowRiskScorer.SceneFeatures("text_card", "文字卡二", "none", "static", false, false, false),
                new SlideshowRiskScorer.SceneFeatures("text_card", "文字卡三", "none", "static", false, false, false)
        );
        SlideshowRiskScorer.SlideshowRiskReport report = scorer.score(scenes, "hyperframes", "remotion");
        assertEquals(3.17, report.average());
        assertEquals("revise", report.verdict());
        assertEquals("需修改", report.verdictLabel());
        assertEquals(3, report.scenesChecked());
        assertEquals(List.of("repetition", "decorative_visuals", "weak_motion", "weak_shot_intent", "typography_overreliance", "unsupported_cinematic_claims"),
                List.copyOf(report.dimensions().keySet()));
    }

    @Test
    void score_fourGoodScenes_strong() {
        List<SlideshowRiskScorer.SceneFeatures> scenes = List.of(
                new SlideshowRiskScorer.SceneFeatures("visual", "山间清晨", "none", "unspecified", true, false, false),
                new SlideshowRiskScorer.SceneFeatures("dialogue", "争吵戏", "none", "unspecified", true, false, false),
                new SlideshowRiskScorer.SceneFeatures("visual", "夜市追逐", "none", "unspecified", true, false, false),
                new SlideshowRiskScorer.SceneFeatures("dialogue", "和解戏", "none", "unspecified", true, false, false)
        );
        SlideshowRiskScorer.SlideshowRiskReport report = scorer.score(scenes, "ffmpeg", null);
        assertEquals(0.5, report.average());
        assertEquals("strong", report.verdict());
        assertEquals("强", report.verdictLabel());
        assertEquals(4, report.scenesChecked());
    }

    @Test
    void fromShot_textCardKeywords() {
        Shot shot1 = new Shot();
        shot1.setDescription("本集文字卡");
        assertEquals("text_card", SlideshowRiskScorer.fromShot(shot1).type());

        Shot shot2 = new Shot();
        shot2.setDescription("标题卡片");
        assertEquals("text_card", SlideshowRiskScorer.fromShot(shot2).type());

        Shot shot3 = new Shot();
        shot3.setDescription("字幕卡");
        assertEquals("text_card", SlideshowRiskScorer.fromShot(shot3).type());

        Shot shot4 = new Shot();
        shot4.setDescription("this is text_card style");
        assertEquals("text_card", SlideshowRiskScorer.fromShot(shot4).type());
    }

    @Test
    void fromShot_dialoguePriority() {
        Shot shot1 = new Shot();
        shot1.setDescription("普通场景");
        shot1.setDialogue("你好");
        assertEquals("dialogue", SlideshowRiskScorer.fromShot(shot1).type());

        Shot shot2 = new Shot();
        shot2.setDescription("文字卡");
        shot2.setDialogue("你好");
        assertEquals("text_card", SlideshowRiskScorer.fromShot(shot2).type());
    }

    @Test
    void fromShot_nulls() {
        Shot shot = new Shot();
        SlideshowRiskScorer.SceneFeatures features = SlideshowRiskScorer.fromShot(shot);
        assertEquals("", features.description());
        assertEquals("visual", features.type());
        assertEquals("none", features.shotSize());
        assertEquals("unspecified", features.cameraMovement());
        assertFalse(features.hasIntent());
        assertFalse(features.heroMoment());
        assertFalse(features.lightingDefined());
    }

    @Test
    void fromShot_cameraMove() {
        Shot shot1 = new Shot();
        shot1.setCameraMove(CameraMove.GU_DING);
        assertEquals("static", SlideshowRiskScorer.fromShot(shot1).cameraMovement());

        Shot shot2 = new Shot();
        shot2.setCameraMove(CameraMove.TUI);
        assertEquals("TUI", SlideshowRiskScorer.fromShot(shot2).cameraMovement());
    }

    @Test
    void fromShot_intentTrim() {
        Shot shot1 = new Shot();
        shot1.setVideoPrompt("   ");
        assertFalse(SlideshowRiskScorer.fromShot(shot1).hasIntent());

        Shot shot2 = new Shot();
        shot2.setVideoPrompt("推镜头跟拍");
        assertTrue(SlideshowRiskScorer.fromShot(shot2).hasIntent());
    }

    @Test
    void fromShot_heroAndLighting() {
        Shot shot1 = new Shot();
        shot1.setDescription("高光时刻");
        assertTrue(SlideshowRiskScorer.fromShot(shot1).heroMoment());

        Shot shot2 = new Shot();
        shot2.setDescription("普通");
        shot2.setVideoPrompt("hero shot");
        assertTrue(SlideshowRiskScorer.fromShot(shot2).heroMoment());

        Shot shot3 = new Shot();
        shot3.setVideoPrompt("侧面打光");
        assertTrue(SlideshowRiskScorer.fromShot(shot3).lightingDefined());

        Shot shot4 = new Shot();
        shot4.setVideoPrompt("plain daylight");
        assertFalse(SlideshowRiskScorer.fromShot(shot4).lightingDefined());
    }

    @Test
    void scoreShots_singleShot() {
        Shot shot = new Shot();
        shot.setShotNo(1);
        shot.setDescription("开场");
        shot.setVideoPrompt("航拍");
        SlideshowRiskScorer.SlideshowRiskReport report = scorer.scoreShots(List.of(shot), "ffmpeg");
        assertEquals(1, report.scenesChecked());
        assertNotNull(report.verdict());
        assertEquals(6, report.dimensions().size());
    }
}