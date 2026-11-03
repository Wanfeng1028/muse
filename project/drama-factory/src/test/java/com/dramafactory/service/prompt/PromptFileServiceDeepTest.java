package com.dramafactory.service.prompt;

import com.dramafactory.service.PromptFileService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.Map;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.catchThrowable;
import static org.assertj.core.api.Assertions.assertThatCode;

public class PromptFileServiceDeepTest {

    @Test
    void testDirectoryNotExists(@TempDir Path tmp) {
        Path nonExistent = tmp.resolve("missing-dir");
        PromptFileService service = new PromptFileService(nonExistent.toString());
        
        assertThat(service.names()).isEmpty();
        assertThatThrownBy(() -> service.body("x"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void testBodyEmptyName(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("hello.md");
        Files.writeString(file, "---\nname: hello\nversion: 1.0\n---\nbody\n", StandardCharsets.UTF_8);
        PromptFileService service = new PromptFileService(tmp.toString());
        
        assertThatThrownBy(() -> service.body(""))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void testPathTraversalName(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("hello.md");
        Files.writeString(file, "---\nname: hello\nversion: 1.0\n---\nbody\n", StandardCharsets.UTF_8);
        PromptFileService service = new PromptFileService(tmp.toString());
        
        assertThatThrownBy(() -> service.body("../hello"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> service.body("a/b"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void testBodyWhitespaceNormalized(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("n.md");
        String content = "---\nname: n\nversion: 1.0.0\ndescription: d\n---\n\n\n\n第一行\n第二行\n\n\n";
        Files.writeString(file, content, StandardCharsets.UTF_8);
        PromptFileService service = new PromptFileService(tmp.toString());
        
        assertThat(service.body("n")).isEqualTo("第一行\n第二行");
    }

    @Test
    void testDeleteFileCacheInvalidation(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("gone.md");
        Files.writeString(file, "---\nname: gone\nversion: 1.0\n---\nbody\n", StandardCharsets.UTF_8);
        PromptFileService service = new PromptFileService(tmp.toString());
        
        assertThat(service.body("gone")).isEqualTo("body");
        
        Files.delete(file);
        
        assertThat(service.names()).doesNotContain("gone");
        assertThatThrownBy(() -> service.body("gone"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void testModifyFileAutoReload(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("v.md");
        String v1 = "---\nname: v\nversion: 1.0\n---\nv1正文\n";
        Files.writeString(file, v1, StandardCharsets.UTF_8);
        PromptFileService service = new PromptFileService(tmp.toString());
        
        assertThat(service.body("v")).isEqualTo("v1正文");
        
        long oldMtime = Files.getLastModifiedTime(file).toMillis();
        String v2 = "---\nname: v\nversion: 2.0\n---\nv2正文\n";
        Files.writeString(file, v2, StandardCharsets.UTF_8);
        Files.setLastModifiedTime(file, FileTime.fromMillis(oldMtime + 10000));
        
        assertThat(service.body("v")).isEqualTo("v2正文");
    }

    @Test
    void testSubdirectoryNotScanned(@TempDir Path tmp) throws Exception {
        Path sub = tmp.resolve("sub");
        Files.createDirectories(sub);
        Path file = sub.resolve("x.md");
        Files.writeString(file, "---\nname: x\nversion: 1.0\n---\nbody\n", StandardCharsets.UTF_8);
        PromptFileService service = new PromptFileService(tmp.toString());
        
        assertThat(service.names()).doesNotContain("x", "sub/x");
    }

    @Test
    void testDotFileSkipped(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve(".hidden.md");
        Files.writeString(file, "---\nname: hidden\nversion: 1.0\n---\nbody\n", StandardCharsets.UTF_8);
        PromptFileService service = new PromptFileService(tmp.toString());
        
        assertThat(service.names()).doesNotContain("hidden");
    }

    @Test
    void testFileNamePatternFilter(@TempDir Path tmp) throws Exception {
        // valid
        Files.writeString(tmp.resolve("a.md"), "---\nname: a\nversion: 1.0\n---\nbody\n", StandardCharsets.UTF_8);
        Files.writeString(tmp.resolve("9lives.md"), "---\nname: 9lives\nversion: 1.0\n---\nbody\n", StandardCharsets.UTF_8);
        Files.writeString(tmp.resolve("my-prompt_v2.md"), "---\nname: my-prompt_v2\nversion: 1.0\n---\nbody\n", StandardCharsets.UTF_8);
        
        // invalid
        Files.writeString(tmp.resolve("-bad.md"), "---\nname: bad\nversion: 1.0\n---\nbody\n", StandardCharsets.UTF_8);
        Files.writeString(tmp.resolve("UPPER.MD"), "---\nname: upper\nversion: 1.0\n---\nbody\n", StandardCharsets.UTF_8);
        Files.writeString(tmp.resolve("has space.md"), "---\nname: space\nversion: 1.0\n---\nbody\n", StandardCharsets.UTF_8);
        Files.writeString(tmp.resolve("note.txt"), "---\nname: note\nversion: 1.0\n---\nbody\n", StandardCharsets.UTF_8);
        
        PromptFileService service = new PromptFileService(tmp.toString());
        Set<String> names = service.names();
        
        assertThat(names).contains("a", "9lives", "my-prompt_v2");
        assertThat(names).doesNotContain("bad", "upper", "space", "note");
    }

    @Test
    void testParseFailuresSkipped(@TempDir Path tmp) throws Exception {
        // no frontmatter
        Files.writeString(tmp.resolve("plain.md"), "just plain text\n", StandardCharsets.UTF_8);
        // unclosed frontmatter
        Files.writeString(tmp.resolve("unclosed.md"), "---\nname: unclosed\n", StandardCharsets.UTF_8);
        // missing name
        Files.writeString(tmp.resolve("noname.md"), "---\nversion: 1.0\n---\nbody\n", StandardCharsets.UTF_8);
        
        PromptFileService service = new PromptFileService(tmp.toString());
        Set<String> names = service.names();
        
        assertThat(names).doesNotContain("plain", "unclosed", "noname");
    }

    @Test
    void testCrlfNotParsed(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("crlf.md");
        String content = "---\r\nname: x\r\nversion: 1.0.0\r\n---\r\n正文\r\n";
        Files.writeString(file, content, StandardCharsets.UTF_8);
        PromptFileService service = new PromptFileService(tmp.toString());
        
        assertThat(service.names()).doesNotContain("x");
    }

    @Test
    void testPromptFileRecord() {
        PromptFileService.PromptFile pf = new PromptFileService.PromptFile("n", "1.0", "d", "b");
        assertThat(pf.name()).isEqualTo("n");
        assertThat(pf.version()).isEqualTo("1.0");
        assertThat(pf.description()).isEqualTo("d");
        assertThat(pf.body()).isEqualTo("b");
        
        PromptFileService.PromptFile pf2 = new PromptFileService.PromptFile("n", "", "", "b");
        assertThat(pf2.version()).isEmpty();
        assertThat(pf2.description()).isEmpty();
    }

    @Test
    void testRenderNullVars(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("t.md");
        Files.writeString(file, "---\nname: t\nversion: 1.0\n---\nHi {{who}}!\n", StandardCharsets.UTF_8);
        PromptFileService service = new PromptFileService(tmp.toString());
        
        assertThat(service.render("t", null)).isEqualTo("Hi !");
    }

    @Test
    void testRenderEmptyMap(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("t.md");
        Files.writeString(file, "---\nname: t\nversion: 1.0\n---\nHi {{who}}!\n", StandardCharsets.UTF_8);
        PromptFileService service = new PromptFileService(tmp.toString());
        
        assertThat(service.render("t", Map.of())).isEqualTo("Hi !");
    }

    @Test
    void testRenderMissingKey(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("t.md");
        Files.writeString(file, "---\nname: t\nversion: 1.0\n---\n{{a}}-{{b}}\n", StandardCharsets.UTF_8);
        PromptFileService service = new PromptFileService(tmp.toString());
        
        assertThat(service.render("t", Map.of("a", "1"))).isEqualTo("1-");
    }

    @Test
    void testRenderDollarAndBackslash(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("t.md");
        Files.writeString(file, "---\nname: t\nversion: 1.0\n---\n价：{{k}}\n", StandardCharsets.UTF_8);
        PromptFileService service = new PromptFileService(tmp.toString());
        
        assertThat(service.render("t", Map.of("k", "$1\\path"))).isEqualTo("价：$1\\path");
    }

    @Test
    void testRenderRepeatedPlaceholder(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("t.md");
        Files.writeString(file, "---\nname: t\nversion: 1.0\n---\n{{w}} and {{w}}\n", StandardCharsets.UTF_8);
        PromptFileService service = new PromptFileService(tmp.toString());
        
        assertThat(service.render("t", Map.of("w", "你"))).isEqualTo("你 and 你");
    }

    @Test
    void testRenderKeyWithSpecialChars(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("t.md");
        Files.writeString(file, "---\nname: t\nversion: 1.0\n---\n[{{a.b-c_d}}]\n", StandardCharsets.UTF_8);
        PromptFileService service = new PromptFileService(tmp.toString());
        
        assertThat(service.render("t", Map.of("a.b-c_d", "OK"))).isEqualTo("[OK]");
    }

    @Test
    void testRenderMissingPrompt(@TempDir Path tmp) {
        PromptFileService service = new PromptFileService(tmp.toString());
        
        assertThatThrownBy(() -> service.render("missing", Map.of("k", "v")))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void testNamesReturnsCopy(@TempDir Path tmp) throws Exception {
        Files.writeString(tmp.resolve("one.md"), "---\nname: one\nversion: 1.0\n---\nbody\n", StandardCharsets.UTF_8);
        Files.writeString(tmp.resolve("two.md"), "---\nname: two\nversion: 1.0\n---\nbody\n", StandardCharsets.UTF_8);
        PromptFileService service = new PromptFileService(tmp.toString());
        
        Set<String> ns = service.names();
        assertThat(ns).containsExactlyInAnyOrder("one", "two");
        
        ns.clear();
        assertThat(service.names()).containsExactlyInAnyOrder("one", "two");
    }
}
