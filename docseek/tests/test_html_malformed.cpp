// tests/test_html_malformed.cpp
// 用途：针对 docseek::HtmlExtractor 的畸形/容错 HTML 输入进行单元测试。
// 覆盖嵌套标签、未闭合标签、截断输入、'<' 当普通字符、大小写混合、
// 未闭合注释、空标签名、未闭合 script 等边界场景。

#include <gtest/gtest.h>

#include <string>

#include "docseek/html_extractor.h"

namespace {

using docseek::HtmlExtracted;
using docseek::HtmlExtractor;

}  // namespace

// 1. 嵌套标签：<div><p>外层<span>内层</span>继续</p></div>
//    期望 text 精确为 "外层内层继续"。
TEST(HtmlMalformed, NestedTags) {
    const std::string html =
        "<div><p>外层<span>内层</span>继续</p></div>";
    const HtmlExtracted out = HtmlExtractor::extract(html);
    EXPECT_EQ(out.text, "外层内层继续");
}

// 2. 未闭合标签：<p>第一段<p>第二段
//    第二个 <p> 触发块级换行，期望 text 精确为 "第一段\n第二段"。
TEST(HtmlMalformed, UnclosedTags) {
    const std::string html = "<p>第一段<p>第二段";
    const HtmlExtracted out = HtmlExtractor::extract(html);
    EXPECT_EQ(out.text, "第一段\n第二段");
}

// 3. 截断输入："<div><p>abc"（结尾无 '>'）。
//    未闭合标签扫到输入结尾，期望 text 精确为 "abc"，且不抛异常、不卡死。
TEST(HtmlMalformed, TruncatedAtEnd) {
    const std::string html = "<div><p>abc";
    HtmlExtracted out;
    EXPECT_NO_THROW(out = HtmlExtractor::extract(html));
    EXPECT_EQ(out.text, "abc");
}

// 4. '<' 后跟空格：当作普通字符。
//    输入 "< 3 是小于号"，期望 text 精确为 "< 3 是小于号"。
TEST(HtmlMalformed, LtAsText) {
    const std::string html = "< 3 是小于号";
    const HtmlExtracted out = HtmlExtractor::extract(html);
    EXPECT_EQ(out.text, "< 3 是小于号");
}

// 5. 大小写混合标签：<DIV><P>大写标签</P></DIV>
//    期望 text 精确为 "大写标签"。
TEST(HtmlMalformed, MixedCase) {
    const std::string html = "<DIV><P>大写标签</P></DIV>";
    const HtmlExtracted out = HtmlExtractor::extract(html);
    EXPECT_EQ(out.text, "大写标签");
}

// 6. 未闭合注释：<p>前</p><!-- 没闭合的注释<p>后</p>
//    注释吞掉后面全部内容，期望 text 精确为 "前"。
TEST(HtmlMalformed, UnclosedComment) {
    const std::string html = "<p>前</p><!-- 没闭合的注释<p>后</p>";
    const HtmlExtracted out = HtmlExtractor::extract(html);
    EXPECT_EQ(out.text, "前");
}

// 7. 空标签名：<> 当普通字符处理。
//    期望 text 精确为 "<>"。
TEST(HtmlMalformed, EmptyTagName) {
    const std::string html = "<>";
    const HtmlExtracted out = HtmlExtractor::extract(html);
    EXPECT_EQ(out.text, "<>");
}

// 8. 未闭合 script：<script>var x = "<p>hi";（script 未闭合）
//    script 内容全部剔除，期望 text 为空串。
TEST(HtmlMalformed, ScriptUnclosed) {
    const std::string html = "<script>var x = \"<p>hi\";";
    const HtmlExtracted out = HtmlExtractor::extract(html);
    EXPECT_EQ(out.text, "");
}
