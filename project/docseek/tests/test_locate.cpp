#include <gtest/gtest.h>

#include <cstdio>
#include <set>
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

// 构造 6 行文档：第 3 行为 markdown 标题行，关键词"退款政策"只出现在标题行。
std::string makeHeadingOnlyContent() {
    return "前言第一行介绍背景\n"
           "前言第二行继续铺垫\n"
           "## 退款政策\n"
           "正文内容第一行说明条款\n"
           "正文内容第二行解释细则\n"
           "正文内容第三行补充备注\n";
}

// 在结果中查找 line_start==ls 的首个窗口（只按起点匹配：文档末尾的 '\n'
// 会产生一个空尾行，窗口的 line_end 会因此多出一行，按完整区间匹配是脆弱的）。
const Passage* findByLineStart(const std::vector<Passage>& vec, int ls) {
    for (const auto& p : vec) {
        if (p.line_start == ls) return &p;
    }
    return nullptr;
}

// T1：B2 bug 回归——标题行强制断窗后，下一窗口必须从标题行开始，
// 保证标题行始终被某个窗口覆盖。
TEST(PassageRankerV012, HeadingWindowRegression) {
    std::string content = makeHeadingOnlyContent();
    ParsedQuery pq;
    pq.keywords.push_back("退款政策");

    std::vector<Passage> res = rankPassages(1, "t.md", content, pq, 5);
    ASSERT_FALSE(res.empty());

    // 存在某窗口覆盖第 3 行标题行，且窗口文本含标题原文。
    bool covered = false;
    for (const auto& p : res) {
        if (p.line_start <= 3 && 3 <= p.line_end &&
            p.text.find("## 退款政策") != std::string::npos) {
            covered = true;
            break;
        }
    }
    EXPECT_TRUE(covered);

    // top-1 应覆盖第 3 行且文本含标题（该窗口 coverage=1.0 排第一）。
    ASSERT_FALSE(res.empty());
    EXPECT_LE(res[0].line_start, 3);
    EXPECT_GE(res[0].line_end, 3);
    EXPECT_NE(res[0].text.find("## 退款政策"), std::string::npos);
}

// T2：passageIntent 对标题打头窗口精确 +0.1，非标题窗口 +0.0。
TEST(PassageRankerV012, PassageIntentBonus) {
    std::string content = makeHeadingOnlyContent();

    ParsedQuery pq0;
    pq0.keywords.push_back("退款政策");
    pq0.passageIntent = false;
    std::vector<Passage> r0 = rankPassages(1, "t.md", content, pq0, 5);

    ParsedQuery pq1;
    pq1.keywords.push_back("退款政策");
    pq1.passageIntent = true;
    std::vector<Passage> r1 = rankPassages(1, "t.md", content, pq1, 5);

    ASSERT_FALSE(r0.empty());
    ASSERT_FALSE(r1.empty());
    EXPECT_EQ(r0.size(), r1.size());

    // 标题行打头的窗口（line_start==3）：passageIntent 应带来 +0.1。
    const Passage* a = findByLineStart(r0, 3);
    const Passage* b = findByLineStart(r1, 3);
    ASSERT_NE(a, nullptr);
    ASSERT_NE(b, nullptr);
    EXPECT_EQ(a->line_end, b->line_end);
    EXPECT_NEAR(b->score - a->score, 0.1, 1e-9);

    // 非标题窗口（line_start==1 的前言窗口）：passageIntent 不应改变分数。
    const Passage* c = findByLineStart(r0, 1);
    const Passage* d = findByLineStart(r1, 1);
    ASSERT_NE(c, nullptr);
    ASSERT_NE(d, nullptr);
    EXPECT_NEAR(d->score - c->score, 0.0, 1e-12);
}

// T3：问句走 searchQuestion 的 AND∪OR 并集召回。
TEST(LocatorV012, LocatorQuestionUsesUnionRecall) {
    std::string dbPath = makeTempDbPath("qunion");
    {
        Database db = Database::open(dbPath);
        db.upsert("退款流程.md", "退款流程",
                  "退款流程说明\n提交申请后等待审核。\n审核通过原路返回。\n",
                  0, 0);
        db.upsert("发货说明.md", "发货说明",
                  "发货须知\n四十八小时内发出。\n偏远地区延迟。\n",
                  0, 0);
        db.upsert("综合.md", "综合",
                  "退款流程发货总览\n退款流程与发货须知汇总。\n",
                  0, 0);

        Searcher searcher(db);
        Locator locator(db, searcher);

        LocateOptions opts;
        opts.limit = 9;
        opts.recallDocs = 10;
        std::vector<Passage> res =
            locator.locate("退款流程发货说明在哪里", opts);

        // 问句：AND 只命中"综合"，并集后三篇都应被召回。
        std::set<std::string> paths;
        for (const auto& p : res) paths.insert(p.path);
        EXPECT_NE(paths.find("退款流程.md"), paths.end());
        EXPECT_NE(paths.find("发货说明.md"), paths.end());
        EXPECT_NE(paths.find("综合.md"), paths.end());
    }
    cleanupTempDb(dbPath);
}

// T4：recallQuery 去重链路——phrases 与 keywords 共用去重集合。
TEST(LocatorV012, LocatorRecallQueryDedup) {
    std::string dbPath = makeTempDbPath("qdedup");
    {
        Database db = Database::open(dbPath);
        db.upsert("发货说明.md", "发货说明",
                  "发货须知\n四十八小时内发出。\n",
                  0, 0);

        Searcher searcher(db);
        Locator locator(db, searcher);

        // 解析：phrases=["发货"]、keywords=["发货"]，
        // recallQuery 去重后为单份"发货"（未去重会是 "发货 发货"）。
        // 注意：完全重复的 AND 在结果集层面等价，本用例守护的是去重后的
        // recallQuery 拼装链路（无 FTS5 语法错误、召回正确），
        // 并非声称能测出结果集差异。
        std::vector<Passage> res = locator.locate("\"发货\"发货在哪");
        EXPECT_FALSE(res.empty());
        ASSERT_FALSE(res.empty());
        EXPECT_NE(res[0].path.find("发货"), std::string::npos);
    }
    cleanupTempDb(dbPath);
}

// 先红后绿复现：跨文档段落排序只看段落分 Passage.score，丢弃了 Searcher
// 给出的文档级检索分 Hit.score，导致"关键词堆砌的短干扰段落"压过真正
// 的主题文档。
// 场景：问句"安装步骤在哪里"（关键词"安装""步骤"）。
//   - "安装指南.md" 是主题文档，标题"## 安装步骤"中"安装""步骤"按序连续出现，
//     命中复合短语加成（kCompoundPhraseBonus，窗口连续包含关键词拼接串 +0.25），
//     排序更靠前；
//   - "词语辨析.md" 是干扰文档，单段落把"安装""步骤"高频堆满，但两者未按序连续成串，
//     段落覆盖度+命中次数饱和，仍拿不到复合短语加成。
// 现状（未实现复合短语加成）下本测试会失败：res[0] 是"词语辨析.md"。
// 本用例是 v0.13 修复（复合短语加成，窗口连续包含关键词拼接串 +0.25）的验收测试，
// 修复后应转为绿。查询解析细节不做任何硬编码假设，只断言最终排序结果。
TEST(LocatorV013, CompoundPhraseBonusPrefersThematicDoc) {

    std::string dbPath = makeTempDbPath("docblend");
    {
        Database db = Database::open(dbPath);
        db.upsert("安装指南.md", "软件安装指南",
                  "# 软件安装指南\n\n## 安装步骤\n\n第一步：下载安装包。\n\n"
                  "第二步：运行程序完成安装。\n\n## 常见问题\n\n"
                  "安装失败时检查磁盘空间。\n",
                  0, 0);
        db.upsert("词语辨析.md", "词语辨析",
                  "动宾结构辨析：安装与卸载是反义。安装配置步骤是先下载再解压，"
                  "安装完成后再看步骤说明，安装过程分为几个步骤，"
                  "安装前请先阅读步骤。\n",
                  0, 0);

        Searcher searcher(db);
        Locator locator(db, searcher);

        std::vector<Passage> res = locator.locate("安装步骤在哪里");

        ASSERT_FALSE(res.empty());
        EXPECT_EQ(res[0].path, "安装指南.md");
    }
    cleanupTempDb(dbPath);
}

}  // namespace
}  // namespace docseek

