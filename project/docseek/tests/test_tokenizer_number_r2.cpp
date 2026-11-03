#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "docseek/searcher.h"

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

#ifndef _WIN32
#include <unistd.h>
#endif

namespace {

long currentPidNumberR2() {
#ifdef _WIN32
    return static_cast<long>(::GetCurrentProcessId());
#else
    return static_cast<long>(::getpid());
#endif
}

std::string makeTempDirNumberR2(const std::string& name) {
    std::filesystem::path base = std::filesystem::current_path() / "test-tmp";
    std::filesystem::create_directories(base);
    std::filesystem::path dir = base / (name + "_" + std::to_string(currentPidNumberR2()));
    std::filesystem::remove_all(dir);
    std::filesystem::create_directories(dir);
    return dir.string();
}

bool containsTokenR2(const std::vector<std::string>& tokens, const std::string& want) {
    for (const std::string& t : tokens) {
        if (t == want) return true;
    }
    return false;
}

bool allTokensNonEmptyR2(const std::vector<std::string>& tokens) {
    for (const std::string& t : tokens) {
        if (t.empty()) return false;
    }
    return true;
}

std::string joinTokensR2(const std::vector<std::string>& tokens) {
    std::string out;
    for (const std::string& t : tokens) {
        out += t;
    }
    return out;
}

}  // namespace

TEST(TokenizerNumberR2, YearKaoyan) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP();
    }
    const std::string text = "2026年考研初试";
    std::vector<std::string> tokens;
    jieba->CutForSearch(text, tokens);
    ASSERT_FALSE(tokens.empty());
    EXPECT_TRUE(allTokensNonEmptyR2(tokens));
    EXPECT_EQ(joinTokensR2(tokens), text);
    EXPECT_TRUE(containsTokenR2(tokens, "2026"));
    EXPECT_TRUE(containsTokenR2(tokens, "考研"));
}

TEST(TokenizerNumberR2, PiDecimal) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP();
    }
    const std::string text = "3.14圆周率";
    std::vector<std::string> tokens;
    EXPECT_NO_THROW(jieba->CutForSearch(text, tokens));
    ASSERT_FALSE(tokens.empty());
    EXPECT_TRUE(allTokensNonEmptyR2(tokens));
    EXPECT_EQ(joinTokensR2(tokens), text);
    EXPECT_TRUE(containsTokenR2(tokens, "3.14"));
    EXPECT_TRUE(containsTokenR2(tokens, "圆周率"));
}

TEST(TokenizerNumberR2, HaoNumber) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP();
    }
    const std::string text = "第10086号";
    std::vector<std::string> tokens;
    jieba->CutForSearch(text, tokens);
    ASSERT_FALSE(tokens.empty());
    EXPECT_TRUE(allTokensNonEmptyR2(tokens));
    EXPECT_EQ(joinTokensR2(tokens), text);
    EXPECT_TRUE(containsTokenR2(tokens, "10086"));
}

TEST(TokenizerNumberR2, EndToEndSearchYear) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP();
    }
    const std::string dir = makeTempDirNumberR2("tokenizer_number_r2_e2e");
    const std::string dbPath = dir + "/test.db";

    docseek::Database db = docseek::Database::open(dbPath);

    const std::string path = "doc-number-r2-1";
    const std::string title = "初试通知";
    const std::string body = "2026年12月19日初试";
    db.upsert(path, title, body, static_cast<int64_t>(0), static_cast<int64_t>(body.size()));

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("2026", 10);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits.front().path, path);
}
