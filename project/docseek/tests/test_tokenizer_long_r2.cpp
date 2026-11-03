#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "sqlite3.h"

#include <chrono>
#include <string>
#include <vector>

namespace {

// 拼接所有 token，用于保守不变量校验（无空白原文应可完整还原）。
std::string joinTokens(const std::vector<std::string>& tokens) {
    std::string joined;
    for (const std::string& t : tokens) {
        joined += t;
    }
    return joined;
}

// 校验所有 token 均非空。
bool allTokensNonEmpty(const std::vector<std::string>& tokens) {
    for (const std::string& t : tokens) {
        if (t.empty()) return false;
    }
    return true;
}

}  // namespace

// 10 万字中文文本：CutForSearch 不抛异常，tokens 非空，且耗时 < 10 秒
TEST(TokenizerLongR2, HugeChineseText) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dictionary unavailable: " << docseek::jiebaInitError();
    }

    std::string text;
    text.reserve(14 * 5000);
    for (int i = 0; i < 5000; ++i) {
        text += "全文检索是信息检索的重要技术。";
    }

    std::vector<std::string> words;
    const auto start = std::chrono::steady_clock::now();
    ASSERT_NO_THROW(jieba->CutForSearch(text, words));
    const auto end = std::chrono::steady_clock::now();

    const auto elapsedMs =
        std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    EXPECT_FALSE(words.empty());
    EXPECT_TRUE(allTokensNonEmpty(words));
    // 事实：原文不含空白，CutForSearch 输出 token 拼接后可还原原文。
    EXPECT_EQ(joinTokens(words), text);
    // 事实：重复文本中稳定切出"全文检索"与"信息检索"。
    bool hasQuanwen = false;
    bool hasXinxi = false;
    for (const std::string& t : words) {
        if (t == "全文检索") hasQuanwen = true;
        if (t == "信息检索") hasXinxi = true;
    }
    EXPECT_TRUE(hasQuanwen);
    EXPECT_TRUE(hasXinxi);
    EXPECT_LT(elapsedMs, 10000);
}

// 1MB 纯 ASCII 文本：CutForSearch 不抛异常
TEST(TokenizerLongR2, OneMegabyteAscii) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dictionary unavailable: " << docseek::jiebaInitError();
    }

    std::string text;
    text.reserve(1024 * 1024);
    while (text.size() < 1024u * 1024u) {
        text += "abcdefghijklmnopqrstuvwxyz0123456789";
    }

    std::vector<std::string> words;
    ASSERT_NO_THROW(jieba->CutForSearch(text, words));

    EXPECT_FALSE(words.empty());
    EXPECT_TRUE(allTokensNonEmpty(words));
    // 事实：纯 ASCII 无空白文本拼接后可还原原文。
    EXPECT_EQ(joinTokens(words), text);
}

// 空字符串：CutForSearch 返回空 vector，不抛异常
TEST(TokenizerLongR2, EmptyString) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dictionary unavailable: " << docseek::jiebaInitError();
    }

    std::vector<std::string> words;
    ASSERT_NO_THROW(jieba->CutForSearch("", words));
    EXPECT_TRUE(words.empty());
    EXPECT_EQ(words.size(), 0u);
}