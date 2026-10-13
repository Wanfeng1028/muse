// 混合检索 v1（纯词法）测试：AND 命中、OR 回退、title/短语加成重排序。
#include <gtest/gtest.h>

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

namespace {

bool containsPath(const std::vector<docseek::Hit>& hits, const std::string& path) {
    for (const docseek::Hit& h : hits) {
        if (h.path == path) return true;
    }
    return false;
}

int indexOfPath(const std::vector<docseek::Hit>& hits, const std::string& path) {
    for (size_t i = 0; i < hits.size(); ++i) {
        if (hits[i].path == path) return static_cast<int>(i);
    }
    return -1;
}

std::string hybridTmp(const std::string& name) {
    fs::path dir = fs::current_path() / "test-tmp" / ("hybrid_" + name);
    std::error_code ec;
    fs::remove_all(dir, ec);
    fs::create_directories(dir, ec);
    return dir.string();
}

}  // namespace

TEST(HybridTest, AndMatchOrdering) {
    std::string dir = hybridTmp("and");
    docseek::Database db = docseek::Database::open(dir + "/case1.db");
    db.upsert(dir + "/doc1.txt", "检索", "苹果香蕉", 1000, 10);
    db.upsert(dir + "/doc2.txt", "水果", "全文检索技术", 1000, 10);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("检索", 10);
    EXPECT_TRUE(containsPath(hits, dir + "/doc1.txt"));
    EXPECT_TRUE(containsPath(hits, dir + "/doc2.txt"));

    auto hits2 = searcher.search("全文检索", 10);
    EXPECT_TRUE(containsPath(hits2, dir + "/doc2.txt"));
    EXPECT_FALSE(containsPath(hits2, dir + "/doc1.txt"));
}

TEST(HybridTest, OrFallback) {
    std::string dir = hybridTmp("or");
    docseek::Database db = docseek::Database::open(dir + "/case2.db");
    db.upsert(dir + "/a.txt", "手机", "苹果手机", 1000, 10);
    db.upsert(dir + "/b.txt", "水果", "香蕉水果", 1000, 10);

    docseek::Searcher searcher(db);
    // AND 为空 → 回退 OR，两个都命中。
    auto hits = searcher.search("苹果 香蕉", 10);
    EXPECT_TRUE(containsPath(hits, dir + "/a.txt"));
    EXPECT_TRUE(containsPath(hits, dir + "/b.txt"));
}

TEST(HybridTest, TitleBoost) {
    std::string dir = hybridTmp("title");
    docseek::Database db = docseek::Database::open(dir + "/case3.db");
    db.upsert(dir + "/title.txt", "全文检索指南", "aaa", 1000, 10);
    db.upsert(dir + "/body.txt", "其他", "全文检索指南bbb", 1000, 10);

    docseek::Searcher searcher(db);
    auto hits = searcher.search("全文检索", 10);
    EXPECT_TRUE(containsPath(hits, dir + "/title.txt"));
    EXPECT_TRUE(containsPath(hits, dir + "/body.txt"));
    int titleIdx = indexOfPath(hits, dir + "/title.txt");
    int bodyIdx = indexOfPath(hits, dir + "/body.txt");
    EXPECT_GE(titleIdx, 0);
    EXPECT_GE(bodyIdx, 0);
    EXPECT_LT(titleIdx, bodyIdx);
}

TEST(HybridTest, BuildOrMatchQuery) {
    EXPECT_EQ(docseek::Searcher::buildOrMatchQuery("a b"), "\"a\" OR \"b\"");
    EXPECT_EQ(docseek::Searcher::buildOrMatchQuery("x"), "\"x\"");
    EXPECT_EQ(docseek::Searcher::buildOrMatchQuery(""), "");
}
