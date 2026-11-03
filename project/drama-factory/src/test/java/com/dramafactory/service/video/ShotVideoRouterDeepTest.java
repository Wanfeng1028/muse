package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

/**
 * ShotVideoRouter.route 全分支深挖测试。
 * 被测方法源码：com.dramafactory.service.video.ShotVideoRouter#route(Shot)。
 * 逐分支覆盖：
 *   B1 shot == null                                    → null
 *   B2 preferredProvider != null && !isBlank()         → 直接返回 preferred
 *   B3 dialogue != null && strip().length() >= 10      → "minimax"
 *   B4 videoPrompt == null && description == null      → null
 *   B5 text 命中卡通/动画/可爱关键词                   → "doubao"
 *   B6 text 命中写实/真人/电影感关键词                 → "novai"
 *   B7 text 命中水墨/国风/中文文字/calligraphy         → "painted"
 *   B8 text 命中水彩/手绘/风格化关键词                 → "painted"
 *   B9 text 无任何命中                                 → null
 * 每个用例注释里标注覆盖的分支行。
 */
class ShotVideoRouterDeepTest {

    private ShotVideoRouter newRouter() {
        return new ShotVideoRouter();
    }

    // ---------- B1 shot == null ----------

    @Test
    void routeNullShotReturnsNull() {
        // 覆盖 B1：源码第一个 if (shot == null) return null;
        assertNull(newRouter().route(null));
    }

    // ---------- B2 preferredProvider 合法 / 空白 ----------

    @Test
    void routeValidPreferredProviderReturnsItDirectly() {
        // 覆盖 B2 命中分支：preferred != null && !isBlank() → 立即返回 preferred。
        // 同时让 dialogue/description 也带上其它特征，验证优先返回 preferred 而不会被后续分支截胡。
        Shot shot = new Shot();
        shot.setPreferredProvider("custom-provider");
        shot.setDialogue("这是一段很长的台词文本用于触发 minimax");
        shot.setDescription("卡通动画风格");

        assertEquals("custom-provider", newRouter().route(shot));
    }

    @Test
    void routeBlankPreferredProviderFallsThrough() {
        // 覆盖 B2 未命中分支：preferred 是空白 → 进入后续分支。
        // dialogue 长度 < 10，videoPrompt/description 都命中卡通 → doubao。
        Shot shot = new Shot();
        shot.setPreferredProvider("   ");
        shot.setDialogue("短台词");
        shot.setVideoPrompt("cute cartoon");

        assertEquals("doubao", newRouter().route(shot));
    }

    @Test
    void routeEmptyPreferredProviderFallsThrough() {
        // 覆盖 B2 未命中分支：preferred 是空串 → 进入后续分支。
        // 让 videoPrompt 命中写实 → novai。
        Shot shot = new Shot();
        shot.setPreferredProvider("");
        shot.setVideoPrompt("realistic cinematic shot");

        assertEquals("novai", newRouter().route(shot));
    }

    // ---------- B3 dialogue 长度阈值 ----------

    @Test
    void routeLongDialogueReturnsMinimax() {
        // 覆盖 B3 命中分支：dialogue.strip().length() >= 10 → "minimax"。
        // 这里 strip 后正好 10 个字符，验证边界等于 10 也命中。
        Shot shot = new Shot();
        shot.setDialogue("1234567890");

        assertEquals("minimax", newRouter().route(shot));
    }

    @Test
    void routeDialogueWithSurroundingWhitespaceStrippedStillHitsMinimax() {
        // 覆盖 B3 的 strip 行为：原始字符串长度 12，但含前后空白，strip 后 10 字符 → 命中。
        Shot shot = new Shot();
        shot.setDialogue("  1234567890  ");

        assertEquals("minimax", newRouter().route(shot));
    }

    @Test
    void routeDialogueJustBelowThresholdFallsThrough() {
        // 覆盖 B3 未命中分支：strip 后 9 字符 < 10 → 继续往下走。
        // videoPrompt 命中水墨 → painted。
        Shot shot = new Shot();
        shot.setDialogue("123456789");
        shot.setVideoPrompt("水墨国风画面");

        assertEquals("painted", newRouter().route(shot));
    }

    // ---------- B4 视频提示词与描述都为 null ----------

    @Test
    void routeNoVideoPromptAndNoDescriptionReturnsNull() {
        // 覆盖 B4 命中分支：videoPrompt == null && description == null → null。
        Shot shot = new Shot();
        shot.setDialogue("短");
        // 不设置 videoPrompt / description，默认均为 null

        assertNull(newRouter().route(shot));
    }

    // ---------- B5 卡通 / 动画 / 可爱关键词 ----------

    @Test
    void routeCartoonKeywordReturnsDoubao() {
        // 覆盖 B5 命中分支：description 含 "卡通" → "doubao"。
        Shot shot = new Shot();
        shot.setDescription("一个卡通风格的小女孩");

        assertEquals("doubao", newRouter().route(shot));
    }

    @Test
    void routeAnimationKeywordInVideoPromptReturnsDoubao() {
        // 覆盖 B5 命中分支：videoPrompt 含 "animation" → "doubao"。
        // 注意 videoPrompt 会拼接到 text 前端。
        Shot shot = new Shot();
        shot.setVideoPrompt("animation cute pixar style");

        assertEquals("doubao", newRouter().route(shot));
    }

    // ---------- B6 写实 / 真人 / 电影感关键词 ----------

    @Test
    void routeRealisticKeywordReturnsNovai() {
        // 覆盖 B6 命中分支：description 含 "写实" → "novai"。
        Shot shot = new Shot();
        shot.setDescription("写实风格的人物特写");

        assertEquals("novai", newRouter().route(shot));
    }

    @Test
    void routeCinematicKeywordReturnsNovai() {
        // 覆盖 B6 命中分支：videoPrompt 含 "cinematic" → "novai"。
        Shot shot = new Shot();
        shot.setVideoPrompt("cinematic wide shot");

        assertEquals("novai", newRouter().route(shot));
    }

    // ---------- B7 水墨 / 国风 / 中文文字 / calligraphy ----------

    @Test
    void routeInkPaintingKeywordReturnsPainted() {
        // 覆盖 B7 命中分支：description 含 "水墨" → "painted"。
        Shot shot = new Shot();
        shot.setDescription("水墨山水画风");

        assertEquals("painted", newRouter().route(shot));
    }

    @Test
    void routeCalligraphyKeywordReturnsPainted() {
        // 覆盖 B7 命中分支：videoPrompt 含 "calligraphy" → "painted"。
        Shot shot = new Shot();
        shot.setVideoPrompt("calligraphy scroll");

        assertEquals("painted", newRouter().route(shot));
    }

    // ---------- B8 水彩 / 手绘 / 风格化 ----------

    @Test
    void routeWatercolorKeywordReturnsPainted() {
        // 覆盖 B8 命中分支：description 含 "水彩" → "painted"。
        Shot shot = new Shot();
        shot.setDescription("水彩插画风格");

        assertEquals("painted", newRouter().route(shot));
    }

    @Test
    void routeHandPaintedKeywordReturnsPainted() {
        // 覆盖 B8 命中分支：videoPrompt 含 "hand-painted" → "painted"。
        Shot shot = new Shot();
        shot.setVideoPrompt("hand-painted texture");

        assertEquals("painted", newRouter().route(shot));
    }

    // ---------- B9 无任何命中 ----------

    @Test
    void routeUnmatchedTextReturnsNull() {
        // 覆盖 B9：text 非空但未命中任何关键词 → 落到最后 return null。
        Shot shot = new Shot();
        shot.setVideoPrompt("some generic scene");
        shot.setDescription("普通的街道场景");

        assertNull(newRouter().route(shot));
    }

    // ---------- 组合分支：videoPrompt 与 description 拼接后命中 ----------

    @Test
    void routeVideoPromptAndDescriptionConcatenatedForMatching() {
        // 覆盖拼接逻辑：videoPrompt 只含 "cute"，description 只含 "pixar"，
        // 拼接后 text 同时含两者，命中 B5 → "doubao"。
        Shot shot = new Shot();
        shot.setVideoPrompt("cute");
        shot.setDescription("pixar");

        assertEquals("doubao", newRouter().route(shot));
    }

    @Test
    void routeDescriptionOnlyWhenVideoPromptNull() {
        // 覆盖 videoPrompt == null 而 description 非 null 的拼接分支：
        // 只有 description 参与匹配，含 "国风" → "painted"。
        Shot shot = new Shot();
        shot.setDescription("国风水墨长卷");

        assertEquals("painted", newRouter().route(shot));
    }

    @Test
    void routeVideoPromptOnlyWhenDescriptionNull() {
        // 覆盖 description == null 而 videoPrompt 非 null 的拼接分支：
        // 只有 videoPrompt 参与匹配，含 "realistic" → "novai"。
        Shot shot = new Shot();
        shot.setVideoPrompt("realistic portrait");

        assertEquals("novai", newRouter().route(shot));
    }
}
