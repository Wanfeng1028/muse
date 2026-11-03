package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class TasksDesignV1Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerAfterAppCss() throws Exception {
        String html = read("static/tasks.html");
        int app = html.indexOf("/app.css");
        int layer = html.indexOf("/tasks-design-v1.css");
        assertTrue(app >= 0, "missing app.css link");
        assertTrue(layer > app, "design layer must be linked after app.css");
    }

    @Test
    void cssIsBalancedAndHasNoBannedDeclarations() throws Exception {
        String css = read("static/tasks-design-v1.css");
        long open = css.chars().filter(c -> c == '{').count();
        long close = css.chars().filter(c -> c == '}').count();
        assertEquals(open, close, "unbalanced braces");
        assertTrue(!css.contains("linear-gradient"), "no gradients");
        assertTrue(!css.contains("backdrop-filter"), "no glassmorphism");
        assertTrue(!css.contains("!important"), "no important");
    }

    @Test
    void cssCoversTasksPageElements() throws Exception {
        String css = read("static/tasks-design-v1.css");
        for (String selector : new String[]{".page-head h1", ".page .card", "#hint.alert", "#taskCount", "#taskGrid .py-3", "#taskGrid .status-pill", "#taskGrid .progress", "#taskGrid .progress-bar", "#taskGrid .state-empty"}) {
            assertTrue(css.contains(selector), "missing selector: " + selector);
        }
    }
}
