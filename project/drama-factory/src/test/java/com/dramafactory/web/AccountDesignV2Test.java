package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class AccountDesignV2Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV2AfterV1() throws Exception {
        String html = read("static/account.html");
        int v1 = html.indexOf("/account-design-v1.css");
        int v2 = html.indexOf("/account-design-v2.css");
        assertTrue(v1 >= 0, "missing account-design-v1.css link");
        assertTrue(v2 > v1, "design layer v2 must be linked after v1");
    }

    @Test
    void cssIsBalancedAndHasNoBannedDeclarations() throws Exception {
        String css = read("static/account-design-v2.css");
        long open = css.chars().filter(c -> c == '{').count();
        long close = css.chars().filter(c -> c == '}').count();
        assertEquals(open, close, "unbalanced braces");
        assertTrue(!css.contains("linear-gradient"), "no gradients");
        assertTrue(!css.contains("backdrop-filter"), "no glassmorphism");
        assertTrue(!css.contains("!important"), "no important");
    }

    @Test
    void cssCoversLanguageTitleAndHtmlDropsInlineStyle() throws Exception {
        String css = read("static/account-design-v2.css");
        assertTrue(css.contains(".sec-name-lang"), "missing sec-name-lang selector");
        assertTrue(css.contains("margin-top: 12px"), "missing language title margin rule");
        String html = read("static/account.html");
        assertTrue(html.contains("class=\"sec-name sec-name-lang\""), "language title must carry sec-name-lang class");
        assertTrue(!html.contains("style=\"margin-top:12px\""), "language title must not keep inline margin style");
        assertTrue(html.contains("<span class=\"sec-name\" data-i18n=\"sec.email\">"), "other sec-name spans must be untouched");
    }
}
