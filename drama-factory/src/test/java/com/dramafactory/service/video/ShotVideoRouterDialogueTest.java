package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

/**
 * ShotVideoRouter 对白 → minimax 路由规则测试。
 * H3 原生带立体声音轨，台词量大的分镜优先走 minimax。
 */
class ShotVideoRouterDialogueTest {

    private final ShotVideoRouter router = new ShotVideoRouter();

    @Test
    void route_substantialDialogue_returnsMinimax() {
        Shot shot = new Shot();
        shot.setDescription("两人在咖啡馆对坐");
        shot.setDialogue("你还记得我们第一次见面吗？那天下着很大的雨，你没有带伞。");
        assertEquals("minimax", router.route(shot));
    }

    @Test
    void route_shortDialogue_fallsThrough() {
        Shot shot = new Shot();
        shot.setDescription("人物点头");
        shot.setDialogue("嗯。");
        // 台词太短（<10 字符），不触发 minimax 规则，无其他风格关键词 → null
        assertNull(router.route(shot));
    }

    @Test
    void route_preferredProvider_beatsDialogue() {
        Shot shot = new Shot();
        shot.setPreferredProvider("agnes");
        shot.setDialogue("这是一段很长很长的对白，应该足够触发 minimax 规则但是被 preferred 覆盖");
        assertEquals("agnes", router.route(shot));
    }

    @Test
    void route_noDialogue_noStyle_returnsNull() {
        Shot shot = new Shot();
        shot.setDescription("空旷的走廊");
        assertNull(router.route(shot));
    }
}
