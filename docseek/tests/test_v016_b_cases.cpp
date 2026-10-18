// docseek v0.16.0 B 类攻坚回归测试（search 路径：Searcher::search()）
// 覆盖 B1（疑问词过滤 / stripFillerWords）与 B3（同义词表）两类修复。
// 风格沿用 tests/test_searcher.cpp：自包含 upsert 建库，不依赖外部 corpus/eval。
#include <gtest/gtest.h>

#include <filesystem>
#include <string>

#include <unistd.h>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace {

// 生成一个临时数据库路径，避免污染真实数据
std::string makeTempDbPath() {
    auto dir = std::filesystem::temp_directory_path() /
               ("docseek_test_v016_b_" + std::to_string(::getpid()));
    std::filesystem::create_directories(dir);
    return (dir / "test.db").string();
}

}  // namespace

// ============================================================================
// B3 同义词表回归：v09-t003-q08「通勤装备花费」
//
// 期望文档 A 正文含「装备花了多少钱」，但完全不含查询词「花费」。
// 干扰文档 B 正文含「花费」两次，但不含「通勤」「装备」。
//
// 红（当前代码）：查询为无空白单 token。AND 阶段：A 缺「花费」被滤掉，B 缺
//   「通勤」「装备」被滤掉 → 0 结果。单 token OR 回退经 substringRecallPass
//   精验，要求原文同时包含 CutForSearch 切出的每个词，A、B 仍被滤掉 → 空。
//   子串召回同样被 substringRecallPass 滤掉 → 空。故当前 hits.empty() 为真，
//   ASSERT_FALSE(hits.empty()) 失败（红）。
// 绿（B3 修复后）：「花费」→{"多少钱"} 同义词展开后，A 正文「装备花了多少钱」
//   命中「多少钱」侧信号，A 召回并排 Top-1；B 仍缺「通勤/装备」不排前。
// ============================================================================
TEST(BSynonym, T003Q08_通勤装备花费) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert("/b4/t003_a.html", "骑行通勤第一周",
                  "上个月我把地铁月票退了，改用一辆二手捷安特通勤。"
                  "装备花了多少钱：车 800 元，头盔 120 元，前后车灯 65 元，"
                  "加起来一千出头。",
                  100, 20);
        db.upsert("/b4/t003_b.html", "装修花费清单",
                  "客厅装修花费两万元，卧室花费一万五。", 100, 20);

        docseek::Searcher s(db);
        auto hits = s.search("通勤装备花费", 10);

        ASSERT_FALSE(hits.empty());
        EXPECT_EQ(hits[0].path, "/b4/t003_a.html");
    }
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}

// ============================================================================
// B3 同义词表回归：v09-t005-q06「裱花袋破裂」
//
// 期望文档 A 正文含「袋子裂了」「一次性裱花袋」，不含查询词「破裂」。
// 干扰文档 B 正文含「破裂」两次，但不含「裱花袋」。
//
// 红（当前代码）：AND 阶段 A 缺「破裂」被滤掉，B 缺「裱花袋」被滤掉 → 0 结果；
//   单 token OR 回退 / 子串召回均被 substringRecallPass 精验滤掉 → 空。
//   故 ASSERT_FALSE(hits.empty()) 失败（红）。
// 绿（B3 修复后）：「破裂」→{"裂"} 同义词展开后，A 正文「袋子裂了」命中「裂」
//   侧信号，A 召回并排 Top-1。
// ============================================================================
TEST(BSynonym, T005Q06_裱花袋破裂) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert("/b4/t005_a.md", "曲奇挤花袋总破",
                  "做曲奇最烦的就是挤到一半袋子裂了。用一次性裱花袋，"
                  "挤两三盘就破。",
                  100, 20);
        db.upsert("/b4/t005_b.md", "手机屏幕破裂维修",
                  "屏幕破裂后先贴膜应急，破裂严重就换屏。", 100, 20);

        docseek::Searcher s(db);
        auto hits = s.search("裱花袋破裂", 10);

        ASSERT_FALSE(hits.empty());
        EXPECT_EQ(hits[0].path, "/b4/t005_a.md");
    }
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}

// ============================================================================
// B3 同义词表回归：v09-t007-q06「小孩学游泳」
//
// 期望文档 A 标题含「孩子几岁学游泳合适」，正文含「孩子」，不含查询词「小孩」。
// 干扰文档 B 正文含「小孩」两次，但不含「学游泳」。
//
// 红（当前代码）：AND 阶段 A 缺「小孩」被滤掉，B 缺「学游泳」被滤掉 → 0 结果；
//   单 token OR 回退 / 子串召回均被 substringRecallPass 精验滤掉 → 空。
//   故 ASSERT_FALSE(hits.empty()) 失败（红）。
// 绿（B3 修复后）：「小孩」→{"孩子"} 同义词展开后，A 标题/正文「孩子」命中
//   侧信号，A 召回并排 Top-1。
// ============================================================================
TEST(BSynonym, T007Q06_小孩学游泳) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert("/b4/t007_a.md", "孩子几岁学游泳合适",
                  "我家孩子五岁半开始学游泳，关键看孩子能不能听懂指令。",
                  100, 20);
        db.upsert("/b4/t007_b.md", "小孩玩具选购",
                  "给小孩买玩具要看年龄段，小孩喜欢拼图。", 100, 20);

        docseek::Searcher s(db);
        auto hits = s.search("小孩学游泳", 10);

        ASSERT_FALSE(hits.empty());
        EXPECT_EQ(hits[0].path, "/b4/t007_a.md");
    }
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}

// ============================================================================
// 诚实边界（本轮不修）：v09-t022-q04「bounce和rock区别」
//
// 为什么 DISABLED：期望文档正文中「区别」出现 0 次，仅含「bounce」「rock」
//   等实体词。同义词展开（B3 机制）只能在查询词与文档词之间建立"等价信号"，
//   无法凭空创造判别信号——因为查询里的判别意图「区别」在期望文档里根本
//   没有对应措辞。正确机制是"问句模式改写"（识别「X 和 Y 区别」这类问句，
//   改写为对 X、Y 的共现/对比检索，而非要求字面命中"区别"），属查询改写层
//   的另一机制，本轮诚实边界不修。见 docs/SYNONYM_TABLE_DESIGN.md 第 6 节。
//
// 保留为 DISABLED 测试：一旦问句模式改写落地，移除 DISABLED_ 前缀即可启用。
// 当前代码下即使启用也应当为红（无改写机制时「区别」被 AND 进查询，
// 期望文档 0 次「区别」→ 空结果）。
// ============================================================================
TEST(DISABLED_BSynonym, T022Q04_区别措辞差异) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert("/b4/t022_a.html", "街舞基础步伐：bounce和rock怎么入门",
                  "bounce 是身体像弹簧一样上下起伏，rock 是身体前后摇摆。"
                  "它常和 bounce 结合使用。",
                  100, 20);

        docseek::Searcher s(db);
        auto hits = s.search("bounce和rock区别", 10);

        ASSERT_FALSE(hits.empty());
        EXPECT_EQ(hits[0].path, "/b4/t022_a.html");
    }
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}

