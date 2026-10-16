// tests/test_html_perf.cpp
// 用途：HtmlExtractor 的性能与边界行为单元测试。
// 覆盖大文件线性扫描耗时、空输入语义、纯文本原样返回、深层嵌套不递归爆栈。

#include <gtest/gtest.h>

#include <chrono>
#include <string>

#include "docseek/html_extractor.h"

namespace docseek {
namespace {

// 1MB 级大文件：验证线性扫描性能与内容正确性。
TEST(HtmlPerf, LargeFile) {
    std::string html;
    html.reserve(1024 * 1024 + 256);
    html += "<html><head><title>大文件</title></head><body>";
    for (int i = 0; i < 20000; ++i) {
        html += "<p>段落中文内容</p>";
    }
    html += "</body></html>";

    const auto start = std::chrono::steady_clock::now();
    const HtmlExtracted doc = HtmlExtractor::extract(html);
    const auto end = std::chrono::steady_clock::now();

    const auto elapsedMs =
        std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    EXPECT_LT(elapsedMs, 2000);
    EXPECT_EQ(doc.title, "大文件");
    EXPECT_FALSE(doc.text.empty());
    EXPECT_NE(doc.text.find("段落中文内容"), std::string::npos);
}

// 空输入：extract 全空；extractFromBytes 视为成功且 doc 全空。
TEST(HtmlPerf, EmptyInput) {
    const HtmlExtracted doc = HtmlExtractor::extract("");
    EXPECT_TRUE(doc.title.empty());
    EXPECT_TRUE(doc.description.empty());
    EXPECT_TRUE(doc.text.empty());

    const HtmlExtractResult result = HtmlExtractor::extractFromBytes("");
    EXPECT_TRUE(result.ok);
    EXPECT_TRUE(result.doc.text.empty());
}

// 无标签纯文本输入应原样返回。
TEST(HtmlPerf, PlainText) {
    const HtmlExtracted doc = HtmlExtractor::extract("hello world 纯文本");
    EXPECT_EQ(doc.text, "hello world 纯文本");
}

// 1000 层嵌套：线性扫描不递归，不应抛异常或爆栈。
TEST(HtmlPerf, DeepNesting) {
    constexpr int kDepth = 1000;
    std::string html;
    html.reserve(static_cast<std::size_t>(kDepth) * 11 + 32);
    for (int i = 0; i < kDepth; ++i) {
        html += "<div>";
    }
    html += "core";
    for (int i = 0; i < kDepth; ++i) {
        html += "</div>";
    }

    std::string text;
    EXPECT_NO_THROW({ text = HtmlExtractor::extract(html).text; });
    EXPECT_EQ(text, "core");
}

}  // namespace
}  // namespace docseek
