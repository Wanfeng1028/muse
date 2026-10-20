#include <gtest/gtest.h>

#include <filesystem>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

namespace {

fs::path makeUniqueDir(const std::string& name) {
    fs::path base = fs::current_path() / "test-tmp" / name;
    std::error_code ec;
    fs::remove_all(base, ec);
    fs::create_directories(base, ec);
    return base;
}

}  // namespace

TEST(HybridEmptyQueryR2, EmptyQueryReturnsEmpty) {
    fs::path dir = makeUniqueDir("hybrid_r2_empty_1");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    db.upsert((dir / "a.txt").string(), "检索文档", "这是一篇关于检索的测试文档内容", 100, 200);
    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("", 10);
    EXPECT_TRUE(hits.empty());
}

TEST(HybridEmptyQueryR2, WhitespaceQueryReturnsEmpty) {
    fs::path dir = makeUniqueDir("hybrid_r2_empty_2");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    db.upsert((dir / "a.txt").string(), "检索文档", "这是一篇关于检索的测试文档内容", 100, 200);
    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("   ", 10);
    EXPECT_TRUE(hits.empty());
}

TEST(HybridEmptyQueryR2, ZeroLimitReturnsEmpty) {
    fs::path dir = makeUniqueDir("hybrid_r2_empty_3");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    db.upsert((dir / "a.txt").string(), "检索文档", "这是一篇关于检索的测试文档内容", 100, 200);
    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("检索", 0);
    EXPECT_TRUE(hits.empty());
}

TEST(HybridEmptyQueryR2, NegativeLimitReturnsEmpty) {
    fs::path dir = makeUniqueDir("hybrid_r2_empty_4");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    db.upsert((dir / "a.txt").string(), "检索文档", "这是一篇关于检索的测试文档内容", 100, 200);
    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("检索", -5);
    EXPECT_TRUE(hits.empty());
}

TEST(HybridEmptyQueryR2, SearchQuestionEmptyAndZeroLimitReturnEmpty) {
    fs::path dir = makeUniqueDir("hybrid_r2_empty_5");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    db.upsert((dir / "a.txt").string(), "检索文档", "这是一篇关于检索的测试文档内容", 100, 200);
    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hitsEmpty = searcher.searchQuestion("", 10);
    EXPECT_TRUE(hitsEmpty.empty());
    std::vector<docseek::Hit> hitsZero = searcher.searchQuestion("检索", 0);
    EXPECT_TRUE(hitsZero.empty());
}