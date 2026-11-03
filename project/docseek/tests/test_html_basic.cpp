// tests/test_html_basic.cpp
// 文溯 DocSeek —— HtmlExtractor 基础行为单元测试（纯内存，无文件 IO）。
// 覆盖：title/description 提取、script/style/noscript 剔除、块级换行、行内不换行、
//       注释剔除、缺省 title、空白折叠、<br> 换行、标题块换行。

#include <gtest/gtest.h>

#include <string>

#include "docseek/html_extractor.h"

namespace {

using docseek::HtmlExtracted;
using docseek::HtmlExtractor;

// 1. title 与 description 的精确提取
TEST(HtmlBasic, TitleAndDescription) {
    const std::string html =
        "<html><head><title>文溯 DocSeek</title>"
        "<meta name=\"description\" content=\"本地全文检索\">"
        "</head><body><p>正文</p></body></html>";

    const HtmlExtracted out = HtmlExtractor::extract(html);

    EXPECT_EQ(out.title, "文溯 DocSeek");
    EXPECT_EQ(out.description, "本地全文检索");
}

// 2. script/style/noscript 内容不得进入 text
TEST(HtmlBasic, ScriptStyleRemoved) {
    const std::string html =
        "<script>var x=1;</script>"
        "<style>.a{color:red}</style>"
        "<noscript>noscript 文本</noscript>"
        "<p>正文</p>";

    const HtmlExtracted out = HtmlExtractor::extract(html);

    EXPECT_EQ(out.text, "正文");
}

// 3. 块级标签产生换行，行内标签不产生换行
TEST(HtmlBasic, BlockNewlines) {
    const HtmlExtracted p =
        HtmlExtractor::extract("<p>第一段</p><p>第二段</p>");
    // 闭合块级标签之间按设计保留空行（连续换行最多压成 2 个，见 docs/HTML_EXTRACTION.md）
    EXPECT_EQ(p.text, "第一段\n\n第二段");

    const HtmlExtracted d =
        HtmlExtractor::extract("<div>a</div><div>b</div>");
    EXPECT_EQ(d.text, "a\n\nb");

    const HtmlExtracted inline_case =
        HtmlExtractor::extract("<p>a<b>加粗</b>b</p>");
    EXPECT_EQ(inline_case.text, "a加粗b");
}

// 4. HTML 注释内容被剔除
TEST(HtmlBasic, CommentRemoved) {
    const HtmlExtracted out =
        HtmlExtractor::extract("<!-- 这是注释 --><p>文本</p>");

    EXPECT_EQ(out.text, "文本");
}

// 5. 无 <title> 时 title 为空串
TEST(HtmlBasic, NoTitle) {
    const HtmlExtracted out = HtmlExtractor::extract("<p>只有正文</p>");

    EXPECT_EQ(out.title, "");
}

// 6. 连续空白折叠为单个空格，并去除首尾空白
TEST(HtmlBasic, WhitespaceCollapse) {
    const HtmlExtracted out = HtmlExtractor::extract("<p>  a   b  </p>");

    EXPECT_EQ(out.text, "a b");
}

// 7. <br> 产生换行
TEST(HtmlBasic, BrTag) {
    const HtmlExtracted out = HtmlExtractor::extract("<p>a<br>b</p>");

    EXPECT_EQ(out.text, "a\nb");
}

// 8. 标题与段落之间为换行
TEST(HtmlBasic, HeadingBlock) {
    const HtmlExtracted out =
        HtmlExtractor::extract("<h1>标题</h1><p>段落</p>");

    // 闭合块级标签之间保留空行（见 docs/HTML_EXTRACTION.md 换行压缩规则）
    EXPECT_EQ(out.text, "标题\n\n段落");
}

}  // namespace
