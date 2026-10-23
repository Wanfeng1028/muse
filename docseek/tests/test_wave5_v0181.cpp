// tests/test_wave5_v0181.cpp
//
// Wave5 三个修复的单元测试（R7 时间序数加成 / RangeAnswerBonus 范围加分 /
// SynonymPassage 同义词段落回退）。
//
// 说明：全部使用公开 API（Searcher::search、rankPassages、findSynonyms），
// 不 mock 核心逻辑。风格参考 tests/test_locate.cpp。

#include <gtest/gtest.h>

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

#ifdef _WIN32
#include <process.h>
#define DOCSEEK_GETPID _getpid
#else
#include <unistd.h>
#define DOCSEEK_GETPID getpid
#endif

#include "docseek/database.h"
#include "docseek/passage_ranker.h"
#include "docseek/query_parser.h"
#include "docseek/searcher.h"
#include "docseek/synonyms.h"

namespace {

// 与 test_locate.cpp 一致的临时 DB 路径构造：temp_directory_path + pid。
std::string makeTempDbPath(const std::string& tag) {
    std::filesystem::path dir = std::filesystem::temp_directory_path();
    std::string name = "docseek_test_wave5_" + tag + "_" +
                       std::to_string(static_cast<long long>(DOCSEEK_GETPID())) + ".db";
    return (dir / name).string();
}

// 在返回的 Hit 列表中查找某个 path 的下标，找不到返回 -1。
int findHitIndex(const std::vector<docseek::Hit>& hits, const std::string& path) {
    for (size_t i = 0; i < hits.size(); ++i) {
        if (hits[i].path == path) {
            return static_cast<int>(i);
        }
    }
    return -1;
}

// 在 rankPassages 返回的段落列表中，找到第一个包含 needle 的段落下标。
int findPassageIndex(const std::vector<docseek::Passage>& ps, const std::string& needle) {
    for (size_t i = 0; i < ps.size(); ++i) {
        if (ps[i].text.find(needle) != std::string::npos) {
            return static_cast<int>(i);
        }
    }
    return -1;
}

// 取某段落匹配词列表中是否含指定词。
bool matchedContains(const docseek::Passage& p, const std::string& term) {
    for (const auto& t : p.matched_terms) {
        if (t == term) {
            return true;
        }
    }
    return false;
}

}  // namespace

// ---------------------------------------------------------------------------
// Suite R7TimeOrdinal：单 token 时间序数加成（黑盒 search）
// ---------------------------------------------------------------------------

// R7 生效：A 含多个“第 N 个月”结构，B 无该结构，A 应排在 B 之前。
TEST(R7TimeOrdinal, R7_BoostsOrdinalDoc) {
    const std::string dbPath = makeTempDbPath("r7_boost");
    std::filesystem::remove(dbPath);

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/r7/a.md", "a",
              "第一个月：基础练习。第二个月：和弦转换。第三个月：完整曲目。", 100, 10);
    db.upsert("/r7/b.md", "三个月实录", "随手记一记。", 100, 10);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("三个月", 10);

    ASSERT_FALSE(hits.empty());
    int ia = findHitIndex(hits, "/r7/a.md");
    int ib = findHitIndex(hits, "/r7/b.md");
    ASSERT_GE(ia, 0);
    ASSERT_GE(ib, 0);
    EXPECT_LT(ia, ib);

    std::filesystem::remove(dbPath);
}

// R7 需要至少两个不同的时间序数：C 只含一次“第三个月”，不应被抬到 A 之前。
TEST(R7TimeOrdinal, R7_RequiresTwoDistinct) {
    const std::string dbPath = makeTempDbPath("r7_distinct");
    std::filesystem::remove(dbPath);

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/r7/a.md", "a",
              "第一个月：基础练习。第二个月：和弦转换。第三个月：完整曲目。", 100, 10);
    db.upsert("/r7/c.md", "c", "第三个月。", 100, 10);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("三个月", 10);

    ASSERT_FALSE(hits.empty());
    int ia = findHitIndex(hits, "/r7/a.md");
    int ic = findHitIndex(hits, "/r7/c.md");
    ASSERT_GE(ia, 0);
    ASSERT_GE(ic, 0);
    // A 仍应在 C 之前（C 的 distinct 序数只有 1，不触发 R7）。
    EXPECT_LT(ia, ic);

    std::filesystem::remove(dbPath);
}

// R7 不影响非时间 token：含“吉他”的文档仍应被召回。
TEST(R7TimeOrdinal, R7_NonTimeTokenUnaffected) {
    const std::string dbPath = makeTempDbPath("r7_nontime");
    std::filesystem::remove(dbPath);

    docseek::Database db = docseek::Database::open(dbPath);
    db.upsert("/r7/g.md", "吉他入门", "吉他基础练习与和弦讲解。", 100, 10);

    docseek::Searcher searcher(db);
    std::vector<docseek::Hit> hits = searcher.search("吉他", 10);

    ASSERT_FALSE(hits.empty());
    int ig = findHitIndex(hits, "/r7/g.md");
    EXPECT_GE(ig, 0);

    std::filesystem::remove(dbPath);
}

// ---------------------------------------------------------------------------
// Suite RangeAnswerBonus：rankPassages 范围答案加分
// ---------------------------------------------------------------------------

// 含“范围”关键词且段落有阿拉伯数字+单位：加分，差值约 0.08。
TEST(RangeAnswerBonus, RangeBonus_Applies) {
    docseek::ParsedQuery pq;
    pq.keywords = {"弦距", "范围"};

    const std::string pathA = "/range/a.md";
    const std::string contentA =
        "弦距范围：2.5毫米到3.5毫米，可根据手感调整。";
    const std::string pathB = "/range/b.md";
    const std::string contentB =
        "弦距范围：因琴而异，需视手感与演奏风格而定。";

    std::vector<docseek::Passage> psA =
        rankPassages(1, pathA, contentA, pq, 1);
    std::vector<docseek::Passage> psB =
        rankPassages(2, pathB, contentB, pq, 1);

    ASSERT_FALSE(psA.empty());
    ASSERT_FALSE(psB.empty());
    EXPECT_NEAR(psA[0].score - psB[0].score, 0.08, 0.001);
}

// 中文数字（十二品）不触发加分。
TEST(RangeAnswerBonus, RangeBonus_ChineseNumeralNoTrigger) {
    docseek::ParsedQuery pq;
    pq.keywords = {"弦距", "范围"};

    const std::string contentCn = "弦距范围：十二品处的参考值，详见表格。";
    const std::string contentPlain = "弦距范围：因琴而异，需视手感与演奏风格而定。";

    std::vector<docseek::Passage> psCn =
        rankPassages(1, "/range/cn.md", contentCn, pq, 1);
    std::vector<docseek::Passage> psPlain =
        rankPassages(2, "/range/plain.md", contentPlain, pq, 1);

    ASSERT_FALSE(psCn.empty());
    ASSERT_FALSE(psPlain.empty());
    EXPECT_LT(std::abs(psCn[0].score - psPlain[0].score), 0.001);
}

// 只有一个数字（1毫米）不触发加分。
TEST(RangeAnswerBonus, RangeBonus_SingleNumberNoTrigger) {
    docseek::ParsedQuery pq;
    pq.keywords = {"弦距", "范围"};

    const std::string contentOne = "弦距范围：1毫米。";
    const std::string contentPlain = "弦距范围：因琴而异，需视手感与演奏风格而定。";

    std::vector<docseek::Passage> psOne =
        rankPassages(1, "/range/one.md", contentOne, pq, 1);
    std::vector<docseek::Passage> psPlain =
        rankPassages(2, "/range/plain2.md", contentPlain, pq, 1);

    ASSERT_FALSE(psOne.empty());
    ASSERT_FALSE(psPlain.empty());
    EXPECT_LT(std::abs(psOne[0].score - psPlain[0].score), 0.001);
}

// 没有“范围”关键词时不触发加分。
TEST(RangeAnswerBonus, RangeBonus_NoRangeWordNoTrigger) {
    docseek::ParsedQuery pq;
    pq.keywords = {"弦距"};  // 无“范围”

    const std::string contentNum = "弦距：2.5毫米到3.5毫米，可调整。";
    const std::string contentPlain = "弦距：因琴而异，需视手感而定。";

    std::vector<docseek::Passage> psNum =
        rankPassages(1, "/range/num.md", contentNum, pq, 1);
    std::vector<docseek::Passage> psPlain =
        rankPassages(2, "/range/plain3.md", contentPlain, pq, 1);

    ASSERT_FALSE(psNum.empty());
    ASSERT_FALSE(psPlain.empty());
    EXPECT_LT(std::abs(psNum[0].score - psPlain[0].score), 0.001);
}

TEST(RangeAnswerBonus, RangeBonus_BareRangeApplies) {
    docseek::ParsedQuery pq;
    pq.keywords = {"弦距", "范围"};

    const std::string pathA = "/range/a.md";
    const std::string contentA =
        "弦距范围：2.5到3.5，另一处7到8，可根据手感调整。";
    const std::string pathB = "/range/b.md";
    const std::string contentB =
        "弦距范围：因琴而异，需视手感与演奏风格而定。";

    std::vector<docseek::Passage> psA =
        rankPassages(1, pathA, contentA, pq, 1);
    std::vector<docseek::Passage> psB =
        rankPassages(2, pathB, contentB, pq, 1);

    ASSERT_FALSE(psA.empty());
    ASSERT_FALSE(psB.empty());
    EXPECT_NEAR(psA[0].score - psB[0].score, 0.08, 0.001);
}

TEST(RangeAnswerBonus, RangeBonus_BareRangeDashForm) {
    docseek::ParsedQuery pq;
    pq.keywords = {"弦距", "范围"};

    const std::string pathA = "/range/a.md";
    const std::string contentA =
        "弦距范围：3-5，另一处6-8，可根据手感调整。";
    const std::string pathB = "/range/b.md";
    const std::string contentB =
        "弦距范围：因琴而异，需视手感与演奏风格而定。";

    std::vector<docseek::Passage> psA =
        rankPassages(1, pathA, contentA, pq, 1);
    std::vector<docseek::Passage> psB =
        rankPassages(2, pathB, contentB, pq, 1);

    ASSERT_FALSE(psA.empty());
    ASSERT_FALSE(psB.empty());
    EXPECT_NEAR(psA[0].score - psB[0].score, 0.08, 0.001);
}

TEST(RangeAnswerBonus, RangeBonus_BareRangeSingleNoTrigger) {
    docseek::ParsedQuery pq;
    pq.keywords = {"弦距", "范围"};

    const std::string pathOne = "/range/one.md";
    const std::string contentOne =
        "弦距范围：9到10。";
    const std::string pathPlain = "/range/plain.md";
    const std::string contentPlain =
        "弦距范围：因琴而异。";

    std::vector<docseek::Passage> psOne =
        rankPassages(1, pathOne, contentOne, pq, 1);
    std::vector<docseek::Passage> psPlain =
        rankPassages(2, pathPlain, contentPlain, pq, 1);

    ASSERT_FALSE(psOne.empty());
    ASSERT_FALSE(psPlain.empty());
    EXPECT_LT(std::abs(psOne[0].score - psPlain[0].score), 0.001);
}

// ---------------------------------------------------------------------------
// Suite SynonymPassage：同义词表 + rankPassages 回退
// ---------------------------------------------------------------------------

// 同义词表：琴弦 -> 含“弦”；不存在的词返回 nullptr。
TEST(SynonymPassage, SynonymTable_HasQinXian) {
    const docseek::SynonymEntry* e = docseek::findSynonyms("琴弦");
    ASSERT_NE(e, nullptr);
    ASSERT_GE(e->expansionCount, 1);

    bool hasXian = false;
    for (int i = 0; i < e->expansionCount; ++i) {
        if (e->expansions[i] != nullptr &&
            std::string(e->expansions[i]) == "弦") {
            hasXian = true;
            break;
        }
    }
    EXPECT_TRUE(hasXian);

    EXPECT_EQ(docseek::findSynonyms("不存在的词"), nullptr);
}

// 同义词回退：查询“琴弦”，段落只含“弦”，matched_terms 应含“琴弦”。
TEST(SynonymPassage, SynonymPassage_MatchesXian) {
    docseek::ParsedQuery pq;
    pq.keywords = {"琴弦"};

    const std::string contentMatch = "换弦时注意张力，避免断弦。";
    std::vector<docseek::Passage> psMatch =
        rankPassages(1, "/syn/match.md", contentMatch, pq, 1);

    ASSERT_FALSE(psMatch.empty());
    int im = findPassageIndex(psMatch, "换弦时注意张力");
    ASSERT_GE(im, 0);
    EXPECT_TRUE(matchedContains(psMatch[im], "琴弦"));

    // 对照组：既无“琴弦”也无“弦”。
    const std::string contentMiss = "今天天气不错，适合出门散步。";
    std::vector<docseek::Passage> psMiss =
        rankPassages(2, "/syn/miss.md", contentMiss, pq, 1);

    if (!psMiss.empty()) {
        int in = findPassageIndex(psMiss, "今天天气不错");
        if (in >= 0) {
            EXPECT_FALSE(matchedContains(psMiss[in], "琴弦"));
        }
    }
}
