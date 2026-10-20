#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "docseek/searcher.h"

#include <sqlite3.h>

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace {

// 拼接所有 token，用于验证无空白原文可还原。
std::string joinTokens(const std::vector<std::string>& tokens) {
    std::string joined;
    for (const std::string& t : tokens) {
        joined += t;
    }
    return joined;
}

}  // namespace

// 元宇宙：新词，验证保守不变量并记录真实切分事实。
TEST(TokenizerNeologismR2, Metaverse) {
    const std::string text = "元宇宙概念很火";
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing: " << docseek::jiebaInitError();
    }
    std::vector<std::string> tokens;
    jieba->CutForSearch(text, tokens);
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
    EXPECT_EQ(joinTokens(tokens), text);
    // 事实：CutForSearch("元宇宙概念很火") 输出 <元宇宙> <概念> <很> <火>。
    // 其中"元宇宙"是否整体切出依赖词典，仅注释记录，不做断言。
}

// 祝融号：专名，验证保守不变量并锁定稳定词。
TEST(TokenizerNeologismR2, Zhurong) {
    const std::string text = "祝融号火星车着陆成功";
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing: " << docseek::jiebaInitError();
    }
    std::vector<std::string> tokens;
    jieba->CutForSearch(text, tokens);
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
    EXPECT_EQ(joinTokens(tokens), text);
    // 事实：CutForSearch("祝融号火星车着陆成功") 输出 <祝融号> <火星> <车> <着陆> <成功>。
    // "火星"与"着陆"为稳定词，锁定其一即可。
    bool hasMars = false;
    bool hasLanding = false;
    for (const std::string& t : tokens) {
        if (t == "火星") hasMars = true;
        if (t == "着陆") hasLanding = true;
    }
    EXPECT_TRUE(hasMars || hasLanding);
}

// 十四五：政策类新词，验证保守不变量并记录真实切分事实。
TEST(TokenizerNeologismR2, FourteenthFiveYear) {
    const std::string text = "十四五规划纲要发布";
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing: " << docseek::jiebaInitError();
    }
    std::vector<std::string> tokens;
    jieba->CutForSearch(text, tokens);
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
    EXPECT_EQ(joinTokens(tokens), text);
    // 事实：CutForSearch("十四五规划纲要发布") 输出 <十四五> <规划> <纲要> <发布>。
    // "规划""纲要"为稳定词，仅注释记录，不做断言。
}

// 新冠疫苗加强针：新词，验证保守不变量并检查 token 非空。
TEST(TokenizerNeologismR2, CovidBooster) {
    const std::string text = "新冠疫苗加强针";
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing: " << docseek::jiebaInitError();
    }
    std::vector<std::string> tokens;
    jieba->CutForSearch(text, tokens);
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_GT(t.size(), 0u);
    }
    EXPECT_EQ(joinTokens(tokens), text);
    // 事实：CutForSearch("新冠疫苗加强针") 输出 <新冠> <疫苗> <加强针>。
    // "疫苗"为稳定词，仅注释记录，不做断言。
}