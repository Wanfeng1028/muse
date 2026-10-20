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

bool containsPath(const std::vector<docseek::Hit>& hits, const std::string& want) {
    for (const auto& h : hits) {
        if (h.path == want) return true;
    }
    return false;
}

}  // namespace

TEST(TokenizerPhraseR2, QuotedPhraseHitsDocA) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) GTEST_SKIP();
    std::string dir = makeTempDir("phrase_r2_a");
    docseek::Database db = docseek::Database::open(dir + "/test.db");
    db.upsert(dir + "/docA", "docA", "全文检索是一门技术", 1000, 11);
    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("\"全文检索\"", 10);
    EXPECT_TRUE(containsPath(hits, dir + "/docA"));
}

TEST(TokenizerPhraseR2, QuotedPhraseExcludesDocB) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) GTEST_SKIP();
    std::string dir = makeTempDir("phrase_r2_b");
    docseek::Database db = docseek::Database::open(dir + "/test.db");
    db.upsert(dir + "/docB", "docB", "全文的检索技术很复杂", 1000, 11);
    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("\"全文检索\"", 10);
    EXPECT_FALSE(containsPath(hits, dir + "/docB"));
}

TEST(TokenizerPhraseR2, UnquotedMatchesBoth) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) GTEST_SKIP();
    std::string dir = makeTempDir("phrase_r2_c");
    docseek::Database db = docseek::Database::open(dir + "/test.db");
    db.upsert(dir + "/docA", "docA", "全文检索是一门技术", 1000, 11);
    db.upsert(dir + "/docB", "docB", "全文的检索技术很复杂", 1000, 11);
    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("全文检索", 10);
    EXPECT_TRUE(containsPath(hits, dir + "/docA"));
    EXPECT_TRUE(containsPath(hits, dir + "/docB"));
}

TEST(TokenizerPhraseR2, EmptyQuotesNoThrow) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) GTEST_SKIP();
    std::string dir = makeTempDir("phrase_r2_d");
    docseek::Database db = docseek::Database::open(dir + "/test.db");
    db.upsert(dir + "/docA", "docA", "全文检索是一门技术", 1000, 11);
    docseek::Searcher searcher(db);
    EXPECT_NO_THROW({
        std::vector<docseek::Hit> hits = searcher.search("\"\"", 10);
        (void)hits;
    });
}