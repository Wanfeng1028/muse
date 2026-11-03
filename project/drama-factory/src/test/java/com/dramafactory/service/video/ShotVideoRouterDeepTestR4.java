package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class ShotVideoRouterDeepTestR4 {

    private final ShotVideoRouter router = new ShotVideoRouter();

    @Test
    void route_nullShot_returnsNull() {
        assertNull(router.route(null));
    }

    @Test
    void route_preferredProvider_returnsIt() {
        Shot shot = new Shot();
        shot.setPreferredProvider("qwen");
        assertEquals("qwen", router.route(shot));
    }

    @Test
    void route_blankPreferred_fallsThrough() {
        Shot shot = new Shot();
        shot.setPreferredProvider("  ");
        shot.setVideoPrompt("cartoon cat");
        assertEquals("doubao", router.route(shot));
    }

    @Test
    void route_emptyPreferred_fallsThrough() {
        Shot shot = new Shot();
        shot.setPreferredProvider("");
        shot.setDescription("水墨国风");
        assertEquals("painted", router.route(shot));
    }

    @Test
    void route_bothTextNull_returnsNull() {
        Shot shot = new Shot();
        assertNull(router.route(shot));
    }

    @Test
    void route_cartoonKeyword_returnsDoubao() {
        Shot shot = new Shot();
        shot.setVideoPrompt("a cartoon style scene, pixar like");
        assertEquals("doubao", router.route(shot));
    }

    @Test
    void route_chineseCartoon_returnsDoubao() {
        Shot shot = new Shot();
        shot.setDescription("卡通风格的可爱小猫");
        assertEquals("doubao", router.route(shot));
    }

    @Test
    void route_pixar_returnsDoubao() {
        Shot shot = new Shot();
        shot.setDescription("皮克斯风格的场景");
        assertEquals("doubao", router.route(shot));
    }

    @Test
    void route_animation_returnsDoubao() {
        Shot shot = new Shot();
        shot.setDescription("这是一段动画");
        assertEquals("doubao", router.route(shot));
    }

    @Test
    void route_cute_returnsDoubao() {
        Shot shot = new Shot();
        shot.setVideoPrompt("CUTE little dog");
        assertEquals("doubao", router.route(shot));
    }

    @Test
    void route_realistic_returnsNovai() {
        Shot shot = new Shot();
        shot.setVideoPrompt("realistic cinematic shot");
        assertEquals("novai", router.route(shot));
    }

    @Test
    void route_chineseRealistic_returnsNovai() {
        Shot shot = new Shot();
        shot.setDescription("写实真人电影感");
        assertEquals("novai", router.route(shot));
    }

    @Test
    void route_inkWash_returnsPainted() {
        Shot shot = new Shot();
        shot.setDescription("水墨国风");
        assertEquals("painted", router.route(shot));
    }

    @Test
    void route_calligraphy_returnsPainted() {
        Shot shot = new Shot();
        shot.setVideoPrompt("Calligraphy on the wall");
        assertEquals("painted", router.route(shot));
    }

    @Test
    void route_watercolor_returnsPainted() {
        Shot shot = new Shot();
        shot.setDescription("水彩手绘风格化");
        assertEquals("painted", router.route(shot));
    }

    @Test
    void route_noKeyword_returnsNull() {
        Shot shot = new Shot();
        shot.setVideoPrompt("a normal street scene");
        shot.setDescription("普通街道");
        assertNull(router.route(shot));
    }

    @Test
    void route_doubaoPriorityOverNovai() {
        Shot shot = new Shot();
        shot.setVideoPrompt("卡通写实");
        assertEquals("doubao", router.route(shot));
    }

    @Test
    void route_emptyStrings_returnsNull() {
        Shot shot = new Shot();
        shot.setVideoPrompt("");
        shot.setDescription("");
        assertNull(router.route(shot));
    }
}
