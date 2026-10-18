package com.dramafactory.service;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PromptFileServiceTest {

    @Test
    void body与render与names正常(@TempDir Path tmp) throws Exception {
        String content = "---\n" +
                "name: hello\n" +
                "version: 1.0.0\n" +
                "description: 打招呼\n" +
                "---\n" +
                "\n" +
                "你好，{{name}}！\n";
        Files.writeString(tmp.resolve("hello.md"), content);

        PromptFileService service = new PromptFileService(tmp.toString());

        assertThat(service.body("hello")).contains("你好");
        assertThat(service.render("hello", Map.of("name", "世界"))).isEqualTo("你好，世界！");
        assertThat(service.names()).contains("hello");
    }

    @Test
    void body缺失文件抛异常(@TempDir Path tmp) throws Exception {
        Files.writeString(tmp.resolve("hello.md"),
                "---\nname: hello\nversion: 1.0.0\ndescription: 打招呼\n---\n\n你好，{{name}}！\n");

        PromptFileService service = new PromptFileService(tmp.toString());

        assertThatThrownBy(() -> service.body("missing"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void 无frontmatter文件不被识别(@TempDir Path tmp) throws Exception {
        Files.writeString(tmp.resolve("bad.md"), "没有 frontmatter 的内容\n");

        PromptFileService service = new PromptFileService(tmp.toString());

        assertThat(service.names()).doesNotContain("bad");
    }
}

