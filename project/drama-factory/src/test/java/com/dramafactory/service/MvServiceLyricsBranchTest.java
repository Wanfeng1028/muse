package com.dramafactory.service;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MvServiceLyricsBranchTest {

    @Autowired
    private MvService mvService;

    @MockBean
    private MvLyricsService mvLyricsService;

    @MockBean
    private com.dramafactory.service.byok.ByokGenerateService byokGenerateService;

    private Object invokePrivate(String name, Class<?>[] types, Object... args) throws Exception {
        Method m = MvService.class.getDeclaredMethod(name, types);
        m.setAccessible(true);
        // MvService 是 @Transactional CGLIB 代理：私有方法反射必须打在 target 上，
        // 直接打在代理实例上会读到代理自身未初始化的 null 字段。
        Object target = org.springframework.test.util.AopTestUtils.getTargetObject(mvService);
        try {
            return m.invoke(target, args);
        } catch (InvocationTargetException e) {
            Throwable c = e.getCause();
            if (c instanceof RuntimeException re) {
                throw re;
            }
            throw new RuntimeException(c);
        }
    }

    @Test
    void lyrics_emptyText_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.buildLyricsJsonFromText("t", " \n "));
        assertTrue(ex.getMessage().contains("歌词文本为空"),
                "异常消息应包含 '歌词文本为空'，实际: " + ex.getMessage());
    }

    @Test
    void lyrics_blankLineGrouping() throws Exception {
        String json = mvService.buildLyricsJsonFromText("t", "第一段第一行\n\n第二段第一行");
        assertNotNull(json);
        assertTrue(json.contains("\"name\":\"段落 1\""), "应包含段落 1，实际: " + json);
        assertTrue(json.contains("\"name\":\"段落 2\""), "应包含段落 2，实际: " + json);
    }

    @Test
    void lyrics_fourLineGrouping() throws Exception {
        String json = mvService.buildLyricsJsonFromText("t", "l1\nl2\nl3\nl4\nl5");
        assertNotNull(json);
        assertTrue(json.contains("\"name\":\"段落 1\""), "应包含段落 1，实际: " + json);
        assertTrue(json.contains("\"name\":\"段落 2\""), "应包含段落 2（4+1 两段），实际: " + json);
    }

    @Test
    void lyrics_nullTitle_emptyTitle() throws Exception {
        String json = mvService.buildLyricsJsonFromText(null, "只有一行");
        assertNotNull(json);
        assertTrue(json.contains("\"title\":\"\""), "null title 应序列化为空串，实际: " + json);
    }

    @Test
    void lyrics_singleLine_estSeconds4() throws Exception {
        String json = mvService.buildLyricsJsonFromText("t", "只有一行");
        assertNotNull(json);
        assertTrue(json.contains("\"estSeconds\":4"), "单行段落 estSeconds 应为 4，实际: " + json);
    }

    @Test
    void truncate_null_returnsNull() throws Exception {
        Object r = invokePrivate("truncate", new Class<?>[]{String.class}, (Object) null);
        assertNull(r, "truncate(null) 应返回 null");
    }

    @Test
    void truncate_long_truncatesTo500() throws Exception {
        String input = "x".repeat(600);
        Object r = invokePrivate("truncate", new Class<?>[]{String.class}, input);
        assertNotNull(r);
        assertTrue(r instanceof String);
        assertEquals(500, ((String) r).length(), "超过 500 应截断为 500");
    }

    @Test
    void findStep_nullRunId_throws() throws Exception {
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> invokePrivate("findStep", new Class<?>[]{Long.class, int.class}, null, 1));
        assertTrue(ex.getMessage().contains("Run 未关联"),
                "异常消息应包含 'Run 未关联'，实际: " + ex.getMessage());
    }

    @Test
    void findStep_missingStep_throws() throws Exception {
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> invokePrivate("findStep", new Class<?>[]{Long.class, int.class}, 999999L, 9));
        assertTrue(ex.getMessage().contains("步骤不存在"),
                "异常消息应包含 '步骤不存在'，实际: " + ex.getMessage());
    }
}
