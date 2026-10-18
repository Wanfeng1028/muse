// tests/test_searcher.cpp
// Searcher 与 buildMatchQuery 的 GoogleTest 单元测试（中文注释）
#include <gtest/gtest.h>

#include <filesystem>
#include <set>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace {

// 生成一个临时数据库路径，避免污染真实数据
std::string makeTempDbPath() {
    auto dir = std::filesystem::temp_directory_path() /
               ("docseek_test_searcher_" + std::to_string(::getpid()));
    std::filesystem::create_directories(dir);
    return (dir / "test.db").string();
}

}  // namespace

// 测试 buildMatchQuery 的转义与分词行为
// 注意：多 token 之间用显式 AND 连接（FTS5 里括号 OR 组与引号串隐式相邻会报
// syntax error）；单个词若被 CutForSearch 切出重叠词则 OR 展开（如"咖啡豆"）。
TEST(BuildMatchQuery, BasicTokens) {
    EXPECT_EQ(docseek::Searcher::buildMatchQuery("hello world"), "\"hello\" AND \"world\"");
    EXPECT_EQ(docseek::Searcher::buildMatchQuery("say \"hi\""), "\"say\" AND \"\"\"\" AND \"hi\" AND \"\"\"\"");
    EXPECT_EQ(docseek::Searcher::buildMatchQuery(""), "");
    EXPECT_EQ(docseek::Searcher::buildMatchQuery("   "), "");
    // 中文重叠词展开为 OR（T1 查询侧）：咖啡豆 => <咖啡@0><咖啡豆@0>
    EXPECT_EQ(docseek::Searcher::buildMatchQuery("咖啡豆"), "(\"咖啡\" OR \"咖啡豆\")");
}

// 测试 search() 的隐式 AND 语义与命中数
TEST(SearchAndSemantics, ImplicitAnd) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert("/s/1.txt", "一", "the quick brown fox", 100, 20);
        db.upsert("/s/2.txt", "二", "quick rabbit", 100, 12);

        docseek::Searcher s(db);
        EXPECT_EQ(s.search("quick", 10).size(), 2u);

        auto foxHits = s.search("quick fox", 10);
        ASSERT_EQ(foxHits.size(), 1u);
        EXPECT_EQ(foxHits[0].path, "/s/1.txt");

        EXPECT_TRUE(s.search("elephant", 10).empty());
    }
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}

// 测试 limit 参数对结果数量的限制
TEST(SearchLimit, RespectsLimit) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert("/l/1.txt", "a", "commonword one", 100, 10);
        db.upsert("/l/2.txt", "b", "commonword two", 100, 10);
        db.upsert("/l/3.txt", "c", "commonword three", 100, 10);

        docseek::Searcher s(db);
        EXPECT_EQ(s.search("commonword", 2).size(), 2u);
    }
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}

// 测试空查询直接返回空结果
TEST(SearchEmptyQuery, EmptyAndWhitespace) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert("/e/1.txt", "x", "some content", 100, 12);

        docseek::Searcher s(db);
        EXPECT_TRUE(s.search("", 10).empty());
        EXPECT_TRUE(s.search("   ", 10).empty());
    }
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}

// T2 复现：切分上下文不一致导致的子串查询漏召回。
//
// 索引侧：FTS5 分词器对文档全文调用 CutForSearch，"猫砂盆" 被切成 <猫> <砂盆>，
// 因此索引里只存在 token "猫" 和 "砂盆"，不存在 "猫砂"。
// 查询侧：parseNaturalQuery 对查询串单独调用 CutForSearch，"猫砂" 被切成 <猫砂>，
// 于是查询关键词是 "猫砂"。MATCH '猫砂' 要求索引中存在 token "猫砂"，
// 但索引里只有 "猫"/"砂盆" —— 两边词汇表对不上，命中 0 条。
//
// 本测试当前必须失败（复现 T2）；T2 修复后应通过。
TEST(SearchT2, SubstringQueryRecall) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert(
            "/t2/cat.txt",
            "猫砂盆选购指南",
            "猫砂盆是养猫家庭的必需品，挑选猫砂盆要注意尺寸和材质。",
            100,
            42);

        docseek::Searcher s(db);

        // 对照组：完整词 "猫砂盆" 的索引 token 为 猫/砂盆，查询同样切成 猫/砂盆，
        // 两边一致，应当有结果，证明索引本身可用。
        EXPECT_FALSE(s.search("猫砂盆", 10).empty());

        // 复现断言：查询 "猫砂" 被切成 <猫砂>，索引中无此 token，
        // 子串查询漏召回。当前代码下此断言必须失败。
        EXPECT_FALSE(s.search("猫砂", 10).empty());
    }
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}

// T5：B3——searchQuestion 对 AND 与 OR 结果按 doc_id 取并集，
// 冲突时保留 AND 版本；空查询守卫。
TEST(SearchQuestion, SearchQuestionAndUnionOr) {
    std::string dbPath = makeTempDbPath();
    {
        docseek::Database db = docseek::Database::open(dbPath);
        db.upsert("/q/a.txt", "a", "alpha gadget", 0, 0);
        db.upsert("/q/b.txt", "b", "beta gadget", 0, 0);
        db.upsert("/q/c.txt", "c", "alpha beta gadget", 0, 0);

        docseek::Searcher s(db);

        // AND 语义不变：只有同时含 alpha 与 beta 的 c.txt 命中。
        std::vector<docseek::Hit> andHits = s.search("alpha beta", 10);
        ASSERT_EQ(andHits.size(), 1u);
        EXPECT_EQ(andHits[0].path, "/q/c.txt");

        // 问句：AND∪OR 并集，三篇都应召回。
        std::vector<docseek::Hit> qHits = s.searchQuestion("alpha beta", 10);
        ASSERT_EQ(qHits.size(), 3u);
        std::set<int64_t> ids;
        for (const auto& h : qHits) ids.insert(h.doc_id);
        EXPECT_EQ(ids.size(), 3u);

        // 冲突保留 AND 版本：c.txt 的 score 在两边应相等。
        bool foundAnd = false;
        bool foundQ = false;
        double andScore = 0.0;
        double qScore = 0.0;
        for (const auto& h : andHits) {
            if (h.path == "/q/c.txt") { foundAnd = true; andScore = h.score; }
        }
        for (const auto& h : qHits) {
            if (h.path == "/q/c.txt") { foundQ = true; qScore = h.score; }
        }
        ASSERT_TRUE(foundAnd);
        ASSERT_TRUE(foundQ);
        EXPECT_DOUBLE_EQ(qScore, andScore);

        // 空查询守卫。
        EXPECT_TRUE(s.searchQuestion("", 10).empty());
        EXPECT_TRUE(s.searchQuestion("   ", 10).empty());
    }
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}

// Fix A 回归（v0.15 修订）：双粒度展开因 v07-041 Top-1 回归已回退；
// expandTokenOrQuery 保持精确查询（单成员直接引号），分词不对齐由 Fix B 子串召回兜底。
TEST(SearcherV015, PreciseQueryNoDualExpansion) {
   // 多字 CJK 词不再双粒度展开，保持精确引号。
   EXPECT_EQ(docseek::Searcher::buildMatchQuery("咖啡"), "\"咖啡\"");
   // ASCII 词不受影响。
   EXPECT_EQ(docseek::Searcher::buildMatchQuery("hello"), "\"hello\"");
   // 单字 CJK 走前缀 `*`（D3，v0.16.1）——这是意图行为，不是 bug。
   EXPECT_EQ(docseek::Searcher::buildMatchQuery("猫"), "\"猫\"*");
   // 实测 CutForSearch("塌腰")=["塌","腰"]（不同起始位置）→ 两个单字各自走前缀 `*` 后顺序 AND（D3，v0.16.1）。
   EXPECT_EQ(docseek::Searcher::buildMatchQuery("塌腰"), "\"塌\"* AND \"腰\"*");
}

// Fix B 回归：substringRecallPass 按 CutForSearch 切词做逐词包含判定。
// 实测 CutForSearch("戚风塌腰")=["戚风塌","腰"]；旧代码无此函数，链接即失败，故先红。
namespace docseek {
bool substringRecallPass(const std::string&, const std::vector<std::string>&);
}

TEST(SearcherV015, SubstringRecallPassCutWords) {
    // hay 含 "戚风塌" 与 "腰" 但不含连续 "戚风塌腰"：旧整串包含逻辑判 false，新逻辑 true。
    EXPECT_TRUE(docseek::substringRecallPass("戚风塌了腰很酸", {"戚风塌腰"}));
    // 缺 "腰"，应判 false。
    EXPECT_FALSE(docseek::substringRecallPass("戚风塌了", {"戚风塌腰"}));
    // 空 tokens 视为通过。
    EXPECT_TRUE(docseek::substringRecallPass("任意内容", {}));
}
