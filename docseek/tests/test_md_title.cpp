// tests/test_md_title.cpp
// 文溯 DocSeek · Markdown 标题提取单元测试（GoogleTest）
// 背景：v0.34.1 之前索引器对 .md 没有标题分支，标题恒为文件名 stem，
// 导致 480/480 的 MD 文档拿不到标题加成（v09-t004-q06 实测）。
#include <gtest/gtest.h>

#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>

#include "docseek/database.h"
#include "docseek/indexer.h"

// extractMarkdownTitle 定义于 src/indexer.cpp（namespace docseek，外部链接），
// 此处仅前置声明，不改 indexer.h。
namespace docseek {
std::string extractMarkdownTitle(const std::string& content);
}  // namespace docseek

namespace fs = std::filesystem;

TEST(MdTitleExtract, FirstHeading) {
  EXPECT_EQ(docseek::extractMarkdownTitle("# 标题\n正文"), "标题");
  EXPECT_EQ(docseek::extractMarkdownTitle("前言\n## 二级\n# 一级"), "二级");
}

TEST(MdTitleExtract, HeadingTextTrimmed) {
  EXPECT_EQ(docseek::extractMarkdownTitle("#   两边空格   \n正文"), "两边空格");
  EXPECT_EQ(docseek::extractMarkdownTitle("   # 带行首空格  \n正文"), "带行首空格");
}

TEST(MdTitleExtract, HashWithoutSpaceIsNotHeading) {
  EXPECT_EQ(docseek::extractMarkdownTitle("#不是标题\n# 真标题"), "真标题");
  EXPECT_EQ(docseek::extractMarkdownTitle("####### 七个井号\n# 真标题"), "真标题");
}

TEST(MdTitleExtract, EmptyHeadingSkipped) {
  EXPECT_EQ(docseek::extractMarkdownTitle("#   \n# 后面的标题"), "后面的标题");
}

TEST(MdTitleExtract, NoHeadingReturnsEmpty) {
  EXPECT_EQ(docseek::extractMarkdownTitle("只有正文\n第二行"), "");
  EXPECT_EQ(docseek::extractMarkdownTitle(""), "");
}

// 测试夹具：与 test_indexer.cpp 的 IdxFixture 同构，但用独立临时目录，避免串扰。
struct MdTitleFixture : public ::testing::Test {
  fs::path dir;
  std::string dbPath;

  void SetUp() override {
    dir = fs::temp_directory_path() / "docseek_mdtitle_test";
    std::error_code ec;
    fs::remove_all(dir, ec);
    fs::create_directories(dir);
    dbPath = (fs::temp_directory_path() / "docseek_mdtitle_test.db").string();
    fs::remove(dbPath, ec);
  }

  void writeFile(const std::string& rel, const std::string& content) {
    fs::path p = dir / rel;
    fs::create_directories(p.parent_path());
    std::ofstream ofs(p, std::ios::binary | std::ios::trunc);
    ofs.write(content.data(), static_cast<std::streamsize>(content.size()));
    ofs.close();
  }
};

TEST_F(MdTitleFixture, MdTitleExtractedAndStemFallback) {
  writeFile("doc.md", "# 真实标题\n正文内容");
  writeFile("plain.md", "只有正文，没有标题行");
  auto db = docseek::Database::open(dbPath);
  docseek::Indexer indexer(db, {});
  auto st = indexer.indexPaths({dir.string()});
  EXPECT_EQ(st.added, 2u);
  auto doc = db.findByPath((dir / "doc.md").string());
  ASSERT_TRUE(doc.has_value());
  EXPECT_EQ(doc->title, "真实标题");
  auto plain = db.findByPath((dir / "plain.md").string());
  ASSERT_TRUE(plain.has_value());
  EXPECT_EQ(plain->title, "plain");
}

TEST_F(MdTitleFixture, StaleTitleRefreshedWhenMtimeSizeUnchanged) {
  const std::string content = "# 新逻辑提取的标题\n正文内容";
  writeFile("doc.md", content);
  auto db = docseek::Database::open(dbPath);
  docseek::Indexer indexer(db, {});
  indexer.indexPaths({dir.string()});
  auto rec = db.findByPath((dir / "doc.md").string());
  ASSERT_TRUE(rec.has_value());
  EXPECT_EQ(rec->title, "新逻辑提取的标题");
  // 模拟旧库记录：标题被写成 stem，但 mtime/size 与现文件一致。
  db.upsert((dir / "doc.md").string(), "doc", content, rec->mtime, rec->size);
  auto corrupted = db.findByPath((dir / "doc.md").string());
  ASSERT_TRUE(corrupted.has_value());
  EXPECT_EQ(corrupted->title, "doc");
  // 重新索引：mtime/size 未变但标题变了，应走 upsert 刷新为真实标题。
  auto st = indexer.indexPaths({dir.string()});
  EXPECT_EQ(st.updated, 1u);
  EXPECT_EQ(st.unchanged, 0u);
  auto healed = db.findByPath((dir / "doc.md").string());
  ASSERT_TRUE(healed.has_value());
  EXPECT_EQ(healed->title, "新逻辑提取的标题");
  // 再跑一遍：标题已一致，回到 unchanged（刷新是一次性自愈）。
  auto st2 = indexer.indexPaths({dir.string()});
  EXPECT_EQ(st2.unchanged, 1u);
  EXPECT_EQ(st2.updated, 0u);
}
