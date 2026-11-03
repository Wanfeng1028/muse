#include "docseek/database.h"
#include "docseek/searcher.h"

using namespace docseek;
#include <gtest/gtest.h>
#include <filesystem>
#include <string>
#include <vector>
#include <cmath>

namespace fs = std::filesystem;
namespace {
fs::path makeDsDir(const std::string& name) {
fs::path base = fs::current_path() / "test-tmp" / name;
std::error_code ec; fs::remove_all(base, ec); fs::create_directories(base, ec);
return base;
}
}

TEST(ServeSearchDeep, MixedChineseEnglish) {
auto dir = makeDsDir("ds_serve_1");
auto db = Database::open((dir / "x.db").string());
db.upsert("a.txt", "Kubernetes 部署指南：全文检索服务上线", "Kubernetes 部署指南：全文检索服务上线", 0, 0);
Searcher s(db);
auto hits1 = s.search("部署指南", 10);
EXPECT_FALSE(hits1.empty());
auto hits2 = s.search("kubernetes", 10);
EXPECT_FALSE(hits2.empty());
}

TEST(ServeSearchDeep, TitleBoost) {
auto dir = makeDsDir("ds_serve_2");
auto db = Database::open((dir / "x.db").string());
db.upsert("title.txt", "全文检索", "这是一篇关于数据库的普通文章", 0, 0);
db.upsert("body.txt", "普通标题", "全文检索是核心技术", 0, 0);
Searcher s(db);
SearchWeights w = s.weights();
w.titleBoost = 2.0;
s.setWeights(w);
auto hits = s.search("全文检索", 10);
ASSERT_EQ(hits.size(), 2u);
EXPECT_NE(hits[0].path.find("title.txt"), std::string::npos);
}

TEST(ServeSearchDeep, OrFallback) {
auto dir = makeDsDir("ds_serve_3");
auto db = Database::open((dir / "x.db").string());
db.upsert("a.txt", "文档A", "全文检索技术", 0, 0);
db.upsert("b.txt", "文档B", "天气预报信息", 0, 0);
Searcher s(db);
auto hits = s.search("全文检索 天气预报", 10);
EXPECT_FALSE(hits.empty());
}

TEST(ServeSearchDeep, NoOrFallbackSingleToken) {
auto dir = makeDsDir("ds_serve_4");
auto db = Database::open((dir / "x.db").string());
db.upsert("a.txt", "文档A", "全文检索技术", 0, 0);
Searcher s(db);
auto hits = s.search("量子计算", 10);
EXPECT_TRUE(hits.empty());
}

TEST(ServeSearchDeep, LimitBoundaries) {
auto dir = makeDsDir("ds_serve_5");
auto db = Database::open((dir / "x.db").string());
db.upsert("a.txt", "标题A", "全文检索", 0, 0);
db.upsert("b.txt", "标题B", "全文检索", 0, 0);
db.upsert("c.txt", "标题C", "全文检索", 0, 0);
Searcher s(db);
auto hits1 = s.search("全文检索", 1);
EXPECT_EQ(hits1.size(), 1u);
auto hits0 = s.search("全文检索", 0);
EXPECT_TRUE(hits0.empty());
auto hitsNeg = s.search("全文检索", -5);
EXPECT_TRUE(hitsNeg.empty());
}

TEST(ServeSearchDeep, SpecialCharsNoThrow) {
auto dir = makeDsDir("ds_serve_6");
auto db = Database::open((dir / "x.db").string());
db.upsert("a.txt", "标题", "内容", 0, 0);
Searcher s(db);
EXPECT_NO_THROW(s.search("\"全文检索\"", 10));
EXPECT_NO_THROW(s.search("(全文检索)", 10));
EXPECT_NO_THROW(s.search("*全文检索*", 10));
EXPECT_NO_THROW(s.search("C++ 全文检索", 10));
}

TEST(ServeSearchDeep, EmptyQuery) {
auto dir = makeDsDir("ds_serve_7");
auto db = Database::open((dir / "x.db").string());
db.upsert("a.txt", "标题", "内容", 0, 0);
Searcher s(db);
EXPECT_TRUE(s.search("", 10).empty());
EXPECT_TRUE(s.search("   ", 10).empty());
EXPECT_TRUE(s.search("!!!", 10).empty());
}

TEST(ServeSearchDeep, SnippetNotEmpty) {
auto dir = makeDsDir("ds_serve_8");
auto db = Database::open((dir / "x.db").string());
db.upsert("a.txt", "标题", "全文检索是核心技术", 0, 0);
Searcher s(db);
auto hits = s.search("全文检索", 10);
ASSERT_FALSE(hits.empty());
EXPECT_FALSE(hits[0].snippet.empty());
}

TEST(ServeSearchDeep, ExplainConsistency) {
auto dir = makeDsDir("ds_serve_9");
auto db = Database::open((dir / "x.db").string());
db.upsert("a.txt", "标题", "全文检索是核心技术", 0, 0);
db.upsert("b.txt", "标题B", "全文检索技术", 0, 0);
Searcher s(db);
auto hits = s.search("全文检索", 10);
auto explained = s.explain("全文检索", 10);
ASSERT_EQ(hits.size(), explained.size());
}
