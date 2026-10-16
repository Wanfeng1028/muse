#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "docseek/searcher.h"

#include <sqlite3.h>

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

#ifndef _WIN32
#include <unistd.h>
#endif

namespace {

// 获取当前进程 id（用于构造唯一临时目录名）
long currentPid() {
#ifdef _WIN32
    return static_cast<long>(::GetCurrentProcessId());
#else
    return static_cast<long>(::getpid());
#endif
}

// 构造本次测试专用的临时目录（相对构建目录，避免使用 /tmp）
std::string makeTempDir(const std::string& name) {
    std::filesystem::path base = std::filesystem::current_path() / "test-tmp";
    std::filesystem::create_directories(base);
    std::filesystem::path dir = base / (name + "_" + std::to_string(currentPid()));
    std::filesystem::remove_all(dir);
    std::filesystem::create_directories(dir);
    return dir.string();
}

}  // namespace

// 通过 Database + Searcher 验证端到端中文检索
TEST(TokenizerTest, EndToEndChineseSearch) {
    std::string dir = makeTempDir("docseek_tokenizer");
    std::string dbPath = dir + "/index.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/a.txt", "标题", "全文检索引擎测试文档", 100, 42);

    docseek::Searcher searcher(db);

    auto hits1 = searcher.search("检索", 10);
    EXPECT_GE(hits1.size(), 1u);

    auto hits2 = searcher.search("全文检索", 10);
    EXPECT_GE(hits2.size(), 1u);

    auto hits3 = searcher.search("不存在的词xyz", 10);
    EXPECT_TRUE(hits3.empty());
}

// 直接验证 jieba 分词器注册与查询侧分词一致
TEST(TokenizerTest, DirectFtsJiebaTokenizer) {
    sqlite3* db = nullptr;
    ASSERT_EQ(sqlite3_open(":memory:", &db), SQLITE_OK);
    ASSERT_NE(db, nullptr);

    ASSERT_EQ(docseek::registerJiebaTokenizer(db), SQLITE_OK);

    const char* create_sql =
        "CREATE VIRTUAL TABLE ft USING fts5(content, tokenize='jieba');";
    char* errmsg = nullptr;
    ASSERT_EQ(sqlite3_exec(db, create_sql, nullptr, nullptr, &errmsg), SQLITE_OK)
        << (errmsg ? errmsg : "");

    const char* insert_sql = "INSERT INTO ft(content) VALUES('全文检索引擎');";
    ASSERT_EQ(sqlite3_exec(db, insert_sql, nullptr, nullptr, &errmsg), SQLITE_OK)
        << (errmsg ? errmsg : "");

    sqlite3_stmt* stmt = nullptr;
    ASSERT_EQ(sqlite3_prepare_v2(db, "SELECT COUNT(*) FROM ft WHERE ft MATCH ?;", -1, &stmt, nullptr),
              SQLITE_OK);
    const char* query = "\"检索\"";
    sqlite3_bind_text(stmt, 1, query, -1, SQLITE_TRANSIENT);
    ASSERT_EQ(sqlite3_step(stmt), SQLITE_ROW);
    int count = sqlite3_column_int(stmt, 0);
    sqlite3_finalize(stmt);

    EXPECT_GE(count, 1);

    sqlite3_close(db);
}

// 验证旧库（unicode61 + user_version=2）在 open 时自动迁移到 jieba
TEST(TokenizerTest, MigrateOldSchema) {
    std::string dir = makeTempDir("docseek_tokenizer_migrate");
    std::string dbPath = dir + "/old.db";

    // 直接构造旧库
    {
        sqlite3* db = nullptr;
        ASSERT_EQ(sqlite3_open(dbPath.c_str(), &db), SQLITE_OK);
        ASSERT_NE(db, nullptr);

        char* errmsg = nullptr;
        // 按真实旧 schema 建表：documents 无 content 列；documents_fts 为
        // contentful（默认），tokenize='unicode61'。
        ASSERT_EQ(sqlite3_exec(db,
                               "CREATE TABLE documents("
                               "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                               "  path TEXT NOT NULL UNIQUE,"
                               "  title TEXT NOT NULL,"
                               "  mtime INTEGER NOT NULL,"
                               "  size INTEGER NOT NULL,"
                               "  indexed_at TEXT NOT NULL"
                               ");",
                               nullptr, nullptr, &errmsg),
                  SQLITE_OK)
            << (errmsg ? errmsg : "");

        ASSERT_EQ(sqlite3_exec(db,
                               "CREATE VIRTUAL TABLE documents_fts USING fts5("
                               "  title, content,"
                               "  tokenize='unicode61'"
                               ");",
                               nullptr, nullptr, &errmsg),
                  SQLITE_OK)
            << (errmsg ? errmsg : "");

        ASSERT_EQ(sqlite3_exec(db,
                               "INSERT INTO documents(path, title, mtime, size, indexed_at)"
                               " VALUES('/old.txt', '旧标题', 1, 1, '2026-01-01T00:00:00Z');",
                               nullptr, nullptr, &errmsg),
                  SQLITE_OK)
            << (errmsg ? errmsg : "");

        // contentful FTS 表直接插入 title/content（rowid 与 documents.id 对齐）。
        ASSERT_EQ(sqlite3_exec(db,
                               "INSERT INTO documents_fts(rowid, title, content)"
                               " VALUES(1, '旧标题', '全文检索引擎');",
                               nullptr, nullptr, &errmsg),
                  SQLITE_OK)
            << (errmsg ? errmsg : "");

        ASSERT_EQ(sqlite3_exec(db, "PRAGMA user_version=2;", nullptr, nullptr, &errmsg), SQLITE_OK)
            << (errmsg ? errmsg : "");

        sqlite3_close(db);
    }

    // 用 Database::open 触发迁移
    docseek::Database db = docseek::Database::open(dbPath);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("检索", 10);
    EXPECT_GE(hits.size(), 1u);

    // 校验 user_version == 4（多用户改造后 schema v4 为最新）
    {
        sqlite3* raw = nullptr;
        ASSERT_EQ(sqlite3_open(dbPath.c_str(), &raw), SQLITE_OK);
        sqlite3_stmt* stmt = nullptr;
        ASSERT_EQ(sqlite3_prepare_v2(raw, "PRAGMA user_version;", -1, &stmt, nullptr), SQLITE_OK);
        ASSERT_EQ(sqlite3_step(stmt), SQLITE_ROW);
        EXPECT_EQ(sqlite3_column_int(stmt, 0), 4);
        sqlite3_finalize(stmt);
        sqlite3_close(raw);
    }
}

// 英文小写折叠：search("hello") 应命中 "Hello World"
TEST(TokenizerTest, EnglishCaseFolding) {
    std::string dir = makeTempDir("docseek_tokenizer_case");
    std::string dbPath = dir + "/case.db";

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/hello.txt", "Hello", "Hello World", 1, 11);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("hello", 10);
    EXPECT_GE(hits.size(), 1u);
}

// T1 缺陷复现（重叠词游标跳跃 → 后续普通词级联丢失）：
// 这不是"重复词"场景，而是"重叠词导致游标跳跃、进而使后续普通词被级联丢失"。
// 旧场景文本 '维修手机维修电脑' 在 bug 代码下并不丢词：第二个 "维修" 的真实
// 位置在 cursor 之后，单调 find 仍能找到它，因此该测试在 bug 下是通过的，
// 不能复现 T1，故换掉。
//
// 复现文本：'计算机算机维修'，CutForSearch 切分顺序为
//   <计算> <算机> <计算机> <算机> <维修>
// bug 推演（单调 find + cursor 前进）：
//   计算@字节0..6  → cursor=6
//   算机在 [6,n) 中 find → 命中第二个 "算机"（字节12..18）→ cursor=18
//   计算机在 [18,n) 中 find → npos → 丢失
//   第二个算机在 [19,n) 中 find → npos → 丢失
//   维修在 [20,n) 中 find → npos → 丢失
// 实测 fts5vocab('ft','instance') 索引中只有 计算@0、算机@1，
// "维修" 完全不在索引里：SELECT COUNT(*) FROM v WHERE term='维修' = 0。
// 这正是 T1 的危害形态：重叠词导致游标跳跃，后续普通词被级联丢失。
// 期望：修复后 term='维修' 至少进索引一次（COUNT >= 1）。
TEST(TokenizerT1, DuplicateWordNotLost) {
    const std::string dir = makeTempDir("docseek_tokenizer_t1_dup");
    const std::string dbPath = dir + "/t1_dup.db";

    sqlite3 *db = nullptr;
    ASSERT_EQ(sqlite3_open(dbPath.c_str(), &db), SQLITE_OK);
    ASSERT_EQ(docseek::registerJiebaTokenizer(db), SQLITE_OK);

    char *errMsg = nullptr;
    int rc = sqlite3_exec(db,
        "CREATE VIRTUAL TABLE ft USING fts5(content, tokenize='jieba');",
        nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::string msg = errMsg ? errMsg : "unknown error";
        sqlite3_free(errMsg);
        sqlite3_close(db);
        FAIL() << "create fts5 table failed: " << msg;
    }

    rc = sqlite3_exec(db,
        "INSERT INTO ft(content) VALUES('计算机算机维修');",
        nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::string msg = errMsg ? errMsg : "unknown error";
        sqlite3_free(errMsg);
        sqlite3_close(db);
        FAIL() << "insert failed: " << msg;
    }

    rc = sqlite3_exec(db,
        "CREATE VIRTUAL TABLE v USING fts5vocab('ft', 'instance');",
        nullptr, nullptr, &errMsg);
    ASSERT_EQ(rc, SQLITE_OK) << (errMsg ? errMsg : "");

    sqlite3_stmt *stmt = nullptr;
    rc = sqlite3_prepare_v2(db,
        "SELECT COUNT(*) FROM v WHERE term='维修';",
        -1, &stmt, nullptr);
    ASSERT_EQ(rc, SQLITE_OK);

    int count = -1;
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        count = sqlite3_column_int(stmt, 0);
    }
    sqlite3_finalize(stmt);
    sqlite3_close(db);

    EXPECT_GE(count, 1);
}

// T1 缺陷复现（重叠词丢失）：
// CutForSearch("计算机技术") => <计算> <算机> <技术> <计算机> <计算机技术>。
// jiebaXTokenize 处理完 <算机> 后游标推进到 "技术" 之前，
// 随后 "计算机"（offset 0，长 9 字节）在游标之后 find -> npos -> 丢失。
// 于是索引里找不到完整词"计算机"。
// 正确行为：索引中 term='计算机' 至少出现 1 次。bug 存在时该断言失败。
//
// 注：改用 fts5vocab 直接检查索引内容。原因：offsets() 在本仓库静态
// 编译的 sqlite3 中不可用（prepare 返回 "no such function: offsets"），
// 而 MATCH '计算机' 会被 jieba 查询侧分词切成 "计算" 从而命中，掩盖
// 索引侧丢词。fts5vocab 直接读索引，不经过查询侧分词。
TEST(TokenizerT1, OverlappingWordNotLost) {
    const std::string dir = makeTempDir("docseek_tokenizer_t1_overlap");
    const std::string dbPath = dir + "/t1_overlap.db";
    remove(dbPath.c_str());

    sqlite3* db = nullptr;
    ASSERT_EQ(sqlite3_open(dbPath.c_str(), &db), SQLITE_OK);
    ASSERT_EQ(docseek::registerJiebaTokenizer(db), SQLITE_OK);

    const char* createFt =
        "CREATE VIRTUAL TABLE ft USING fts5(content, tokenize='jieba');";
    char* errMsg = nullptr;
    ASSERT_EQ(sqlite3_exec(db, createFt, nullptr, nullptr, &errMsg), SQLITE_OK)
        << (errMsg ? errMsg : "");

    const char* insertSql =
        "INSERT INTO ft(content) VALUES('计算机技术');";
    ASSERT_EQ(sqlite3_exec(db, insertSql, nullptr, nullptr, &errMsg), SQLITE_OK)
        << (errMsg ? errMsg : "");

    const char* createVocab =
        "CREATE VIRTUAL TABLE v USING fts5vocab('ft', 'instance');";
    ASSERT_EQ(sqlite3_exec(db, createVocab, nullptr, nullptr, &errMsg), SQLITE_OK)
        << (errMsg ? errMsg : "");

    sqlite3_stmt* stmt = nullptr;
    const char* countSql = "SELECT COUNT(*) FROM v WHERE term='计算机';";
    ASSERT_EQ(sqlite3_prepare_v2(db, countSql, -1, &stmt, nullptr), SQLITE_OK);

    int count = -1;
    ASSERT_EQ(sqlite3_step(stmt), SQLITE_ROW);
    count = sqlite3_column_int(stmt, 0);
    sqlite3_finalize(stmt);

    EXPECT_GE(count, 1);

    sqlite3_close(db);
    remove(dbPath.c_str());
    rmdir(dir.c_str());
}
