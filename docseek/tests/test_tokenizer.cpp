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

    // 校验 user_version == 3
    {
        sqlite3* raw = nullptr;
        ASSERT_EQ(sqlite3_open(dbPath.c_str(), &raw), SQLITE_OK);
        sqlite3_stmt* stmt = nullptr;
        ASSERT_EQ(sqlite3_prepare_v2(raw, "PRAGMA user_version;", -1, &stmt, nullptr), SQLITE_OK);
        ASSERT_EQ(sqlite3_step(stmt), SQLITE_ROW);
        EXPECT_EQ(sqlite3_column_int(stmt, 0), 3);
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
