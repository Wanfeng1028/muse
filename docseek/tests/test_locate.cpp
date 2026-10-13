#include <gtest/gtest.h>

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/locator.h"
#include "docseek/passage_ranker.h"
#include "docseek/query_parser.h"
#include "docseek/searcher.h"

namespace docseek {
namespace {

namespace fs = std::filesystem;

// 创建临时目录并返回库路径。
std::string makeTempDbPath(const std::string& tag) {
    fs::path dir = fs::temp_directory_path() / ("docseek_test_locate_" + tag);
    std::error_code ec;
    fs::remove_all(dir, ec);
    fs::create_directories(dir, ec);
    return (dir / "test.db").string();
}

// 清理临时目录。
void cleanupTempDb(const std::string& dbPath) {
    std::error_code ec;
    fs::path dir = fs::path(dbPath).parent_path();
    fs::remove_all(dir, ec);
}

// 检查 vector 是否包含某元素。
bool contains(const std::vector<std::string>& v, const std::string& s) {
    for (const auto& x : v) {
        if (x == s) return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// QueryParser
// ---------------------------------------------------------------------------

TEST(QueryParser, InterrogativeStripping) {
    ParsedQuery pq =
        parseNaturalQuery("文档里写退款流程的部分在哪一段");
    EXPECT_TRUE(contains(pq.keywords, "退款"));
    EXPECT_TRUE(contains(pq.keywords, "流程"));
    EXPECT_FALSE(contains(pq.keywords, "哪里"));
    EXPECT_FALSE(contains(pq.keywords, "在"));
    EXPECT_FALSE(contains(pq.keywords, "的"));
    EXPECT_FALSE(contains(pq.keywords, "一段"));
    EXPECT_TRUE(pq.passageIntent);
}

TEST(QueryParser, QuotedPhrase) {
    ParsedQuery pq =
        parseNaturalQuery("苹果发布会 \"Vision Pro\" 价格是多少");
    EXPECT_TRUE(contains(pq.phrases, "Vision Pro"));
}

TEST(QueryParser, Fallback) {
    ParsedQuery pq = parseNaturalQuery("abc123");
    EXPECT_FALSE(pq.keywords.empty());
}

TEST(QueryParser, Empty) {
    ParsedQuery pq = parseNaturalQuery("   ");
    EXPECT_TRUE(pq.keywords.empty());
}

// ---------------------------------------------------------------------------
// PassageRanker
// ---------------------------------------------------------------------------

TEST(PassageRanker, Basic) {
    // 构造三段中文文本，目标段落在第 5–7 行含"退火温度"。
    std::string content =
        "第一段内容介绍背景信息\n"
        "第二段继续描述相关内容\n"
        "第三段说明工艺流程\n"
        "第四段过渡到核心参数\n"
        "第五段讨论退火温度的设定\n"
        "第六段给出退火温度的具体数值\n"
        "第七段总结退火温度的影响\n"
        "第八段补充其他注意事项\n";

    ParsedQuery pq;
    pq.keywords.push_back("退火温度");

    std::vector<Passage> res =
        rankPassages(1, "test.md", content, pq, 3);
    ASSERT_FALSE(res.empty());
    const Passage& top = res[0];
    EXPECT_LE(top.line_start, 5);
    EXPECT_GE(top.line_end, 7);
    EXPECT_FALSE(top.matched_terms.empty());
    EXPECT_NE(top.text.find("退火温度"), std::string::npos);
}

TEST(PassageRanker, Empty) {
    ParsedQuery pq;
    pq.keywords.push_back("测试");
    std::vector<Passage> res = rankPassages(1, "empty.md", "", pq, 3);
    EXPECT_TRUE(res.empty());
}

// ---------------------------------------------------------------------------
// Locator
// ---------------------------------------------------------------------------

TEST(Locator, Integration) {
    std::string dbPath = makeTempDbPath("integration");

    {
        Database db = Database::open(dbPath);
        db.upsert("退款政策.md", "退款政策",
                  "退款政策说明\n"
                  "本文档介绍退款相关规则。\n"
                  "七天无理由退款是本平台的核心政策。\n"
                  "退款流程需要用户提交申请。\n"
                  "审核通过后退款将原路返回。\n",
                  1000, 200);
        db.upsert("发货说明.md", "发货说明",
                  "发货说明\n"
                  "订单确认后 48 小时内发货。\n"
                  "偏远地区可能延迟。\n",
                  1001, 150);
        db.upsert("会员权益.md", "会员权益",
                  "会员权益\n"
                  "会员可享受专属折扣。\n"
                  "积分可兑换礼品。\n",
                  1002, 120);

        Searcher searcher(db);
        Locator locator(db, searcher);
        std::vector<Passage> res =
            locator.locate("退款流程具体是怎么规定的");

        ASSERT_FALSE(res.empty());
        EXPECT_NE(res[0].path.find("退款"), std::string::npos);

        // 检查 [line_start, line_end] 覆盖"七天无理由退款"所在行（第 3 行）。
        const int targetLine = 3;
        EXPECT_LE(res[0].line_start, targetLine);
        EXPECT_GE(res[0].line_end, targetLine);
    }

    cleanupTempDb(dbPath);
}

TEST(Locator, NoResult) {
    std::string dbPath = makeTempDbPath("noresult");

    {
        Database db = Database::open(dbPath);
        db.upsert("退款政策.md", "退款政策",
                  "退款政策说明\n七天无理由退款。\n",
                  1000, 200);

        Searcher searcher(db);
        Locator locator(db, searcher);
        std::vector<Passage> res = locator.locate("xyzabc不存在的词");
        EXPECT_TRUE(res.empty());
    }

    cleanupTempDb(dbPath);
}

}  // namespace
}  // namespace docseek
