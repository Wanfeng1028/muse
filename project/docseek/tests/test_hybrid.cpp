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

TEST(HybridTest, WeightsDefaultEquivalentToV1) {
    std::string dir = hybridTmp("weights_t2_default");
    docseek::Database db = docseek::Database::open(dir + "/w.db");
    db.upsert(dir + "/a.txt", "全文检索指南", "全文检索技术详解", 1000, 10);
    db.upsert(dir + "/b.txt", "其他", "全文检索指南内容", 1000, 10);

    docseek::Searcher s1(db);
    docseek::Searcher s2(db, docseek::SearchWeights{});

    auto r1 = s1.search("全文检索", 10);
    auto r2 = s2.search("全文检索", 10);

    ASSERT_EQ(r1.size(), r2.size());
    for (size_t i = 0; i < r1.size(); ++i) {
        EXPECT_EQ(r1[i].path, r2[i].path);
        EXPECT_DOUBLE_EQ(r1[i].score, r2[i].score);
    }
}

TEST(HybridTest, WeightsTitleBoostZero) {
    std::string dir = hybridTmp("weights_t2_title");
    docseek::Database db = docseek::Database::open(dir + "/w.db");
    db.upsert(dir + "/a.txt", "全文检索指南", "全文检索技术详解", 1000, 10);
    db.upsert(dir + "/b.txt", "其他", "全文检索指南内容", 1000, 10);

    docseek::Searcher sDef(db);
    docseek::Searcher sZero(db, docseek::SearchWeights{0.0, 2.0});

    auto rDef = sDef.search("全文检索", 10);
    auto rZero = sZero.search("全文检索", 10);

    double aDef = 0.0, aZero = 0.0, bDef = 0.0, bZero = 0.0;
    for (const auto& r : rDef) {
        if (r.path == dir + "/a.txt") aDef = r.score;
        if (r.path == dir + "/b.txt") bDef = r.score;
    }
    for (const auto& r : rZero) {
        if (r.path == dir + "/a.txt") aZero = r.score;
        if (r.path == dir + "/b.txt") bZero = r.score;
    }

    EXPECT_DOUBLE_EQ(aZero, aDef - 1.0);
    EXPECT_DOUBLE_EQ(bZero, bDef);
}

TEST(HybridTest, WeightsPhraseBoostZero) {
    std::string dir = hybridTmp("weights_t2_phrase");
    docseek::Database db = docseek::Database::open(dir + "/w.db");
    db.upsert(dir + "/a.txt", "全文检索指南", "全文检索技术详解", 1000, 10);
    db.upsert(dir + "/b.txt", "其他", "全文检索指南内容", 1000, 10);

    docseek::Searcher sDef(db);
    docseek::Searcher sZero(db, docseek::SearchWeights{1.0, 0.0});

    auto rDef = sDef.search("全文检索", 10);
    auto rZero = sZero.search("全文检索", 10);

    double aDef = 0.0, aZero = 0.0;
    for (const auto& r : rDef) {
        if (r.path == dir + "/a.txt") aDef = r.score;
    }
    for (const auto& r : rZero) {
        if (r.path == dir + "/a.txt") aZero = r.score;
    }

    EXPECT_DOUBLE_EQ(aZero, aDef - 2.0);
}

TEST(HybridTest, WeightsPhraseBoostScales) {
    std::string dir = hybridTmp("weights_t2_scales");
    docseek::Database db = docseek::Database::open(dir + "/w.db");
    db.upsert(dir + "/a.txt", "全文检索指南", "全文检索技术详解", 1000, 10);
    db.upsert(dir + "/b.txt", "其他", "全文检索指南内容", 1000, 10);

    docseek::Searcher sZero(db, docseek::SearchWeights{0.0, 0.0});
    docseek::Searcher sHundred(db, docseek::SearchWeights{0.0, 100.0});

    auto rZero = sZero.search("全文检索", 10);
    auto rHundred = sHundred.search("全文检索", 10);

    double aZero = 0.0, aHundred = 0.0, bZero = 0.0, bHundred = 0.0;
    for (const auto& r : rZero) {
        if (r.path == dir + "/a.txt") aZero = r.score;
        if (r.path == dir + "/b.txt") bZero = r.score;
    }
    for (const auto& r : rHundred) {
        if (r.path == dir + "/a.txt") aHundred = r.score;
        if (r.path == dir + "/b.txt") bHundred = r.score;
    }

    EXPECT_DOUBLE_EQ(aHundred, aZero + 100.0);
    EXPECT_DOUBLE_EQ(bHundred, bZero + 100.0);
}

TEST(HybridTest, WeightsSetWeights) {
    std::string dir = hybridTmp("weights_t2_set");
    docseek::Database db = docseek::Database::open(dir + "/w.db");
    db.upsert(dir + "/a.txt", "全文检索指南", "全文检索技术详解", 1000, 10);
    db.upsert(dir + "/b.txt", "其他", "全文检索指南内容", 1000, 10);

    docseek::Searcher sCtor(db, docseek::SearchWeights{3.0, 0.5});
    docseek::Searcher sSet(db);
    sSet.setWeights(docseek::SearchWeights{3.0, 0.5});

    EXPECT_DOUBLE_EQ(sSet.weights().titleBoost, 3.0);
    EXPECT_DOUBLE_EQ(sSet.weights().phraseBoost, 0.5);

    auto rCtor = sCtor.search("全文检索", 10);
    auto rSet = sSet.search("全文检索", 10);

    ASSERT_EQ(rCtor.size(), rSet.size());
    for (size_t i = 0; i < rCtor.size(); ++i) {
        EXPECT_EQ(rCtor[i].path, rSet[i].path);
        EXPECT_DOUBLE_EQ(rCtor[i].score, rSet[i].score);
    }
}
