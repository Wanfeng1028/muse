#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"

#include <sqlite3.h>

#include <string>
#include <vector>

namespace {

// 获取切分结果，直接调用进程级 Jieba 单例。词典初始化失败返回 false。
bool cutForSearch(const std::string& text, std::vector<std::string>& words) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        return false;
    }
    jieba->CutForSearch(text, words);
    return true;
}

// 所有 token 均非空。
bool allTokensNonEmpty(const std::vector<std::string>& tokens) {
    for (const std::string& t : tokens) {
        if (t.empty()) return false;
    }
    return true;
}

}  // namespace

// 重复的"好"字：切分不崩，tokens 非空，所有 token 非空。
TEST(TokenizerRepeatR2, HaoRepeat) {
    const std::string text = "好好好好好好";
    std::vector<std::string> tokens;
    if (!cutForSearch(text, tokens)) {
        GTEST_SKIP() << "jieba dictionary unavailable: " << docseek::jiebaInitError();
    }
    // 保守不变量：不抛异常、tokens 非空、所有 token 非空。
    EXPECT_FALSE(tokens.empty());
    EXPECT_TRUE(allTokensNonEmpty(tokens));
}

// 重复的"啊"字：tokens 非空。
TEST(TokenizerRepeatR2, ARepeat) {
    const std::string text = "啊啊啊啊啊";
    std::vector<std::string> tokens;
    if (!cutForSearch(text, tokens)) {
        GTEST_SKIP() << "jieba dictionary unavailable: " << docseek::jiebaInitError();
    }
    // 保守不变量：tokens 非空。
    EXPECT_FALSE(tokens.empty());
    EXPECT_TRUE(allTokensNonEmpty(tokens));
}

// 重复的数字：tokens 非空。
TEST(TokenizerRepeatR2, DigitRepeat) {
    const std::string text = "1111111111";
    std::vector<std::string> tokens;
    if (!cutForSearch(text, tokens)) {
        GTEST_SKIP() << "jieba dictionary unavailable: " << docseek::jiebaInitError();
    }
    // 保守不变量：tokens 非空、所有 token 非空。
    EXPECT_FALSE(tokens.empty());
    EXPECT_TRUE(allTokensNonEmpty(tokens));
}