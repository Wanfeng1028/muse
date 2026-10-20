#include <gtest/gtest.h>
#include <sqlite3.h>
#include <string>
#include <vector>
#include "docseek/jieba_tokenizer.h"

namespace {

std::vector<std::string> cutForSearchR2(const std::string& text) {
    if (docseek::jiebaInstance() == nullptr) {
        return {};
    }
    std::vector<std::string> words;
    docseek::jiebaInstance()->CutForSearch(text, words);
    return words;
}

// CutForSearch 输出重叠词，拼接不一定还原原文；但每个 token 必为原文子串。
bool allTokensSubstrings(const std::vector<std::string>& tokens, const std::string& text) {
    for (const std::string& t : tokens) {
        if (text.find(t) == std::string::npos) return false;
    }
    return true;
}

bool concatEquals(const std::vector<std::string>& words, const std::string& original) {
    std::string joined;
    for (const auto& w : words) {
        joined += w;
    }
    return joined == original;
}

bool hasToken(const std::vector<std::string>& words, const std::string& token) {
    for (const auto& w : words) {
        if (w == token) {
            return true;
        }
    }
    return false;
}

size_t countToken(const std::vector<std::string>& words, const std::string& token) {
    size_t count = 0;
    for (const auto& w : words) {
        if (w == token) {
            ++count;
        }
    }
    return count;
}

int ftsMatchCount(sqlite3* db, const char* matchSql) {
    sqlite3_stmt* stmt = nullptr;
    int count = -1;
    if (sqlite3_prepare_v2(db, matchSql, -1, &stmt, nullptr) == SQLITE_OK) {
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            count = sqlite3_column_int(stmt, 0);
        }
    }
    sqlite3_finalize(stmt);
    return count;
}

} // namespace

TEST(TokenizerDeepDS, CommonSentence) {
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    std::string text = "我爱北京天安门";
    auto words = cutForSearchR2(text);
    EXPECT_FALSE(words.empty());
    EXPECT_TRUE(allTokensSubstrings(words, text));
    EXPECT_TRUE(hasToken(words, "北京"));
}

TEST(TokenizerDeepDS, ProperNoun) {
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    std::string text = "中华人民共和国成立于1949年";
    auto words = cutForSearchR2(text);
    EXPECT_TRUE(hasToken(words, "中华人民共和国"));
}

TEST(TokenizerDeepDS, NumberAlphaMix) {
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    std::string text = "3C产品2026";
    auto words = cutForSearchR2(text);
    EXPECT_FALSE(words.empty());
    EXPECT_TRUE(concatEquals(words, text));
}

TEST(TokenizerDeepDS, CjkEnglishMix) {
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    std::string text = "AI技术";
    auto words = cutForSearchR2(text);
    EXPECT_TRUE(hasToken(words, "AI") || hasToken(words, "ai"));
}

TEST(TokenizerDeepDS, EmptyString) {
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    auto words = cutForSearchR2("");
    EXPECT_TRUE(words.empty());
}

TEST(TokenizerDeepDS, SingleChar) {
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    auto words = cutForSearchR2("好");
    std::vector<std::string> expected = {"好"};
    EXPECT_EQ(words, expected);
}

TEST(TokenizerDeepDS, Punctuation) {
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    std::string text = "你好，世界";
    auto words = cutForSearchR2(text);
    EXPECT_FALSE(words.empty());
    EXPECT_TRUE(concatEquals(words, text));
}

TEST(TokenizerDeepDS, AsciiFoldFts) {
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    sqlite3* db = nullptr;
    EXPECT_EQ(sqlite3_open(":memory:", &db), SQLITE_OK);
    docseek::registerJiebaTokenizer(db);
    EXPECT_EQ(sqlite3_exec(db, "CREATE VIRTUAL TABLE documents_fts USING fts5(title, content, tokenize='jieba')", nullptr, nullptr, nullptr), SQLITE_OK);
    EXPECT_EQ(sqlite3_exec(db, "INSERT INTO documents_fts(title, content) VALUES('t', '我喜欢用iPhone拍照')", nullptr, nullptr, nullptr), SQLITE_OK);
    EXPECT_EQ(ftsMatchCount(db, "SELECT count(*) FROM documents_fts WHERE documents_fts MATCH '\"iphone\"'"), 1);
    EXPECT_EQ(ftsMatchCount(db, "SELECT count(*) FROM documents_fts WHERE documents_fts MATCH '\"IPHONE\"'"), 1);
    sqlite3_close(db);
}

TEST(TokenizerDeepDS, Overlap) {
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    std::string text = "计算机技术";
    auto words = cutForSearchR2(text);
    EXPECT_TRUE(hasToken(words, "计算机"));
}

TEST(TokenizerDeepDS, Repeat) {
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    std::string text = "北京北京";
    auto words = cutForSearchR2(text);
    EXPECT_EQ(countToken(words, "北京"), 2u);
}

TEST(TokenizerDeepDS, LongText) {
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    std::string text;
    for (int i = 0; i < 5000; ++i) {
        text += "汉";
    }
    auto words = cutForSearchR2(text);
    EXPECT_TRUE(concatEquals(words, text));
}

TEST(TokenizerDeepDS, FtsEmpty) {
    if (docseek::jiebaInstance() == nullptr) {
        GTEST_SKIP() << "jieba dictionary missing";
    }
    sqlite3* db = nullptr;
    EXPECT_EQ(sqlite3_open(":memory:", &db), SQLITE_OK);
    docseek::registerJiebaTokenizer(db);
    EXPECT_EQ(sqlite3_exec(db, "CREATE VIRTUAL TABLE documents_fts USING fts5(title, content, tokenize='jieba')", nullptr, nullptr, nullptr), SQLITE_OK);
    EXPECT_EQ(ftsMatchCount(db, "SELECT count(*) FROM documents_fts WHERE documents_fts MATCH '\"北京\"'"), 0);
    sqlite3_close(db);
}