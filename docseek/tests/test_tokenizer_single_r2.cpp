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

bool containsToken(const std::vector<std::string>& tokens, const std::string& want) {
    for (const std::string& t : tokens) {
        if (t == want) return true;
    }
    return false;
}

bool hitsContainPath(const std::vector<docseek::Hit>& hits, const std::string& want) {
    for (const docseek::Hit& h : hits) {
        if (h.path == want) return true;
    }
    return false;
}

std::vector<std::string> cutForSearch(const std::string& text) {
    std::vector<std::string> words;
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        return words;
    }
    jieba->CutForSearch(text, words);
    return words;
}

void insertDocA(docseek::Database& db, const std::string& path, const std::string& content) {
    db.upsert(path, "docA", content, static_cast<int64_t>(0), static_cast<int64_t>(content.size()));
}

}  // namespace

TEST(TokenizerSingleR2, DogQueryHitsDocA) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dictionary unavailable";
    }
    std::string dir = makeTempDir("single_r2_dog");
    docseek::Database db = docseek::Database::open(dir + "/index.db");
    std::string docPath = dir + "/docA.txt";
    insertDocA(db, docPath, "狗是人类忠实的朋友");
    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("狗", 10);
    // 事实: CutForSearch("狗") 输出单 token 狗，FTS5 命中 docA。
    std::vector<std::string> tokens = cutForSearch("狗");
    EXPECT_FALSE(tokens.empty());
    EXPECT_TRUE(containsToken(tokens, "狗"));
    EXPECT_TRUE(hitsContainPath(hits, docPath));
}

TEST(TokenizerSingleR2, CatQueryMissesDocA) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dictionary unavailable";
    }
    std::string dir = makeTempDir("single_r2_cat");
    docseek::Database db = docseek::Database::open(dir + "/index.db");
    std::string docPath = dir + "/docA.txt";
    insertDocA(db, docPath, "狗是人类忠实的朋友");
    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("猫", 10);
    // 事实: 库中无含猫的文档，search 返回不含 docA。
    EXPECT_FALSE(hitsContainPath(hits, docPath));
}

TEST(TokenizerSingleR2, StopwordQueryNoThrow) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dictionary unavailable";
    }
    std::string dir = makeTempDir("single_r2_stop");
    docseek::Database db = docseek::Database::open(dir + "/index.db");
    std::string docPath = dir + "/docA.txt";
    insertDocA(db, docPath, "狗是人类忠实的朋友");
    docseek::Searcher searcher(db);
    // 事实: 的作为单字停用词，search 不抛异常即可。
    EXPECT_NO_THROW({
        std::vector<docseek::Hit> hits = searcher.search("的", 10);
        (void)hits;
    });
}

TEST(TokenizerSingleR2, JiebaInstanceAvailable) {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    if (jieba == nullptr) {
        GTEST_SKIP() << "jieba dictionary unavailable";
    }
    EXPECT_NE(jieba, nullptr);
    // 事实: 词典可用时 CutForSearch 对中文短语产出非空且 token 非空。
    std::vector<std::string> tokens = cutForSearch("狗是人类忠实的朋友");
    EXPECT_FALSE(tokens.empty());
    for (const std::string& t : tokens) {
        EXPECT_FALSE(t.empty());
    }
}