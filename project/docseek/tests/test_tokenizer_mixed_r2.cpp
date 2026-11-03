#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"

#include <sqlite3.h>

#include <algorithm>
#include <cctype>
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

// 所有 token 拼接后是否等于原文（无空白原文的还原性检查）。
bool concatEquals(const std::vector<std::string>& tokens, const std::string& text) {
    std::string joined;
    for (const std::string& t : tokens) {
        joined += t;
    }
    return joined == text;
}

// 是否存在按 ASCII 折叠后等于 want 的 token（大小写不敏感）。
bool hasAsciiFoldedToken(const std::vector<std::string>& tokens, const std::string& want) {
    std::string wantFolded;
    for (char c : want) {
        wantFolded.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    for (const std::string& t : tokens) {
        std::string folded;
        for (char c : t) {
            folded.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
        }
        if (folded == wantFolded) return true;
    }
    return false;
}

}  // namespace

// 中英数字混排：iPhone15 + 发布会 + 数字日期
TEST(TokenizerMixedR2, Iphone15Launch) {
    const std::string text = "iPhone15发布会定档9月";
    std::vector<std::string> tokens = cutForSearchR2(text);
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
    EXPECT_TRUE(concatEquals(tokens, text));
    // 事实: 实际切分为 <iPhone> <15> <发布会> <定档> <9> <月>。
    EXPECT_TRUE(hasAsciiFoldedToken(tokens, "iphone"));
    EXPECT_TRUE(hasAsciiFoldedToken(tokens, "15"));
}

// 中英混排：英文词 ChatGPT 应保持整体不断裂
TEST(TokenizerMixedR2, ChatgptWeekly) {
    const std::string text = "用ChatGPT写周报";
    std::vector<std::string> tokens = cutForSearchR2(text);
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
    // 事实: 实际切分为 <用> <ChatGPT> <写> <周报>，ChatGPT 整体保留。
    EXPECT_TRUE(hasAsciiFoldedToken(tokens, "chatgpt"));
}

// 中英混排：KPI + 中文词
TEST(TokenizerMixedR2, KpiAssessment) {
    const std::string text = "KPI考核";
    std::vector<std::string> tokens = cutForSearchR2(text);
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
    EXPECT_TRUE(concatEquals(tokens, text));
    // 事实: 实际切分为 <KPI> <考核>。
    EXPECT_TRUE(hasAsciiFoldedToken(tokens, "kpi"));
}

// 交替字母数字：a1b2c3 + 中文
TEST(TokenizerMixedR2, AlnumAlternating) {
    const std::string text = "a1b2c3混合";
    std::vector<std::string> tokens = cutForSearchR2(text);
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
    EXPECT_TRUE(concatEquals(tokens, text));
    // 事实: 实际切分为 <a1b2c3> <混合>。
    EXPECT_TRUE(hasAsciiFoldedToken(tokens, "a1b2c3"));
}