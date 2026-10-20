#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "docseek/searcher.h"

#include <cstdint>
#include <string>
#include <vector>

namespace {

bool containsToken(const std::vector<std::string>& tokens, const std::string& want) {
    for (const std::string& t : tokens) {
        if (t == want) return true;
    }
    return false;
}

std::string joinTokens(const std::vector<std::string>& tokens) {
    std::string joined;
    for (const std::string& t : tokens) {
        joined += t;
    }
    return joined;
}

}  // namespace

TEST(TokenizerTradR2, InfoRetrievalTech) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dictionary unavailable";
    }
    const std::string text = "資訊檢索技術";
    std::vector<std::string> tokens;
    jieba->CutForSearch(text, tokens);
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
    EXPECT_EQ(joinTokens(tokens), text);
    EXPECT_TRUE(containsToken(tokens, "資訊"));
    EXPECT_TRUE(containsToken(tokens, "檢索"));
}

TEST(TokenizerTradR2, TraditionalChineseTest) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dictionary unavailable";
    }
    const std::string text = "繁體中文測試";
    std::vector<std::string> tokens;
    jieba->CutForSearch(text, tokens);
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
    EXPECT_EQ(joinTokens(tokens), text);
    EXPECT_TRUE(containsToken(tokens, "中文"));
}

TEST(TokenizerTradR2, EndToEndSearchTradChinese) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dictionary unavailable";
    }
    docseek::Database db = docseek::Database::open(":memory:");
    const std::string body = "本文件介紹資訊檢索的基本概念與方法。";
    db.upsert("/virtual/doc-trad-1", "資訊檢索入門", body, 0, 0);
    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("資訊檢索", 10);
    EXPECT_FALSE(hits.empty());
    bool hit = false;
    for (const docseek::Hit& h : hits) {
        if (h.path == "/virtual/doc-trad-1") {
            hit = true;
        }
    }
    EXPECT_TRUE(hit);
}