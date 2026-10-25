package com.dramafactory.web;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertFalse;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;
import java.nio.charset.StandardCharsets;
import java.util.regex.Pattern;

public class CostLedgerTrendColorTest {

    @Test
    void trendSvgHasNoHardcodedColors() throws Exception {
        String js = StreamUtils.copyToString(
                new ClassPathResource("static/cost-ledger.js").getInputStream(),
                StandardCharsets.UTF_8
        );

        Pattern strokeHex = Pattern.compile("stroke=\"#[0-9a-fA-F]{6}\"");
        Pattern fillHex = Pattern.compile("fill=\"#[0-9a-fA-F]{6}\"");

        assertFalse(strokeHex.matcher(js).find(), "JS must not contain hardcoded stroke hex colors");
        assertFalse(fillHex.matcher(js).find(), "JS must not contain hardcoded fill hex colors");
    }

    @Test
    void designCssCoversTrendColorRoles() throws Exception {
        String css = StreamUtils.copyToString(
                new ClassPathResource("static/cost-ledger-design-v1.css").getInputStream(),
                StandardCharsets.UTF_8
        );

        assertTrue(css.contains("#trendChart line"), "CSS must define #trendChart line");
        assertTrue(css.contains("#trendChart polyline:first-of-type"), "CSS must define #trendChart polyline:first-of-type");
        assertTrue(css.contains("#trendChart polyline:last-of-type"), "CSS must define #trendChart polyline:last-of-type");
        assertTrue(css.contains("#trendChart circle"), "CSS must define #trendChart circle");
        assertTrue(css.contains("#trendChart text"), "CSS must define #trendChart text");
        assertTrue(css.contains("#trendChart g line:first-of-type"), "CSS must define #trendChart g line:first-of-type");
        assertTrue(css.contains("#trendChart g line:last-of-type"), "CSS must define #trendChart g line:last-of-type");
    }

    @Test
    void trendSvgKeepsGeometry() throws Exception {
        String js = StreamUtils.copyToString(
                new ClassPathResource("static/cost-ledger.js").getInputStream(),
                StandardCharsets.UTF_8
        );

        assertTrue(js.contains("stroke-width=\"2\""), "JS must keep stroke-width=\"2\"");
        assertTrue(js.contains("stroke-dasharray=\"5 4\""), "JS must keep stroke-dasharray=\"5 4\"");
        assertTrue(js.contains("r=\"3.5\""), "JS must keep r=\"3.5\"");
        assertTrue(js.contains("fill=\"none\""), "JS must keep fill=\"none\"");
    }

    @Test
    void designCssSizesTrendSvg() throws Exception {
        String css = StreamUtils.copyToString(
                new ClassPathResource("static/cost-ledger-design-v1.css").getInputStream(),
                StandardCharsets.UTF_8
        );

        int start = css.indexOf("#trendChart svg {");
        assertTrue(start != -1, "CSS must contain #trendChart svg { selector");

        int end = css.indexOf("}", start);
        assertTrue(end != -1, "CSS #trendChart svg { must have closing }");

        String ruleBlock = css.substring(start, end + 1);
        assertTrue(ruleBlock.contains("width: 100%"), "#trendChart svg rule must contain width: 100%");
        assertTrue(ruleBlock.contains("height: auto"), "#trendChart svg rule must contain height: auto");
    }
}