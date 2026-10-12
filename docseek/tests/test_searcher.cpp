// tests/test_searcher.cpp
// Searcher 与 buildMatchQuery 的 GoogleTest 单元测试（中文注释）
#include <gtest/gtest.h>

#include <filesystem>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace {

// 生成一个临时数据库路径，避免污染真实数据
std::string makeTempDbPath() {
    auto dir = std::filesystem::temp_directory_path() /
               ("docseek_test_searcher_" + std::to_string(::getpid()));
    std::filesystem::create_directories(dir);
    return (dir / "test.db").string();
}

}  // namespace

// 测试 buildMatchQuery 的转义与分词行为
TEST(BuildMatchQuery, BasicTokens) {
    EXPECT_EQ(docseek::Searcher::buildMatchQuery("hello world"), "\"hello\" \"world\"");
    EXPECT_EQ(docseek::Searcher::buildMatchQuery("say \"hi\""), "\"say\" \"\"\"hi\"\"\"");
    EXPECT_EQ(docseek::Searcher::buildMatchQuery(""), "");
    EXPECT_EQ(docseek::Searcher::buildMatchQuery("   "), "");
}

// 测试 search() 的隐式 AND 语义与命中数
TEST(SearchAndSemantics, ImplicitAnd) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert("/s/1.txt", "一", "the quick brown fox", 100, 20);
        db.upsert("/s/2.txt", "二", "quick rabbit", 100, 12);

        docseek::Searcher s(db);
        EXPECT_EQ(s.search("quick", 10).size(), 2u);

        auto foxHits = s.search("quick fox", 10);
        ASSERT_EQ(foxHits.size(), 1u);
        EXPECT_EQ(foxHits[0].path, "/s/1.txt");

        EXPECT_TRUE(s.search("elephant", 10).empty());
    }
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}

// 测试 limit 参数对结果数量的限制
TEST(SearchLimit, RespectsLimit) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert("/l/1.txt", "a", "commonword one", 100, 10);
        db.upsert("/l/2.txt", "b", "commonword two", 100, 10);
        db.upsert("/l/3.txt", "c", "commonword three", 100, 10);

        docseek::Searcher s(db);
        EXPECT_EQ(s.search("commonword", 2).size(), 2u);
    }
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}

// 测试空查询直接返回空结果
TEST(SearchEmptyQuery, EmptyAndWhitespace) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert("/e/1.txt", "x", "some content", 100, 12);

        docseek::Searcher s(db);
        EXPECT_TRUE(s.search("", 10).empty());
        EXPECT_TRUE(s.search("   ", 10).empty());
    }
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}
