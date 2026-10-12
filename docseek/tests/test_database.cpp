// tests/test_database.cpp
// DocSeek 数据库层单元测试（GoogleTest）
#include <gtest/gtest.h>

#include <filesystem>
#include <string>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace {

// 生成临时数据库文件路径
std::string tempDbPath() {
    return (std::filesystem::temp_directory_path() / "docseek_test_db.db").string();
}

// 夹具：每个测试前清理旧文件，再打开数据库
class DatabaseTest : public ::testing::Test {
protected:
    void SetUp() override {
        std::filesystem::remove_all(tempDbPath());
    }
    void TearDown() override {
        std::filesystem::remove_all(tempDbPath());
    }
    docseek::Database makeDb() {
        return docseek::Database::open(tempDbPath());
    }
};

}  // namespace

// 打开数据库并插入两条记录，验证计数与查询
TEST_F(DatabaseTest, OpenAndUpsert) {
    auto db = makeDb();
    db.upsert("/tmp/a.txt", "甲", "hello world", 100, 11);
    db.upsert("/tmp/b.txt", "乙", "foo bar", 200, 7);

    EXPECT_EQ(db.docCount(), 2);

    auto a = db.findByPath("/tmp/a.txt");
    ASSERT_TRUE(a.has_value());
    EXPECT_EQ(a->title, "甲");
    EXPECT_EQ(a->mtime, 100);

    EXPECT_EQ(db.totalBytes(), 18);
}

// 同一路径重复 upsert，验证更新而非新增，且 FTS 同步更新
TEST_F(DatabaseTest, UpsertUpdate) {
    auto db = makeDb();
    db.upsert("/tmp/update.txt", "t", "old content", 100, 11);
    db.upsert("/tmp/update.txt", "t", "new content", 200, 11);

    EXPECT_EQ(db.docCount(), 1);

    auto hits_new = db.searchFts(docseek::Searcher::buildMatchQuery("new"), 10);
    EXPECT_EQ(hits_new.size(), 1u);

    auto hits_old = db.searchFts(docseek::Searcher::buildMatchQuery("old"), 10);
    EXPECT_TRUE(hits_old.empty());
}

// 删除记录，验证返回值和 FTS 清理
TEST_F(DatabaseTest, RemoveByPath) {
    auto db = makeDb();
    db.upsert("/tmp/remove.txt", "r", "removable content", 100, 17);

    EXPECT_TRUE(db.removeByPath("/tmp/remove.txt"));
    EXPECT_FALSE(db.removeByPath("/tmp/remove.txt"));
    EXPECT_EQ(db.docCount(), 0);

    auto hits = db.searchFts(docseek::Searcher::buildMatchQuery("removable"), 10);
    EXPECT_TRUE(hits.empty());
}

// 搜索排序：命中词频高的文档应排前面，snippet 非空
TEST_F(DatabaseTest, SearchRanking) {
    auto db = makeDb();
    db.upsert("/d/a.txt", "a", "apple apple apple", 100, 17);
    db.upsert("/d/b.txt", "b", "apple", 200, 5);

    auto hits = db.searchFts("\"apple\"", 10);
    ASSERT_EQ(hits.size(), 2u);
    EXPECT_EQ(hits[0].path, "/d/a.txt");
    EXPECT_GE(hits[0].score, hits[1].score);
    EXPECT_FALSE(hits[0].snippet.empty());
}

// 空查询返回空结果；不存在的词返回空结果
TEST_F(DatabaseTest, SearchEmpty) {
    auto db = makeDb();
    db.upsert("/tmp/x.txt", "x", "some content here", 100, 17);

    EXPECT_TRUE(db.searchFts("", 10).empty());
    EXPECT_TRUE(db.searchFts("\"不存在的词zzz\"", 10).empty());
}

// 数据库文件大小应为正
TEST_F(DatabaseTest, DbFileBytes) {
    auto db = makeDb();
    db.upsert("/tmp/size.txt", "s", "content", 100, 7);
    EXPECT_GT(db.dbFileBytes(), 0);
}
