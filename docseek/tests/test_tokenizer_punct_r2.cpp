#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"

#include <sqlite3.h>

#include <string>
#include <vector>

namespace {

// 直接调用进程级 Jieba 单例做分词。若词典初始化失败则返回空 vector。
std::vector<std::string> cutForSearchR2(const std::string& text) {
    std::vector<std::string> words;
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        return words;
    }
    jieba->CutForSearch(text, words);
    return words;
}

// 检查任意 token 是否包含指定子串。
bool anyTokenContains(const std::vector<std::string>& tokens, const std::string& needle) {
    for (const std::string& t : tokens) {
        if (t.find(needle) != std::string::npos) return true;
    }
    return false;
}

// 拼接所有 token。
std::string joinTokens(const std::vector<std::string>& tokens) {
    std::string out;
    for (const std::string& t : tokens) {
        out += t;
    }
    return out;
}

}  // namespace

// CJK 逗号/叹号/句号不应作为独立 token 或粘连在词内出现
TEST(TokenizerPunctR2, NoCjkPunctInsideTokens) {
    const std::string text = "你好，世界！今天天气不错。";
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dict missing: " << docseek::jiebaInitError();
    }
    std::vector<std::string> tokens = cutForSearchR2(text);
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_EQ(t.find("，"), std::string::npos) << "token contains CJK comma: " << t;
        EXPECT_EQ(t.find("！"), std::string::npos) << "token contains CJK exclam: " << t;
        EXPECT_EQ(t.find("。"), std::string::npos) << "token contains CJK period: " << t;
    }
}

// 问号句：拼接长度不超过原文长度，且每个 token 非空
TEST(TokenizerPunctR2, QuestionSentenceConservative) {
    const std::string text = "全文检索，真的有用吗？";
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dict missing: " << docseek::jiebaInitError();
    }
    std::vector<std::string> tokens = cutForSearchR2(text);
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
    // 事实：CutForSearch 输出 <全文> <检索> <，> <真的> <有用> <吗> <？>
    EXPECT_TRUE(anyTokenContains(tokens, "全文"));
    EXPECT_TRUE(anyTokenContains(tokens, "检索"));
    EXPECT_LE(joinTokens(tokens).size(), text.size());
}

// 全角冒号/括号不应出现在任何 token 内
TEST(TokenizerPunctR2, FullwidthColonParenAbsent) {
    const std::string text = "价格：100元（特价）";
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dict missing: " << docseek::jiebaInitError();
    }
    std::vector<std::string> tokens = cutForSearchR2(text);
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_EQ(t.find("："), std::string::npos) << "token contains fullwidth colon: " << t;
        EXPECT_EQ(t.find("（"), std::string::npos) << "token contains fullwidth lparen: " << t;
        EXPECT_EQ(t.find("）"), std::string::npos) << "token contains fullwidth rparen: " << t;
    }
    // 事实：数字 100 保持为一个 token
    EXPECT_TRUE(anyTokenContains(tokens, "100"));
}

// 纯 ASCII 标点输入不应崩溃，且切分结果非空
TEST(TokenizerPunctR2, AsciiPunctNoThrow) {
    const std::string text = "a,b;c:d";
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dict missing: " << docseek::jiebaInitError();
    }
    std::vector<std::string> tokens;
    EXPECT_NO_THROW({
        tokens = cutForSearchR2(text);
    });
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
    // 事实：a,b,c,d 各成 token，标点被丢弃
    EXPECT_TRUE(anyTokenContains(tokens, "a"));
    EXPECT_TRUE(anyTokenContains(tokens, "b"));
}
