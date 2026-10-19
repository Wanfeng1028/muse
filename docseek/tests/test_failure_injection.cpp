// tests/test_failure_injection.cpp — v0.18.1 关键路径失败注入测试。
//
// 目标：为检索/索引关键路径补失败注入用例，覆盖 v0.18.1 发版对照报告中
// "关键路径有失败注入测试"判未通过所缺失的场景。
//
// 设计约束（遵守本仓库 test_ops.cpp 的既有 fixture 模式）：
//   * 只使用 docseek/database.h、docseek/indexer.h、docseek/searcher.h 中已存在的公共 API；
//   * 所有临时路径通过 fs::temp_directory_path() 生成，RAII 清理。
//
// 红/绿语义：
//   每个 TEST 断言的是"失败时行为明确"，而不是"失败不会发生"。

#include <gtest/gtest.h>

#include <atomic>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unistd.h>
#include <vector>

#include "docseek/database.h"
#include "docseek/indexer.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

namespace {

// ---- fixture ----

// 生成唯一临时路径，避免测试间互相干扰。
fs::path uniqueTempPath(const std::string& tag) {
    static std::atomic<int> counter{0};
    return fs::temp_directory_path() /
           ("docseek_test_fi_" + tag + "_" +
            std::to_string(counter.fetch_add(1)) + "_" +
            std::to_string(reinterpret_cast<uintptr_t>(&counter)));
}

// 递归删除目录（忽略不存在）。
void removeDirIfExists(const fs::path& p) {
    std::error_code ec;
    fs::remove_all(p, ec);
}

// 删除单个文件（忽略不存在）。
void removeFileIfExists(const fs::path& p) {
    std::error_code ec;
    fs::remove(p, ec);
}

// 写入指定字节内容。
void writeBytes(const fs::path& p, const std::string& bytes) {
    std::ofstream ofs(p, std::ios::binary | std::ios::trunc);
    ofs.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
    ofs.close();
}

// RAII：一个自清理的临时目录。
class TempDir {
public:
    explicit TempDir(const std::string& tag)
        : path_(uniqueTempPath(tag)) {
        std::error_code ec;
        fs::create_directories(path_, ec);
    }
    ~TempDir() { removeDirIfExists(path_); }

    TempDir(const TempDir&) = delete;
    TempDir& operator=(const TempDir&) = delete;

    const fs::path& path() const { return path_; }

private:
    fs::path path_;
};

}  // namespace

// ---------------------------------------------------------------------------
// 用例 1：索引只读目录 —— Indexer 索引到只读目录时失败，
//         错误被记入 IndexStats.errors（Indexer 内部对单文件异常吞并记 errors）。
// ---------------------------------------------------------------------------
TEST(FailureInjection, IndexReadOnlyDirRecordsError) {
    // root 无视文件权限位，只读目录对其仍可读；此用例在 root 下无意义，直接跳过。
    if (::geteuid() == 0) GTEST_SKIP() << "root 下权限位不生效，跳过只读目录用例";
    TempDir td("index_ro");
    const fs::path roDir = td.path() / "ro";
    std::error_code ec;
    fs::create_directories(roDir, ec);

    // 在只读目录里先放一个文件，确保 indexPaths 会尝试读取它。
    const fs::path srcFile = roDir / "a.txt";
    writeBytes(srcFile, "hello docseek failure injection\n");

    // 目录设为只读（owner 无写权限）。
    fs::permissions(roDir,
                    fs::perms::owner_read | fs::perms::owner_exec,
                    fs::perm_options::replace, ec);

    // DB 放在另一个可写目录（数据库自身必须可写）。
    const fs::path dbPath = td.path() / "index.db";
    docseek::Database db = docseek::Database::open(dbPath);

    docseek::Indexer indexer(db);
    docseek::IndexStats st = indexer.indexPaths({roDir.string()});

    // 恢复权限，保证 TempDir 析构能删干净。
    fs::permissions(roDir,
                    fs::perms::owner_all,
                    fs::perm_options::replace, ec);

    // 二选一：断言错误被记录（indexer 内部吞异常并写入 errors）。
    EXPECT_FALSE(st.errors.empty())
        << "只读目录索引应至少记录一条错误";
}

// ---------------------------------------------------------------------------
// 用例 2：搜索空索引 —— 返回空结果，不抛异常。
// ---------------------------------------------------------------------------
TEST(FailureInjection, SearchEmptyIndexReturnsEmptyNoThrow) {
    TempDir td("empty_index");
    const fs::path dbPath = td.path() / "empty.db";

    docseek::Database db = docseek::Database::open(dbPath);
    docseek::Searcher searcher(db);

    std::vector<docseek::Hit> hits;
    ASSERT_NO_THROW(hits = searcher.search("不存在的词xyz", 10));
    EXPECT_TRUE(hits.empty());
}

// ---------------------------------------------------------------------------
// 用例 3：searchQuestion 对无意义查询（纯标点）返回空，不抛异常。
// ---------------------------------------------------------------------------
TEST(FailureInjection, SearchQuestionPunctuationOnlyReturnsEmptyNoThrow) {
    TempDir td("punct_query");
    const fs::path dbPath = td.path() / "empty.db";

    docseek::Database db = docseek::Database::open(dbPath);
    docseek::Searcher searcher(db);

    const std::string punctuationOnly = "，。！？";

    std::vector<docseek::Hit> hits;
    ASSERT_NO_THROW(hits = searcher.searchQuestion(punctuationOnly, 10));
    EXPECT_TRUE(hits.empty());
}

// ---------------------------------------------------------------------------
// 用例 4：Database::open 对目录路径抛 std::runtime_error。
// ---------------------------------------------------------------------------
TEST(FailureInjection, DatabaseOpenOnDirectoryThrows) {
    TempDir td("open_dir");
    const fs::path dirPath = td.path() / "as_db";
    std::error_code ec;
    fs::create_directories(dirPath, ec);
    ASSERT_TRUE(fs::is_directory(dirPath));

    EXPECT_THROW(
        {
            docseek::Database db = docseek::Database::open(dirPath.string());
            (void)db;
        },
        std::runtime_error);
}

// ---------------------------------------------------------------------------
// 用例 5：Indexer::pruneMissing —— 先索引一个文件再删文件，pruneMissing() 返回 1。
// ---------------------------------------------------------------------------
TEST(FailureInjection, PruneMissingRemovesDeletedFile) {
    TempDir td("prune_missing");
    const fs::path srcDir = td.path() / "src";
    std::error_code ec;
    fs::create_directories(srcDir, ec);

    const fs::path fileA = srcDir / "a.txt";
    writeBytes(fileA, "hello prune missing test\n");

    const fs::path dbPath = td.path() / "index.db";
    docseek::Database db = docseek::Database::open(dbPath);

    docseek::Indexer indexer(db);
    docseek::IndexStats st = indexer.indexPaths({srcDir.string()});
    ASSERT_GE(st.added + st.updated + st.unchanged, static_cast<size_t>(1));
    ASSERT_EQ(db.docCount(), 1);

    // 从磁盘删除文件，再 prune。
    removeFileIfExists(fileA);
    ASSERT_FALSE(fs::exists(fileA));

    const size_t removed = indexer.pruneMissing();
    EXPECT_EQ(removed, static_cast<size_t>(1));
    EXPECT_EQ(db.docCount(), 0);
}

// ---------------------------------------------------------------------------
// 用例 6：并发 —— 多线程同时 search 同一 Database 实例，不崩溃、不抛异常。
//
// 说明：本用例只验证"并发检索不会导致崩溃或抛出未捕获异常"，
//       不校验结果正确性。
// ---------------------------------------------------------------------------
TEST(FailureInjection, ConcurrentSearchSameDatabaseNoCrash) {
    TempDir td("concurrent");
    const fs::path srcDir = td.path() / "src";
    std::error_code ec;
    fs::create_directories(srcDir, ec);

    writeBytes(srcDir / "a.txt", "hello concurrent search world\n");
    writeBytes(srcDir / "b.txt", "another document about search\n");

    const fs::path dbPath = td.path() / "index.db";
    docseek::Database db = docseek::Database::open(dbPath);
    docseek::Indexer indexer(db);
    (void)indexer.indexPaths({srcDir.string()});

    docseek::Searcher searcher(db);

    std::atomic<int> ok{0};
    std::atomic<bool> threw{false};
    std::vector<std::thread> ts;
    for (int i = 0; i < 4; ++i) {
        ts.emplace_back([&searcher, &ok, &threw]() {
            try {
                auto hits = searcher.search("search", 10);
                (void)hits;
                ok.fetch_add(1, std::memory_order_relaxed);
            } catch (...) {
                threw.store(true, std::memory_order_relaxed);
            }
        });
    }
    for (auto& t : ts) t.join();

    EXPECT_EQ(ok.load(), 4);
    EXPECT_FALSE(threw.load());
    // 只测不崩：走到此处即无 crash。
    EXPECT_TRUE(true);
}

// ---------------------------------------------------------------------------
// 用例 7：超大文件跳过 —— IndexOptions{maxFileBytes=1024} 索引 2KB 文件，
//         IndexStats.skipped >= 1。
// ---------------------------------------------------------------------------
TEST(FailureInjection, OversizeSingleFileIsSkipped) {
    TempDir td("oversize");
    const fs::path srcDir = td.path() / "src";
    std::error_code ec;
    fs::create_directories(srcDir, ec);

    const fs::path bigFile = srcDir / "big.txt";
    // 2KB 内容（全为可打印字符）。
    std::string payload(2048, 'a');
    writeBytes(bigFile, payload);

    const auto sz = fs::file_size(bigFile, ec);
    ASSERT_FALSE(ec);
    ASSERT_GE(sz, static_cast<uintmax_t>(2048));

    const fs::path dbPath = td.path() / "index.db";
    docseek::Database db = docseek::Database::open(dbPath);

    docseek::IndexOptions opts;
    opts.maxFileBytes = 1024;
    docseek::Indexer indexer(db, opts);

    docseek::IndexStats st = indexer.indexPaths({srcDir.string()});
    EXPECT_GE(st.skipped, static_cast<size_t>(1));
}

// ---------------------------------------------------------------------------
// 用例 8：removeByPath 不存在返回 false 不抛。
// ---------------------------------------------------------------------------
TEST(FailureInjection, RemoveByPathMissingReturnsFalseNoThrow) {
    TempDir td("remove_missing");
    const fs::path dbPath = td.path() / "index.db";
    docseek::Database db = docseek::Database::open(dbPath);

    bool removed = true;
    ASSERT_NO_THROW(removed = db.removeByPath("/no/such/path/at/all.txt"));
    EXPECT_FALSE(removed);
}
