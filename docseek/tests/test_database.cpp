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
TEST_F(DatabaseTest, UserIsolation_CountAndList) {
    // 在测：不同用户的数据相互隔离，docCount 与 list 都按 user 维度过滤
    auto db = makeDb();
    db.upsert("/tmp/alice1.txt", "甲一", "content a1", 100, 10, "alice");
    db.upsert("/tmp/alice2.txt", "甲二", "content a2", 101, 11, "alice");
    db.upsert("/tmp/bob1.txt", "乙一", "content b1", 102, 12, "bob");

    EXPECT_EQ(db.docCount("alice"), 2);
    EXPECT_EQ(db.docCount("bob"), 1);
    // 默认用户是 local，本用例未向 local 写入任何文档
    EXPECT_EQ(db.docCount(), 0);

    auto aliceDocs = db.list("alice");
    ASSERT_EQ(aliceDocs.size(), 2u);
    for (const auto& d : aliceDocs) {
        EXPECT_EQ(d.user, "alice");
    }

    // 默认 list 只返回 local 用户的文档，此处为空
    EXPECT_TRUE(db.list().empty());
}

TEST_F(DatabaseTest, UserIsolation_SamePath) {
    // 在测：同一路径在不同用户下互不覆盖，findByPath 按 user 维度返回各自版本
    auto db = makeDb();
    db.upsert("/tmp/shared.txt", "alice版", "alice content", 100, 20, "alice");
    db.upsert("/tmp/shared.txt", "bob版", "bob content", 200, 30, "bob");

    auto aliceDoc = db.findByPath("/tmp/shared.txt", "alice");
    ASSERT_TRUE(aliceDoc.has_value());
    EXPECT_EQ(aliceDoc->title, "alice版");

    auto bobDoc = db.findByPath("/tmp/shared.txt", "bob");
    ASSERT_TRUE(bobDoc.has_value());
    EXPECT_EQ(bobDoc->title, "bob版");

    // 默认用户 local 下不存在该路径
    EXPECT_FALSE(db.findByPath("/tmp/shared.txt").has_value());
}

TEST_F(DatabaseTest, UserIsolation_Search) {
    // 在测：全文检索按 user 维度隔离，不会跨用户命中
    auto db = makeDb();
    db.upsert("/tmp/alice_secret.txt", "机密文档", "这是机密内容", 100, 15, "alice");
    db.upsert("/tmp/bob_public.txt", "公开文档", "这是公开内容", 200, 15, "bob");

    auto aliceHits = db.searchFts(docseek::Searcher::buildMatchQuery("机密"), 10, "alice");
    EXPECT_EQ(aliceHits.size(), 1u);

    auto bobHits = db.searchFts(docseek::Searcher::buildMatchQuery("机密"), 10, "bob");
    EXPECT_TRUE(bobHits.empty());

    // 默认用户 local 无任何文档，检索为空
    auto defaultHits = db.searchFts(docseek::Searcher::buildMatchQuery("机密"), 10);
    EXPECT_TRUE(defaultHits.empty());
}

TEST_F(DatabaseTest, RemoveByUser) {
    // 在测：removeByUser 只删除指定用户的全部文档，返回删除条数，用户不存在返回 0 不抛异常
    auto db = makeDb();
    db.upsert("/tmp/alice1.txt", "甲一", "content a1", 100, 10, "alice");
    db.upsert("/tmp/alice2.txt", "甲二", "content a2", 101, 11, "alice");
    db.upsert("/tmp/bob1.txt", "乙一", "content b1", 102, 12, "bob");

    EXPECT_EQ(db.removeByUser("alice"), 2u);
    EXPECT_EQ(db.docCount("alice"), 0);
    EXPECT_EQ(db.docCount("bob"), 1);

    // 删除不存在的用户应返回 0 且不抛异常
    EXPECT_NO_THROW({
        EXPECT_EQ(db.removeByUser("ghost"), 0u);
    });
}

TEST_F(DatabaseTest, CheckUserValid) {
    // 在测：checkUserValid 对空、含控制字符、超长用户名抛 runtime_error，对合法用户名不抛
    EXPECT_THROW(docseek::checkUserValid(""), std::runtime_error);
    EXPECT_THROW(docseek::checkUserValid(std::string("a\ttab")), std::runtime_error);
    EXPECT_THROW(docseek::checkUserValid(std::string(65, 'x')), std::runtime_error);

    EXPECT_NO_THROW(docseek::checkUserValid("alice"));
    EXPECT_NO_THROW(docseek::checkUserValid("user-1.name"));
}

TEST_F(DatabaseTest, DefaultUserIsLocal) {
    // 在测：默认用户常量为 local，且不传 user 参数时写入的文档归属于 local
    EXPECT_STREQ(docseek::kDefaultUser, "local");

    auto db = makeDb();
    db.upsert("/tmp/default.txt", "默认", "default content", 100, 20);

    auto a = db.findByPath("/tmp/default.txt", "local");
    ASSERT_TRUE(a.has_value());
    EXPECT_EQ(a->user, "local");
}