#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "sqlite3.h"

#include <string>
#include <vector>

namespace {

std::vector<std::string> cutForSearch(const std::string& text) {
    std::vector<std::string> words;
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        return words;
    }
    jieba->CutForSearch(text, words);
    return words;
}

bool allTokensNonEmpty(const std::vector<std::string>& tokens) {
    for (const std::string& t : tokens) {
        if (t.empty()) return false;
    }
    return true;
}

std::string concatTokens(const std::vector<std::string>& tokens) {
    std::string joined;
    for (const std::string& t : tokens) {
        joined += t;
    }
    return joined;
}

bool containsToken(const std::vector<std::string>& tokens, const std::string& want) {
    for (const std::string& t : tokens) {
        if (t == want) return true;
    }
    return false;
}

}  // namespace

TEST(TokenizerSingletonR2, InstanceIsNonNull) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dict missing: " << docseek::jiebaInitError();
    }
    EXPECT_NE(jieba, nullptr);
}

TEST(TokenizerSingletonR2, InitErrorEmptyWhenReady) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dict missing: " << docseek::jiebaInitError();
    }
    EXPECT_TRUE(docseek::jiebaInitError().empty());
}

TEST(TokenizerSingletonR2, InstanceIsStableSingleton) {
    const cppjieba::Jieba* first = docseek::jiebaInstance();
    if (first == nullptr) {
        GTEST_SKIP() << "jieba dict missing: " << docseek::jiebaInitError();
    }
    const cppjieba::Jieba* second = docseek::jiebaInstance();
    EXPECT_EQ(first, second);

    std::vector<std::string> tokens = cutForSearch("jieba单例测试2024");
    ASSERT_FALSE(tokens.empty());
    EXPECT_TRUE(allTokensNonEmpty(tokens));
    EXPECT_EQ(concatTokens(tokens), "jieba单例测试2024");
    // 事实：英文串 jieba 整体保留为一个 token。
    EXPECT_TRUE(containsToken(tokens, "jieba"));
    // 事实：连续数字 2024 整体保留为一个 token。
    EXPECT_TRUE(containsToken(tokens, "2024"));
}