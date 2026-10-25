package com.dramafactory.web;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RunsDesignV3Test {

    private String readStatic(String fileName) throws IOException {
        ClassPathResource resource = new ClassPathResource("static/" + fileName);
        try (InputStream in = resource.getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    private String ruleBody(String css, int selectorStart) {
        int open = css.indexOf('{', selectorStart);
        int close = css.indexOf('}', open);
        return css.substring(open, close + 1);
    }

    @Test
    void runsHtmlReferencesV3CssAfterV2Css() throws IOException {
        String html = readStatic("runs.html");
        int v2 = html.indexOf("/runs-design-v2.css");
        int v3 = html.indexOf("/runs-design-v3.css");
        assertTrue(v2 >= 0, "runs.html 应引用 /runs-design-v2.css");
        assertTrue(v3 >= 0, "runs.html 应引用 /runs-design-v3.css");
        assertTrue(v3 > v2, "/runs-design-v3.css 必须在 /runs-design-v2.css 之后被引用");
    }

    @Test
    void runsDesignV3CssHasExactlyTwoBalancedRulesWithoutBannedWords() throws IOException {
        String css = readStatic("runs-design-v3.css");

        int openCount = 0;
        int closeCount = 0;
        int depth = 0;
        for (int i = 0; i < css.length(); i++) {
            char c = css.charAt(i);
            if (c == '{') {
                openCount++;
                depth++;
            } else if (c == '}') {
                closeCount++;
                depth--;
            }
            assertTrue(depth >= 0, "CSS 花括号必须平衡");
        }
        assertEquals(2, openCount, "runs-design-v3.css 必须恰好包含 2 条规则");
        assertEquals(2, closeCount, "runs-design-v3.css 必须恰好包含 2 条规则");
        assertEquals(0, depth, "CSS 花括号必须平衡");

        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertFalse(css.contains(banned), "不允许出现禁用词: " + banned);
        }

        int wizard = css.indexOf("#wizard .card-title svg");
        assertTrue(wizard >= 0, "必须包含 #wizard .card-title svg 规则");
        String wizardRule = ruleBody(css, wizard);
        assertTrue(wizardRule.contains("15px"), "#wizard .card-title svg 规则必须包含 15px");
        assertTrue(wizardRule.contains("-2px"), "#wizard .card-title svg 规则必须包含 -2px");

        int planArea = css.indexOf("#planArea");
        assertTrue(planArea >= 0, "必须包含 #planArea 规则");
        String planRule = ruleBody(css, planArea);
        assertTrue(planRule.contains("margin-top: 16px"), "#planArea 规则必须包含 margin-top: 16px");
    }

    @Test
    void runsHtmlNoLongerContainsInlinedSvgAndPlanStyles() throws IOException {
        String html = readStatic("runs.html");
        assertFalse(html.contains("width:15px;height:15px;vertical-align:-2px"),
                "runs.html 不应再内联 width:15px;height:15px;vertical-align:-2px");
        assertFalse(html.contains("margin-top:16px"),
                "runs.html 不应再内联 margin-top:16px");
    }
}
