package com.dramafactory.service.prompt;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

public class PromptLibraryExtractionEdgeTest {

    private static final PromptLibraryService SERVICE = new PromptLibraryService();

    private static String call(String name, Class<?>[] types, Object... args) throws Exception {
        java.lang.reflect.Method m = PromptLibraryService.class.getDeclaredMethod(name, types);
        m.setAccessible(true);
        return (String) m.invoke(SERVICE, args);
    }

    @Test
    void title_标准一级标题() throws Exception {
        String result = call("extractTitle", new Class[]{String.class, String.class}, "# Hello World\n这是正文", "a/b.md");
        assertThat(result).isEqualTo("Hello World");
    }

    @Test
    void title_无标题回退文件名() throws Exception {
        String result = call("extractTitle", new Class[]{String.class, String.class}, "纯正文\n第二行", "dir/noname.md");
        assertThat(result).isEqualTo("noname");
    }

    @Test
    void title_二级标题不开新标题回退文件名() throws Exception {
        String result = call("extractTitle", new Class[]{String.class, String.class}, "## 二级标题\n正文", "dir/sub.md");
        assertThat(result).isEqualTo("sub");
    }

    @Test
    void title_空标题回退文件名() throws Exception {
        String result = call("extractTitle", new Class[]{String.class, String.class}, "#   \n正文", "dir/empty-title.md");
        assertThat(result).isEqualTo("empty-title");
    }

    @Test
    void title_首个一级标题获胜() throws Exception {
        String result = call("extractTitle", new Class[]{String.class, String.class}, "# 第一\n# 第二\n正文", "x.md");
        assertThat(result).isEqualTo("第一");
    }

    @Test
    void title_BOM头导致回退() throws Exception {
        String result = call("extractTitle", new Class[]{String.class, String.class}, "\uFEFF# BOM标题\n正文", "dir/bom.md");
        assertThat(result).isEqualTo("bom");
    }

    @Test
    void title_CRLF行尾() throws Exception {
        String result = call("extractTitle", new Class[]{String.class, String.class}, "# 标题\r\n正文\r\n", "dir/crlf.md");
        assertThat(result).isEqualTo("标题");
    }

    @Test
    void title_标题行前后空格被trim() throws Exception {
        String result = call("extractTitle", new Class[]{String.class, String.class}, "   #   前后空格   \n正文", "d.md");
        assertThat(result).isEqualTo("前后空格");
    }

    @Test
    void title_中文标题() throws Exception {
        String result = call("extractTitle", new Class[]{String.class, String.class}, "# 中文标题测试\n正文", "dir/cn.md");
        assertThat(result).isEqualTo("中文标题测试");
    }

    @Test
    void summary_首段摘要() throws Exception {
        String result = call("extractSummary", new Class[]{String.class}, "# T\n\n这是第一段摘要。\n\n第二段。");
        assertThat(result).isEqualTo("这是第一段摘要。");
    }

    @Test
    void summary_超长截断() throws Exception {
        String result = call("extractSummary", new Class[]{String.class}, "# T\n\n" + "a".repeat(250));
        assertThat(result).hasSize(200);
        assertThat(result).isEqualTo("a".repeat(200));
    }

    @Test
    void summary_标题后直接跟二级标题则无摘要() throws Exception {
        String result = call("extractSummary", new Class[]{String.class}, "# T\n\n## 二级\n正文");
        assertThat(result).isEqualTo("");
    }

    @Test
    void summary_只有标题无正文() throws Exception {
        String result = call("extractSummary", new Class[]{String.class}, "# T");
        assertThat(result).isEqualTo("");
    }

    @Test
    void summary_从未出现标题行() throws Exception {
        String result = call("extractSummary", new Class[]{String.class}, "无标题正文\n第二行");
        assertThat(result).isEqualTo("");
    }

    @Test
    void summary_多行合并一段() throws Exception {
        String result = call("extractSummary", new Class[]{String.class}, "# T\n\n第一段第一行\n第一段第二行\n\n第二段");
        assertThat(result).isEqualTo("第一段第一行 第一段第二行");
    }

    @Test
    void summary_多余空白压缩() throws Exception {
        String result = call("extractSummary", new Class[]{String.class}, "# T\n\n  第一   段  \n\nx");
        assertThat(result).isEqualTo("第一 段");
    }

    @Test
    void summary_CRLF摘要() throws Exception {
        String result = call("extractSummary", new Class[]{String.class}, "# T\r\n\r\n第一段\r\n\r\n第二段");
        assertThat(result).isEqualTo("第一段");
    }

    @Test
    void summary_标题前的前言被忽略() throws Exception {
        String result = call("extractSummary", new Class[]{String.class}, "前言第一行\n前言第二行\n# T\n\n摘要正文。");
        assertThat(result).isEqualTo("摘要正文。");
    }

    @Test
    void source_子目录() throws Exception {
        String result = call("extractSource", new Class[]{String.class}, "a/b.md");
        assertThat(result).isEqualTo("a");
    }

    @Test
    void source_根目录文件() throws Exception {
        String result = call("extractSource", new Class[]{String.class}, "root.md");
        assertThat(result).isEqualTo("根目录");
    }

    @Test
    void source_深层子目录() throws Exception {
        String result = call("extractSource", new Class[]{String.class}, "a/b/c.md");
        assertThat(result).isEqualTo("a");
    }

    @Test
    void source_中文目录() throws Exception {
        String result = call("extractSource", new Class[]{String.class}, "中文/文件.md");
        assertThat(result).isEqualTo("中文");
    }

    @Test
    void buildId_多级路径() throws Exception {
        String result = call("buildId", new Class[]{String.class}, "a/b/c.md");
        assertThat(result).isEqualTo("a__b__c");
    }

    @Test
    void buildId_大写MD后缀() throws Exception {
        String result = call("buildId", new Class[]{String.class}, "dir/中文路径.MD");
        assertThat(result).isEqualTo("dir__中文路径");
    }

    @Test
    void buildId_简单文件名() throws Exception {
        String result = call("buildId", new Class[]{String.class}, "plain.md");
        assertThat(result).isEqualTo("plain");
    }

    @Test
    void buildId_无后缀路径() throws Exception {
        String result = call("buildId", new Class[]{String.class}, "a/b");
        assertThat(result).isEqualTo("a__b");
    }

    @Test
    void fileNameWithoutExt_多级路径() throws Exception {
        String result = call("fileNameWithoutExt", new Class[]{String.class}, "a/b/c.md");
        assertThat(result).isEqualTo("c");
    }

    @Test
    void fileNameWithoutExt_大写MD后缀() throws Exception {
        String result = call("fileNameWithoutExt", new Class[]{String.class}, "README.MD");
        assertThat(result).isEqualTo("README");
    }

    @Test
    void fileNameWithoutExt_无后缀() throws Exception {
        String result = call("fileNameWithoutExt", new Class[]{String.class}, "noext");
        assertThat(result).isEqualTo("noext");
    }

    @Test
    void fileNameWithoutExt_混合大小写后缀() throws Exception {
        String result = call("fileNameWithoutExt", new Class[]{String.class}, "dir/UPPER.Md");
        assertThat(result).isEqualTo("UPPER");
    }
}
