package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class TasksDesignV2Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV2AfterV1() throws Exception {
        String html = read("static/tasks.html");
        int v1 = html.indexOf("/tasks-design-v1.css");
        int v2 = html.indexOf("/tasks-design-v2.css");
        assertTrue(v1 >= 0, "missing tasks-design-v1.css link");
        assertTrue(v2 > v1, "design layer v2 must be linked after v1");
    }

    @Test
    void cssIsBalancedAndHasNoBannedDeclarations() throws Exception {
        String css = read("static/tasks-design-v2.css");
        long open = css.chars().filter(c -> c == '{').count();
        long close = css.chars().filter(c -> c == '}').count();
        assertEquals(open, close, "unbalanced braces");
        assertTrue(!css.contains("linear-gradient"), "no gradients");
        assertTrue(!css.contains("backdrop-filter"), "no glassmorphism");
        assertTrue(!css.contains("!important"), "no important");
    }

    @Test
    void cssCoversTaskRowElementsAndJsDropsInlineStyles() throws Exception {
        String css = read("static/tasks-design-v2.css");
        for (String selector : new String[]{"#taskGrid .task-row", "#taskGrid .task-top", "#taskGrid .task-left", "#taskGrid .task-status", "#taskGrid .task-name", "#taskGrid .task-progress-wrap", "#taskGrid .task-progress", "#taskGrid .task-pct", "#taskGrid .task-link", "#taskGrid .task-retry", "#taskGrid .task-meta", "#taskGrid .task-error"}) {
            assertTrue(css.contains(selector), "missing selector: " + selector);
        }
        String js = read("static/tasks.js");
        for (String cls : new String[]{"task-row", "task-top", "task-left", "task-status", "task-name", "task-progress-wrap", "task-progress", "task-pct", "task-link", "task-retry", "task-meta", "task-error"}) {
            assertTrue(js.contains(cls), "js must add class: " + cls);
        }
        for (String inline : new String[]{"row.style.borderBottom", "name.style.fontSize", "progress.style.width = \"120px\"", "pct.style.fontFamily", "meta.style.fontSize", "err.style.color"}) {
            assertTrue(!js.contains(inline), "js must not keep inline style: " + inline);
        }
        assertTrue(js.contains("bar.style.width = statusProgressWidth(task.status)"), "dynamic bar width stays inline");
    }
}
