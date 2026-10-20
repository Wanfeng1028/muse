#include <gtest/gtest.h>
#include <filesystem>
#include <string>
#include "docseek/database.h"
#include "docseek/searcher.h"
#include "docseek/locator.h"
#include "docseek/passage_ranker.h"

using namespace docseek;
namespace fs = std::filesystem;

TEST(WeightedFlip_ThematicBeatsNoise, WeightedFlip_ThematicBeatsNoise) {
    ParsedQuery pq;
    pq.keywords = {"备份", "数据", "建议"};
    std::string thematic = "数据备份指南\n备份策略：每天备份一次。\n增量备份每周做一次，全量备份每月一次。";
    std::string noise = "能\n点\n算\n一回\n建议\n建议\n建议\n建议\n备份一次";
    TermWeights w;
    w.weights["备份"] = 2.5;
    w.weights["数据"] = 2.0;
    w.weights["建议"] = 0.6;
    auto ra = rankPassages(1, "a.md", thematic, pq, 3, w);
    auto rb = rankPassages(2, "b.md", noise, pq, 3, w);
    ASSERT_FALSE(ra.empty());
    ASSERT_FALSE(rb.empty());
    EXPECT_GT(ra[0].score, rb[0].score);
}

TEST(UniformWeights_NoFlipGuarantee, UniformWeights_NoFlipGuarantee) {
    ParsedQuery pq;
    pq.keywords = {"备份", "数据", "建议"};
    std::string thematic = "数据备份指南\n备份策略：每天备份一次。\n增量备份每周做一次，全量备份每月一次。";
    std::string noise = "能\n点\n算\n一回\n建议\n建议\n建议\n建议\n备份一次";
    auto ra = rankPassages(1, "a.md", thematic, pq, 3);
    auto rb = rankPassages(2, "b.md", noise, pq, 3);
    EXPECT_FALSE(ra.empty());
    EXPECT_FALSE(rb.empty());
}

TEST(MissingWeight_DefaultsToOne, MissingWeight_DefaultsToOne) {
    TermWeights w;
    EXPECT_DOUBLE_EQ(w.weightOf("备份"), 1.0);
}

TEST(Locator_EndToEnd_NoCrash, Locator_EndToEnd_NoCrash) {
    fs::path dir = fs::temp_directory_path() / "docseek_v021_reg";
    auto db = Database::open((dir / "test.db").string());
    db.upsert("backup.md", "数据备份指南", "备份策略：每天备份一次。增量备份每周做，全量备份每月一次。", 1000, 100);
    db.upsert("noise.md", "随笔", "能点算一回。建议大家多喝水。建议早睡。建议备份重要文件。", 1000, 100);
    db.upsert("other.md", "通知", "明天下午开会，请准时参加。", 1000, 100);
    Searcher searcher(db);
    Locator locator(db, searcher);
    LocateOptions opts;
    opts.limit = 3;
    auto res = locator.locate("数据备份多久做一次比较好", opts);
    EXPECT_FALSE(res.empty());
    std::error_code ec;
    fs::remove_all(dir, ec);
}
