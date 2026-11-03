// tests/test_indexer.cpp
// 文溯 DocSeek · Indexer 单元测试（GoogleTest）
#include <gtest/gtest.h>

#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>

#include "docseek/database.h"
#include "docseek/indexer.h"

namespace fs = std::filesystem;

// 测试夹具：每个 TEST_F 独立准备临时目录与数据库文件
struct IdxFixture : public ::testing::Test {
  fs::path dir;
  std::string dbPath;

  void SetUp() override {
    // 使用固定临时目录名，先清空再重建
    dir = fs::temp_directory_path() / "docseek_idx_test";
    std::error_code ec;
    fs::remove_all(dir, ec);
    fs::create_directories(dir);

    // 数据库文件同样先删除，保证每次干净
    dbPath = (fs::temp_directory_path() / "docseek_idx_test.db").string();
    fs::remove(dbPath, ec);
  }

  // 写文件辅助：rel 为相对 dir 的路径，content 为内容
  void writeFile(const std::string& rel, const std::string& content) {
    fs::path p = dir / rel;
    fs::create_directories(p.parent_path());
    std::ofstream ofs(p, std::ios::binary | std::ios::trunc);
    ofs.write(content.data(), static_cast<std::streamsize>(content.size()));
    ofs.close();
  }
};

// 基础索引：3 个成功，2 个跳过（二进制 + 超限）
TEST_F(IdxFixture, IndexBasic) {
  writeFile("a.txt", "hello world");
  writeFile("b.md", "# 标题\nfoo bar");
  writeFile("sub/c.txt", "nested");
  // 含 '\0' 的二进制文件
  std::string bin = "abc";
  bin.push_back('\0');
  bin += "def";
  writeFile("skip.bin", bin);
  // 30 字节文本文件，超过 maxFileBytes=20 将被跳过
  writeFile("big.txt", std::string(30, 'x'));

  auto db = docseek::Database::open(dbPath);

  docseek::IndexOptions opts;
  opts.maxFileBytes = 20;
  docseek::Indexer indexer(db, opts);

  auto st = indexer.indexPaths({dir.string()});

  EXPECT_EQ(st.added, 3u);
  EXPECT_EQ(st.skipped, 2u);
  EXPECT_EQ(db.docCount(), 3);
}

// 幂等性：再次索引无新增、全部 unchanged
TEST_F(IdxFixture, IndexIdempotent) {
  writeFile("a.txt", "hello world");
  writeFile("b.md", "# 标题\nfoo bar");
  writeFile("sub/c.txt", "nested");
  std::string bin = "abc";
  bin.push_back('\0');
  bin += "def";
  writeFile("skip.bin", bin);
  writeFile("big.txt", std::string(30, 'x'));

  auto db = docseek::Database::open(dbPath);
  docseek::IndexOptions opts;
  opts.maxFileBytes = 20;
  docseek::Indexer indexer(db, opts);

  indexer.indexPaths({dir.string()});
  auto st = indexer.indexPaths({dir.string()});

  EXPECT_EQ(st.added, 0u);
  EXPECT_EQ(st.unchanged, 3u);
}

// 更新检测：修改 a.txt 并显式推进 mtime，应记为 updated
TEST_F(IdxFixture, IndexUpdate) {
  writeFile("a.txt", "hello world");
  writeFile("b.md", "# 标题\nfoo bar");
  writeFile("sub/c.txt", "nested");
  std::string bin = "abc";
  bin.push_back('\0');
  bin += "def";
  writeFile("skip.bin", bin);
  writeFile("big.txt", std::string(30, 'x'));

  auto db = docseek::Database::open(dbPath);
  docseek::IndexOptions opts;
  opts.maxFileBytes = 20;
  docseek::Indexer indexer(db, opts);

  indexer.indexPaths({dir.string()});

  // 重写 a.txt 内容，并把 mtime 推进 5 秒
  writeFile("a.txt", "hello world updated");
  fs::path ap = dir / "a.txt";
  auto t = fs::last_write_time(ap);
  fs::last_write_time(ap, t + std::chrono::seconds(5));

  auto st = indexer.indexPaths({dir.string()});

  EXPECT_EQ(st.updated, 1u);
  EXPECT_EQ(st.unchanged, 2u);
}

// 清理：删除文件后索引应删除对应记录；pruneMissing 返回删除数
TEST_F(IdxFixture, Prune) {
  writeFile("a.txt", "hello world");
  writeFile("b.md", "# 标题\nfoo bar");
  writeFile("sub/c.txt", "nested");
  std::string bin = "abc";
  bin.push_back('\0');
  bin += "def";
  writeFile("skip.bin", bin);
  writeFile("big.txt", std::string(30, 'x'));

  auto db = docseek::Database::open(dbPath);
  docseek::IndexOptions opts;
  opts.maxFileBytes = 20;
  docseek::Indexer indexer(db, opts);

  indexer.indexPaths({dir.string()});
  EXPECT_EQ(db.docCount(), 3);

  // 删除 b.md 后再索引，应删除 1 条记录
  fs::remove(dir / "b.md");
  auto st = indexer.indexPaths({dir.string()});
  EXPECT_EQ(st.removed, 1u);
  EXPECT_EQ(db.docCount(), 2);

  // 删除 sub/c.txt 后单独调用 pruneMissing
  fs::remove(dir / "sub/c.txt");
  size_t pruned = indexer.pruneMissing();
  EXPECT_EQ(pruned, 1u);
  EXPECT_EQ(db.docCount(), 1);
}

// 扩展名过滤：只索引 .txt
TEST_F(IdxFixture, ExtFilter) {
  writeFile("a.txt", "hello world");
  writeFile("b.md", "# 标题\nfoo bar");
  writeFile("sub/c.txt", "nested");

  auto db = docseek::Database::open(dbPath);

  docseek::IndexOptions opts;
  opts.extensions = {".txt"};
  docseek::Indexer indexer(db, opts);

  auto st = indexer.indexPaths({dir.string()});

  EXPECT_EQ(st.added, 2u);
}
