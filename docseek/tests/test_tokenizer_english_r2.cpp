#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "docseek/searcher.h"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

#ifndef _WIN32
#include <unistd.h>
#endif

namespace {

long currentPid() {
#ifdef _WIN32
    return static_cast<long>(::GetCurrentProcessId());
#else
    return static_cast<long>(::getpid());
#endif
}

std::string makeTempDir(const std::string& name) {
    std::filesystem::path base = std::filesystem::current_path() / "test-tmp";
    std::filesystem::create_directories(base);
    std::filesystem::path dir = base / (name + "_" + std::to_string(currentPid()));
    std::filesystem::remove_all(dir);
    std::filesystem::create_directories(dir);
    return dir.string();
}

std::string toLowerAscii(const std::string& s) {
    std::string out = s;
    std::transform(out.begin(), out.end(), out.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return out;
}

bool containsTokenFolded(const std::vector<std::string>& tokens, const std::string& want) {
    const std::string wantFolded = toLowerAscii(want);
    for (const std::string& t : tokens) {
        if (toLowerAscii(t) == wantFolded) return true;
    }
    return false;
}

}  // namespace

TEST(TokenizerEnglishR2, HelloWorldLowercase) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dict missing";
    }
    std::vector<std::string> words;
    jieba->CutForSearch("hello world", words);
    EXPECT_FALSE(words.empty());
    for (const std::string& t : words) {
        EXPECT_FALSE(t.empty());
    }
    EXPECT_TRUE(containsTokenFolded(words, "hello"));
}

TEST(TokenizerEnglishR2, HelloWorldMixedCase) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dict missing";
    }
    std::vector<std::string> words;
    EXPECT_NO_THROW(jieba->CutForSearch("Hello WORLD", words));
    EXPECT_FALSE(words.empty());
    for (const std::string& t : words) {
        EXPECT_FALSE(t.empty());
    }
    EXPECT_TRUE(containsTokenFolded(words, "hello"));
}

TEST(TokenizerEnglishR2, EndToEndSearchFoldsAscii) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dict missing";
    }
    const std::string dir = makeTempDir("tokenizer_english_r2");
    const std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    const std::string path = "doc1.txt";
    const std::string title = "Hello";
    const std::string content = "world program";
    const int64_t mtime = 0;
    const int64_t size = static_cast<int64_t>(content.size());
    db.upsert(path, title, content, mtime, size);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("hello", 10);
    EXPECT_FALSE(hits.empty());
    EXPECT_EQ(hits.front().path, path);
}
