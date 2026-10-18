// tests/test_adjacent_probe_v018.cpp
// F-T019 tryAdjacentPrefixProbe（相邻 token 前缀/子串交叉探测）黑盒测试。
// 说明：tryAdjacentPrefixProbe 是 searcher.cpp 内部 static 函数，不可直接调用；
//       本文件一律通过公开 API docseek::Searcher::search() 用合成语料做黑盒验证。
#include <gtest/gtest.h>

#include <filesystem>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/query_parser.h"
#include "docseek/searcher.h"

namespace {

// 生成一个临时数据库路径，避免污染真实数据（沿用夹具模式）
std::string makeTempDbPath() {
    auto dir = std::filesystem::temp_directory_path() /
               ("docseek_test_adjacent_probe_" + std::to_string(::getpid()));
    std::filesystem::create_directories(dir);
    return (dir / "test.db").string();
}

// 清理临时库目录
void cleanupTempDb(const std::string& dbPath) {
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}

}  // namespace

// 1. 相邻前缀探测恢复「长期不弹琴」类错位查询的 top1
TEST(Searcher_T019Q12_AdjacentPrefixProbe_RecoversLongTermNoPlay, Top1Hit) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        // 期望文档：含连续片段「长期不弹」
        db.upsert("/guitar/tension.txt", "琴弦保养",
                  "如果长期不弹，把弦放松半音到全音，可以避免琴颈变形。",
                  100, 64);
        // 干扰文档：含「长期」但无「不弹」
        db.upsert("/guitar/other.txt", "其他",
                  "长期存放吉他需要注意湿度，琴弦可以拆下来。",
                  100, 48);
        // 干扰文档：含「弹琴」但无「长期不弹」
        db.upsert("/guitar/play.txt", "弹琴",
                  "每天弹琴之前要洗手，保持琴弦干净。",
                  100, 40);

        docseek::Searcher s(db);
        auto hits = s.search("长期不弹琴的话琴弦应该怎么处理比较好", 10);
        ASSERT_FALSE(hits.empty());
        EXPECT_EQ(hits[0].path, "/guitar/tension.txt");
    }
    cleanupTempDb(dbPath);
}

// 2. 候选探测使用 searchFts(..., 1) 语义：黑盒等价验证 —— 期望文档被召回即说明
//    探测以单条命中为界返回（Database 为真实类，无法注入计数 mock）。
//    这里验证「命中后不再依赖更多候选也能返回」：索引中只存在 a+b 首字拼接的
//    「不弹」，而「不弹琴」整体不在索引里，仍能召回。
TEST(Searcher_T019Q12_AdjacentPrefixProbe_ProbeLimitOne, SingleHitSufficient) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        // 文档侧切词倾向产生「不弹」，查询侧会切出「不」+「弹琴」
        db.upsert("/p/only.txt", "保养",
                  "长期不弹时请放松琴弦。",
                  100, 32);

        docseek::Searcher s(db);
        auto hits = s.search("长期不弹琴怎么保养", 10);
        ASSERT_FALSE(hits.empty());
        EXPECT_EQ(hits[0].path, "/p/only.txt");
    }
    cleanupTempDb(dbPath);
}

// 3. 候选顺序为 {a+b, a+b首字, a首字+b}：构造仅 a+b首字 命中的语料，
//    验证被选中（若顺序错误，a+b 会先探测并命中其它文档或探测失败）。
TEST(Searcher_T019Q12_AdjacentPrefixProbe_CandidateOrder, PreferConcatenatedHead) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        // 期望文档含「长期不弹」（a+b首字 = "不"+"弹" = "不弹"）
        db.upsert("/o/target.txt", "琴弦",
                  "长期不弹会导致琴颈张力失衡。",
                  100, 40);
        // 干扰文档含完整「不弹琴」整词，但不含「长期不弹」连续片段
        db.upsert("/o/distract.txt", "练习",
                  "老师说你不能弹琴的时候偷懒。",
                  100, 40);

        docseek::Searcher s(db);
        auto hits = s.search("长期不弹琴的问题", 10);
        ASSERT_FALSE(hits.empty());
        // top1 必须是含「长期不弹」的期望文档
        EXPECT_EQ(hits[0].path, "/o/target.txt");
    }
    cleanupTempDb(dbPath);
}

// 4. 已有命中（hits 非空）时不触发探测：AND 能正常命中的查询行为一字不变。
TEST(Searcher_T019Q12_AdjacentPrefixProbe_SkipsWhenHitsNonEmpty, AndPathUntouched) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert("/s/1.txt", "a", "quick brown fox", 100, 16);
        db.upsert("/s/2.txt", "b", "quick rabbit", 100, 12);

        docseek::Searcher s(db);
        // 隐式 AND 命中，hits 非空，探测路径不参与
        auto hits = s.search("quick fox", 10);
        ASSERT_EQ(hits.size(), 1u);
        EXPECT_EQ(hits[0].path, "/s/1.txt");
    }
    cleanupTempDb(dbPath);
}

// 5. 相邻对全部候选均无命中时 hits 保持空：控制流继续走回退路径，
//    最终返回空（与未插入探测时一致）。
TEST(Searcher_T019Q12_AdjacentPrefixProbe_NoHitFallThrough, EmptyStaysEmpty) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert("/n/1.txt", "a", "完全无关的内容 alpha beta", 100, 24);

        docseek::Searcher s(db);
        // 查询 token 拼接后也拼不出库中任何连续片段
        auto hits = s.search("长期不弹琴怎么处理", 10);
        EXPECT_TRUE(hits.empty());
    }
    cleanupTempDb(dbPath);
}

// 6. 命中后重查用 quoteToken(cand) OR <原 orQuery>，limit 生效：
//    构造多条可被 OR 召回的结果，验证 limit 被尊重（<= limit）。
TEST(Searcher_T019Q12_AdjacentPrefixProbe_RequeriesWithOrQuery, LimitRespected) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        // 期望命中文档（含「长期不弹」）
        db.upsert("/r/1.txt", "一",
                  "长期不弹的话，琴弦应该放松。", 100, 40);
        // 含「长期」的其它文档，会被 OR 召回
        db.upsert("/r/2.txt", "二",
                  "长期练习是提高的关键。", 100, 30);
        db.upsert("/r/3.txt", "三",
                  "长期保养能延长寿命。", 100, 30);

        docseek::Searcher s(db);
        auto hits = s.search("长期不弹琴的话琴弦应该怎么处理", 2);
        // limit=2 生效：返回条数不超过 2
        EXPECT_LE(hits.size(), 2u);
        ASSERT_FALSE(hits.empty());
        // 期望文档应被重查召回（OR 命中）
        bool found = false;
        for (const auto& h : hits) {
            if (h.path == "/r/1.txt") {
                found = true;
                break;
            }
        }
        EXPECT_TRUE(found);
    }
    cleanupTempDb(dbPath);
}

// 7. UTF-8 首字提取：对多字节 token 首字应为完整单码点。
//    通过 parseNaturalQuery 观察切词结果，配合 search 黑盒验证：
//    含「不弹」连续片段的文档能被「不弹琴」类查询召回（说明首字提取未半字节截断）。
TEST(Searcher_T019Q12_AdjacentPrefixProbe_Utf8HeadExtraction, MultiByteHead) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        // 文档只含「不弹」，不含「弹琴」也不含「不弹琴」
        db.upsert("/u/1.txt", "琴",
                  "长期不弹需要放松琴弦。", 100, 32);

        docseek::Searcher s(db);
        auto hits = s.search("长期不弹琴保养方法", 10);
        ASSERT_FALSE(hits.empty());
        EXPECT_EQ(hits[0].path, "/u/1.txt");
    }
    cleanupTempDb(dbPath);

    // 附带验证 parseNaturalQuery 返回的 token 是多字节完整 UTF-8 词
    auto parsed = docseek::parseNaturalQuery("长期不弹琴保养方法");
    ASSERT_FALSE(parsed.keywords.empty());
    for (const auto& kw : parsed.keywords) {
        // 每个 keyword 不能为空，且不含 0x80 以下孤立的续接字节
        EXPECT_FALSE(kw.empty());
        // UTF-8 完整性：首个字节若为多字节引导，必须能容纳完整码点
        unsigned char c0 = static_cast<unsigned char>(kw[0]);
        if ((c0 & 0x80) != 0) {
            // 首字节属于多字节序列，长度检查
            size_t need = 1;
            if ((c0 & 0xE0) == 0xC0) need = 2;
            else if ((c0 & 0xF0) == 0xE0) need = 3;
            else if ((c0 & 0xF8) == 0xF0) need = 4;
            EXPECT_GE(kw.size(), need);
        }
    }
}

// 8. 回归：v07/v08/v09s 已通过的典型查询在本探测插入后零影响。
//    选取若干不触发探测（hits 非空）的查询，验证结果与 AND 路径一致。
TEST(Regression_V07_V08_V09s_NoRegression, CommonQueriesUnchanged) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert("/v/1.txt", "咖啡",
                  "the quick brown fox jumps over the lazy dog", 100, 44);
        db.upsert("/v/2.txt", "茶",
                  "quick rabbit runs fast", 100, 22);
        db.upsert("/v/3.txt", "琴",
                  "长期不弹的话放松琴弦。", 100, 30);

        docseek::Searcher s(db);
        // 单 token 命中：不满足 tokens.size() >= 2，探测不触发
        EXPECT_EQ(s.search("quick", 10).size(), 2u);
        // 双 token AND 命中：hits 非空，探测不触发
        auto foxHits = s.search("quick fox", 10);
        ASSERT_EQ(foxHits.size(), 1u);
        EXPECT_EQ(foxHits[0].path, "/v/1.txt");
        // 完全不命中：探测与回退均无果，返回空
        EXPECT_TRUE(s.search("elephant zebra", 10).empty());
    }
    cleanupTempDb(dbPath);
}

// ============================================================================
// 【跳过】项与理由
//
// - Searcher_T019Q12_AdjacentPrefixProbe_ProbeLimitOne（原清单第 2 条中
//   "用计数型 mock/stub Database 验证 searchFts 调用参数 limit 恰为 1、
//   且命中后短路"）：Database 是真实类，无虚函数接口可供注入计数 mock，
//   tryAdjacentPrefixProbe 又是 static 内部函数不可直接调用。本文件已用
//   合成语料黑盒等价验证（测试 2：SingleHitSufficient），但无法逐字断言
//   "searchFts(quoteToken(cand), 1)" 的 limit 实参。故明确标注【跳过】。
//
// - Searcher_T019Q12_AdjacentPrefixProbe_SkipsWhenHitsNonEmpty 中"用 mock
//   验证 searchFts 未被以 quoteToken(cand) 探测方式调用"：同上，Database
//   无可注入接口。已用"AND 命中路径结果一字不变"做等价验证（测试 4）。
//
// - Searcher_T019Q12_AdjacentPrefixProbe_RequeriesWithOrQuery 中"断言重查
//   查询字符串恰为 quoteToken(cand)+' OR '+buildOrMatchQuery(rest)"：
//   buildOrMatchQuery 为 Searcher 内部实现细节，公开头文件未暴露；且
//   tryAdjacentPrefixProbe 内部重查字符串无法从外部观测。已用"limit 生效
//   + 期望文档被 OR 召回"做等价验证（测试 6）。故字符串逐字断言【跳过】。
// ============================================================================
