package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertTrue;

import com.dramafactory.model.AgentType;
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class AgentsSubtitleCountTest {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void subtitleCountMatchesAgentTypeEnum() throws Exception {
        int expected = AgentType.values().length;
        String html = read("static/agents.html");
        Matcher m = Pattern.compile("管理 (\\d+) 个专用 Agent").matcher(html);
        assertTrue(m.find(), "subtitle count not found in agents.html");
        assertTrue(Integer.parseInt(m.group(1)) == expected,
                "subtitle count must equal AgentType count, got " + m.group(1) + " expected " + expected);
        String js = read("static/agents.js");
        assertTrue(js.contains("管理 " + expected + " 个专用 Agent"), "zh subtitle count mismatch in agents.js");
        assertTrue(js.contains(expected + " dedicated Agents"), "en subtitle count mismatch in agents.js");
    }
}
