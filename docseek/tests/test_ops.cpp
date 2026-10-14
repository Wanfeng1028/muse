// tests/test_ops.cpp — v0.5 可观测性/备份恢复/失败注入/批量事务测试。

#include <gtest/gtest.h>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <map>
#include <string>
#include <vector>

#include "docseek/concurrency_guard.h"
#include "docseek/database.h"
#include "docseek/indexer.h"
#include "docseek/logger.h"
#include "docseek/metrics.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

namespace {

// RAII：临时设置环境变量，析构时恢复原值（无原值则 unsetenv）。
class ScopedEnv {
public:
    ScopedEnv(const char* name, const char* value) : name_(name) {
        const char* old = std::getenv(name);
        if (old) {
            hadOld_ = true;
            oldValue_ = old;
        }
        setenv(name, value, 1);
    }
    ~ScopedEnv() {
        if (hadOld_) {
            setenv(name_.c_str(), oldValue_.c_str(), 1);
        } else {
            unsetenv(name_.c_str());
        }
    }

    ScopedEnv(const ScopedEnv&) = delete;
    ScopedEnv& operator=(const ScopedEnv&) = delete;

private:
    std::string name_;
    std::string oldValue_;
    bool hadOld_ = false;
};

// 生成一个唯一的临时路径，避免测试间相互干扰。
fs::path uniqueTempPath(const std::string& tag) {
    static int counter = 0;
    return fs::temp_directory_path() /
           ("docseek_test_ops_" + tag + "_" + std::to_string(++counter) +
            "_" + std::to_string(reinterpret_cast<uintptr_t>(&counter)));
}

// 删除单个文件（忽略不存在的情况）。
void removeFileIfExists(const fs::path& p) {
    std::error_code ec;
    fs::remove(p, ec);
}

// 递归删除目录（忽略不存在的情况）。
void removeDirIfExists(const fs::path& p) {
    std::error_code ec;
    fs::remove_all(p, ec);
}

// 写入指定字节内容到文件。
void writeBytes(const fs::path& p, const std::string& bytes) {
    std::ofstream ofs(p, std::ios::binary | std::ios::trunc);
    ofs.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
    ofs.close();
}

// 统计字符串中子串出现的次数（用于“无换行”等断言）。
size_t countSubstr(const std::string& hay, const std::string& needle) {
    if (needle.empty()) return 0;
    size_t n = 0;
    size_t pos = 0;
    while ((pos = hay.find(needle, pos)) != std::string::npos) {
        ++n;
        pos += needle.size();
    }
    return n;
}

}  // namespace

// 1. 日志 JSON 行格式：包含字段、request_id、单行以 }\n 结尾。
TEST(LoggerTest, JsonLineFormat) {
    ScopedEnv env("DOCSEEK_LOG_LEVEL", "debug");
    docseek::setLevelFromEnv();

    docseek::setRequestId("r-000042");
    testing::internal::CaptureStderr();
    docseek::log(docseek::Level::Info, "testmod", "hello", {{"k", "v"}});
    std::string out = testing::internal::GetCapturedStderr();

    // 恰好以 "}\n" 结尾，且内部没有其他换行（单行 JSON）。
    ASSERT_GE(out.size(), 2u);
    EXPECT_EQ(out.substr(out.size() - 2), "}\n");
    EXPECT_EQ(countSubstr(out, "\n"), 1u);

    EXPECT_NE(out.find("\"level\":\"info\""), std::string::npos);
    EXPECT_NE(out.find("\"module\":\"testmod\""), std::string::npos);
    EXPECT_NE(out.find("\"msg\":\"hello\""), std::string::npos);
    EXPECT_NE(out.find("\"request_id\":\"r-000042\""), std::string::npos);
    EXPECT_NE(out.find("\"k\":\"v\""), std::string::npos);
    EXPECT_NE(out.find("\"ts\":\""), std::string::npos);

    // 清空 request id 后再记录一条，应包含空字符串。
    docseek::clearRequestId();
    testing::internal::CaptureStderr();
    docseek::log(docseek::Level::Info, "testmod", "world");
    std::string out2 = testing::internal::GetCapturedStderr();
    EXPECT_NE(out2.find("\"request_id\":\"\""), std::string::npos);
}

// 2. 级别过滤：error 级别下 Info/Warn 不输出，Error 输出。
TEST(LoggerTest, LevelFiltering) {
    ScopedEnv env("DOCSEEK_LOG_LEVEL", "error");
    docseek::setLevelFromEnv();

    testing::internal::CaptureStderr();
    docseek::log(docseek::Level::Info, "m", "info-msg");
    docseek::log(docseek::Level::Warn, "m", "warn-msg");
    std::string out = testing::internal::GetCapturedStderr();
    EXPECT_TRUE(out.empty());

    testing::internal::CaptureStderr();
    docseek::log(docseek::Level::Error, "m", "boom");
    std::string out2 = testing::internal::GetCapturedStderr();
    EXPECT_FALSE(out2.empty());
    EXPECT_NE(out2.find("\"level\":\"error\""), std::string::npos);
}

// 3. request id 序列：前缀为 r-，且两次生成互不相同。
TEST(LoggerTest, RequestIdSequence) {
    std::string a = docseek::newRequestId();
    std::string b = docseek::newRequestId();
    EXPECT_EQ(a.rfind("r-", 0), 0u);
    EXPECT_EQ(b.rfind("r-", 0), 0u);
    EXPECT_NE(a, b);
}

// 4. Metrics 记录与 JSON 输出。
TEST(MetricsTest, RecordAndJson) {
    docseek::Metrics m(500.0);
    m.recordQuery("search", " 全文检索 ", 10.0);
    m.recordQuery("search", "全文检索", 20.0);
    m.recordQuery("locate", "退款", 600.0);

    std::string j = m.toJson(100);
    EXPECT_NE(j.find("\"uptime_sec\":100"), std::string::npos);
    EXPECT_NE(j.find("\"search\":{\"count\":2,\"avg_ms\":15.0"), std::string::npos);
    EXPECT_NE(j.find("\"locate\":{\"count\":1"), std::string::npos);

    // top_queries：全文检索出现次数更多，应排在退款之前。
    size_t posFull = j.find("\"q\":\"全文检索\",\"count\":2");
    size_t posRefund = j.find("\"q\":\"退款\"");
    EXPECT_NE(posFull, std::string::npos);
    EXPECT_NE(posRefund, std::string::npos);
    if (posFull != std::string::npos && posRefund != std::string::npos) {
        EXPECT_LT(posFull, posRefund);
    }

    // slow_queries：600ms 超过 500ms 阈值，应记录。
    EXPECT_NE(j.find("\"endpoint\":\"locate\""), std::string::npos);
    EXPECT_NE(j.find("\"latency_ms\":600.0"), std::string::npos);

    EXPECT_NE(j.find("\"locate_rejected\":0"), std::string::npos);
}

// 5. 拒绝计数累加。
TEST(MetricsTest, RejectedCounter) {
    docseek::Metrics m;
    m.recordLocateRejected();
    m.recordLocateRejected();
    std::string j = m.toJson(1);
    EXPECT_NE(j.find("\"locate_rejected\":2"), std::string::npos);
}

// 6. 损坏的数据库文件打开时抛 runtime_error，而不是崩溃。
TEST(FailureInjectionTest, CorruptedDbThrows) {
    // 纯垃圾（非 SQLite 格式）。
    fs::path p1 = uniqueTempPath("corrupt_garbage");
    {
        std::string garbage(64, '\xAB');
        writeBytes(p1, garbage);
    }
    EXPECT_THROW(docseek::Database::open(p1.string()), std::runtime_error);
    removeFileIfExists(p1);

    // 带有 SQLite 魔数但后续是垃圾。
    fs::path p2 = uniqueTempPath("corrupt_magic");
    {
        std::string data = "SQLite format 3";
        data.push_back('\0');
        data.append(64, '\xCD');
        writeBytes(p2, data);
    }
    EXPECT_THROW(docseek::Database::open(p2.string()), std::runtime_error);
    removeFileIfExists(p2);
}

// 7. 备份无效源路径抛异常，且 isValidDocseekDb 对不存在文件返回 false。
TEST(FailureInjectionTest, BackupInvalidSource) {
    fs::path dst = uniqueTempPath("backup_dst");
    EXPECT_THROW(docseek::Database::backup("/definitely/not/exist.db", dst.string()),
                 std::runtime_error);
    EXPECT_FALSE(docseek::Database::isValidDocseekDb("/definitely/not/exist.db"));
    removeFileIfExists(dst);
}

// 8. 恢复拒绝垃圾文件：isValidDocseekDb 返回 false。
TEST(FailureInjectionTest, RestoreRejectsGarbage) {
    fs::path garbagePath = uniqueTempPath("restore_garbage");
    {
        std::string garbage(128, '\xEF');
        writeBytes(garbagePath, garbage);
    }
    EXPECT_FALSE(docseek::Database::isValidDocseekDb(garbagePath.string()));
    removeFileIfExists(garbagePath);
}

// 9. 批量事务：abort 回滚，commit 提交。
TEST(FailureInjectionTest, BatchRollback) {
    fs::path dbPath = uniqueTempPath("batch_rollback");
    removeFileIfExists(dbPath);

    {
        docseek::Database db = docseek::Database::open(dbPath.string());
        db.upsert("/a.txt", "a", "aaa", 1, 3);
        EXPECT_EQ(db.docCount(), 1);

        db.beginBatch();
        EXPECT_TRUE(db.inBatch());
        db.upsert("/b.txt", "b", "bbb", 1, 3);
        db.upsert("/c.txt", "c", "ccc", 1, 3);
        db.abortBatch();
        EXPECT_FALSE(db.inBatch());
        EXPECT_EQ(db.docCount(), 1);

        db.beginBatch();
        db.upsert("/b.txt", "b", "bbb", 1, 3);
        db.upsert("/c.txt", "c", "ccc", 1, 3);
        db.commitBatch();
        EXPECT_EQ(db.docCount(), 3);
    }

    removeFileIfExists(dbPath);
}

// 10. 批量事务误用：未 begin 直接 commit、嵌套 begin 均应抛异常。
TEST(FailureInjectionTest, BatchMisuseThrows) {
    fs::path dbPath = uniqueTempPath("batch_misuse");
    removeFileIfExists(dbPath);

    {
        docseek::Database db = docseek::Database::open(dbPath.string());
        EXPECT_THROW(db.commitBatch(), std::runtime_error);
        db.beginBatch();
        EXPECT_THROW(db.beginBatch(), std::runtime_error);
        db.abortBatch();
        EXPECT_FALSE(db.inBatch());
    }

    removeFileIfExists(dbPath);
}

// 11. 备份/恢复往返：数据与全文索引都保留。
TEST(BackupRestoreTest, Roundtrip) {
    fs::path tmp1 = uniqueTempPath("roundtrip_src");
    fs::path tmp2 = uniqueTempPath("roundtrip_dst");
    removeFileIfExists(tmp1);
    removeFileIfExists(tmp2);

    {
        docseek::Database db1 = docseek::Database::open(tmp1.string());
        db1.upsert("/doc1.txt", "全文检索", "关于全文检索的文档", 1, 10);
        db1.upsert("/doc2.txt", "退款流程", "退款流程说明文档", 2, 20);
        db1.upsert("/doc3.txt", "订单查询", "订单查询接口说明", 3, 30);

        docseek::Database::backup(db1.path(), tmp2.string());
        EXPECT_TRUE(docseek::Database::isValidDocseekDb(tmp2.string()));

        docseek::Database db2 = docseek::Database::open(tmp2.string());
        EXPECT_EQ(db2.docCount(), 3);

        std::string match = docseek::Searcher::buildMatchQuery("全文检索");
        auto hits = db2.searchFts(match, 10);
        EXPECT_GE(hits.size(), 1u);
    }

    removeFileIfExists(tmp1);
    removeFileIfExists(tmp2);
}

// 12. Indexer 在批量事务下的提交与增量识别。
TEST(BatchTransactionTest, IndexerBatchCommit) {
    fs::path dir = uniqueTempPath("indexer_dir");
    removeDirIfExists(dir);
    fs::create_directories(dir);

    const int kCount = 300;
    for (int i = 0; i < kCount; ++i) {
        fs::path f = dir / ("doc_" + std::to_string(i) + ".txt");
        writeBytes(f, "批量事务测试 内容 " + std::to_string(i));
    }

    fs::path dbPath = uniqueTempPath("indexer_db");
    removeFileIfExists(dbPath);

    {
        docseek::Database db = docseek::Database::open(dbPath.string());
        docseek::Indexer idx(db, {});
        docseek::IndexStats st = idx.indexPaths({dir.string()});
        EXPECT_EQ(st.added, static_cast<size_t>(kCount));
        EXPECT_EQ(db.docCount(), static_cast<int64_t>(kCount));

        // 再跑一次：全部 unchanged。
        docseek::IndexStats st2 = idx.indexPaths({dir.string()});
        EXPECT_EQ(st2.unchanged, static_cast<size_t>(kCount));
        EXPECT_EQ(st2.added, 0u);
    }

    removeFileIfExists(dbPath);
    removeDirIfExists(dir);
}

// 13. 并发守卫：获取/释放/超时失败。
TEST(ConcurrencyGuardTest, AcquireRelease) {
    docseek::ConcurrencyGuard g(2);
    EXPECT_TRUE(g.tryAcquire(100));
    EXPECT_TRUE(g.tryAcquire(100));
    // 槽位已满，50ms 内无人释放，必须超时失败。
    EXPECT_FALSE(g.tryAcquire(50));
    g.release();
    EXPECT_TRUE(g.tryAcquire(50));
    g.release();
    g.release();

    docseek::ScopedSlot slot(g, 100);
    EXPECT_TRUE(slot.held());
}

// 14. 非法 maxConcurrent 退化为 1。
TEST(ConcurrencyGuardTest, InvalidMaxFallsBackToOne) {
    docseek::ConcurrencyGuard g(0);
    EXPECT_TRUE(g.tryAcquire(50));
    EXPECT_FALSE(g.tryAcquire(20));
    g.release();
}
