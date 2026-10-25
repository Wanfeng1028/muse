package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class TasksDesignV3Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesV3AfterV2() throws Exception {
        String html = read("static/tasks.html");
        int v2 = html.indexOf("/tasks-design-v2.css");
        int v3 = html.indexOf("/tasks-design-v3.css");
        assertTrue(v2 >= 0, "missing v2 link");
        assertTrue(v3 > v2, "v3 must be linked after v2");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/tasks-design-v3.css");
        assertEquals(1, css.chars().filter(c -> c == '{').count(), "expected 1 rule");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        assertTrue(css.contains(".task-filter-field"), "missing selector");
        assertTrue(css.contains("min-width: 160px"), "missing min-width value");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
    }

    @Test
    void htmlMigrated() throws Exception {
        String html = read("static/tasks.html");
        assertTrue(!html.contains("min-width:160px"), "old inline min-width still present");
        assertEquals(3, html.split("task-filter-field", -1).length - 1, "expected 3 filter-field divs");
        assertTrue(html.contains("style=\"display:none;\""), "hint toggle must stay inline");
    }
}
