package com.dramafactory.service;

import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Shot;
import com.dramafactory.service.SlideshowRiskScorer.SceneFeatures;
import com.dramafactory.service.SlideshowRiskScorer.SlideshowRiskReport;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SlideshowRiskScorerTest {

    private final SlideshowRiskScorer scorer = new SlideshowRiskScorer();

    @Test
    void emptyScenes_returnsFail() {
        SlideshowRiskReport report = scorer.score(new ArrayList<>(), null, null);
        assertThat(report.average()).isEqualTo(5.0);
        assertThat(report.verdict()).isEqualTo("fail");
        assertThat(report.dimensions()).isEmpty();
    }

    @Test
    void eightScenes_highVariety_strong() {
        // 8 场景：type 全 "visual"、description 各异、shotSize 各异、6 个运动镜头且全部 hasIntent
        // repetition: typeRatio=1.0>0.7 → +2.0；desc 各异 → 不加；size 各异 → 不加；得分 2.0
        // decorative: hasIntent 全 true → 0.0
        // weak_motion: 6 运动镜头全 hasIntent → 0.0
        // weak_shot_intent: 全 hasIntent → 0.0
        // typography: 无 text_card → 0.0
        // cinematic: rendererFamily=null → 0.0
        // average = 2.0/6 = 0.333... → 0.33；verdict = strong
        List<SceneFeatures> scenes = new ArrayList<>();
        for (int i = 0; i < 6; i++) {
            scenes.add(new SceneFeatures("visual", "desc" + i, "size" + i, "pan", true, false, false));
        }
        for (int i = 6; i < 8; i++) {
            scenes.add(new SceneFeatures("visual", "desc" + i, "size" + i, "static", true, false, false));
        }

        SlideshowRiskReport report = scorer.score(scenes, null, null);
        assertThat(report.dimensions().get("repetition").score()).isEqualTo(2.0);
        assertThat(report.dimensions().get("decorative_visuals").score()).isEqualTo(0.0);
        assertThat(report.dimensions().get("weak_motion").score()).isEqualTo(0.0);
        assertThat(report.dimensions().get("weak_shot_intent").score()).isEqualTo(0.0);
        assertThat(report.dimensions().get("typography_overreliance").score()).isEqualTo(0.0);
        assertThat(report.dimensions().get("unsupported_cinematic_claims").score()).isEqualTo(0.0);
        assertThat(report.average()).isEqualTo(0.33);
        assertThat(report.verdict()).isEqualTo("strong");
    }

    @Test
    void tenScenes_textHeavyStatic_revise() {
        // 10 场景：全 static、全无意图、type 全 "text_card"、description 各异、shotSize 全同
        // repetition: typeRatio=1.0>0.7 → +2.0；desc 各异 → 不加；size 全同 → +1.5；得分 3.5
        // decorative: 全无意图 → 5.0
        // weak_motion: 无运动镜头 → 1.5
        // weak_shot_intent: 全无意图 → 5.0
        // typography: 全 text_card → 4.0
        // cinematic: rendererFamily=null → 0.0
        // average = (3.5+5.0+1.5+5.0+4.0+0.0)/6 = 19/6 = 3.1666... → 3.17；verdict = revise
        List<SceneFeatures> scenes = new ArrayList<>();
        for (int i = 0; i < 10; i++) {
            scenes.add(new SceneFeatures("text_card", "desc" + i, "wide", "static", false, false, false));
        }

        SlideshowRiskReport report = scorer.score(scenes, null, null);
        assertThat(report.dimensions().get("repetition").score()).isEqualTo(3.5);
        assertThat(report.dimensions().get("decorative_visuals").score()).isEqualTo(5.0);
        assertThat(report.dimensions().get("weak_motion").score()).isEqualTo(1.5);
        assertThat(report.dimensions().get("weak_shot_intent").score()).isEqualTo(5.0);
        assertThat(report.dimensions().get("typography_overreliance").score()).isEqualTo(4.0);
        assertThat(report.dimensions().get("unsupported_cinematic_claims").score()).isEqualTo(0.0);
        assertThat(report.average()).isEqualTo(3.17);
        assertThat(report.verdict()).isEqualTo("revise");
    }

    @Test
    void cinematicClaims_unsupported_fail() {
        // rendererFamily="cinematic-film"、6 场景：无 hero、无运镜、lighting 全 false、hasIntent 全 true
        // cinematic: hero=0 → issue1；运镜=0 < 6*0.3 → issue2；lighting=0 < 6*0.3 → issue3
        // score = min(5, 3*1.8) = 5.0
        List<SceneFeatures> scenes = new ArrayList<>();
        for (int i = 0; i < 6; i++) {
            scenes.add(new SceneFeatures("visual", "desc" + i, "size" + i, "static", true, false, false));
        }

        SlideshowRiskReport report = scorer.score(scenes, "cinematic-film", null);
        assertThat(report.dimensions().get("unsupported_cinematic_claims").score()).isEqualTo(5.0);
    }

    @Test
    void fromShot_mapsFields() {
        // text_card：description 含「文字卡」
        Shot shot1 = mock(Shot.class);
        when(shot1.getDescription()).thenReturn("文字卡：标题");
        when(shot1.getDialogue()).thenReturn(null);
        when(shot1.getShotSize()).thenReturn(null);
        when(shot1.getCameraMove()).thenReturn(null);
        when(shot1.getVideoPrompt()).thenReturn(null);
        SceneFeatures f1 = SlideshowRiskScorer.fromShot(shot1);
        assertThat(f1.type()).isEqualTo("text_card");
        assertThat(f1.shotSize()).isEqualTo("none");
        assertThat(f1.cameraMovement()).isEqualTo("unspecified");

        // dialogue：dialogue 非空
        Shot shot2 = mock(Shot.class);
        when(shot2.getDescription()).thenReturn("普通场景");
        when(shot2.getDialogue()).thenReturn("你好");
        when(shot2.getShotSize()).thenReturn(null);
        when(shot2.getCameraMove()).thenReturn(null);
        when(shot2.getVideoPrompt()).thenReturn(null);
        SceneFeatures f2 = SlideshowRiskScorer.fromShot(shot2);
        assertThat(f2.type()).isEqualTo("dialogue");

        // visual：无文字卡关键词且 dialogue 为空
        Shot shot3 = mock(Shot.class);
        when(shot3.getDescription()).thenReturn("普通场景");
        when(shot3.getDialogue()).thenReturn(null);
        when(shot3.getShotSize()).thenReturn(null);
        when(shot3.getCameraMove()).thenReturn(null);
        when(shot3.getVideoPrompt()).thenReturn(null);
        SceneFeatures f3 = SlideshowRiskScorer.fromShot(shot3);
        assertThat(f3.type()).isEqualTo("visual");

        // GU_DING → static
        Shot shot4 = mock(Shot.class);
        when(shot4.getDescription()).thenReturn("普通场景");
        when(shot4.getDialogue()).thenReturn(null);
        when(shot4.getShotSize()).thenReturn(null);
        when(shot4.getCameraMove()).thenReturn(CameraMove.GU_DING);
        when(shot4.getVideoPrompt()).thenReturn(null);
        SceneFeatures f4 = SlideshowRiskScorer.fromShot(shot4);
        assertThat(f4.cameraMovement()).isEqualTo("static");
    }
}
