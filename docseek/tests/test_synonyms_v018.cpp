// tests/test_synonyms_v018.cpp
// 同义词表新增边「人群」→「人挤人」的 GoogleTest 单元测试（中文注释）
//
// 覆盖 F-T009B：
//   1. 公开 API findSynonyms("人群") 返回非空，且 expansions 含「人挤人」；
//   2. findSynonyms("不存在的词") 返回 nullptr；
//   3. 通过公开 API Searcher::search() 黑盒验证：查询含「人群」能召回
//      正文/标题含「人挤人」的文档（query 侧同义词扩展生效）；
//   4. 反向不污染：不含「人群」的查询不应因该边而召回「人挤人」文档。
//
// 注意：rerankHits 是 searcher.cpp 内部 static 函数，不直接调用；
//       同义词的召回行为一律走 search() 黑盒验证。
#include <gtest/gtest.h>

#include <filesystem>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/query_parser.h"
#include "docseek/searcher.h"
#include "docseek/synonyms.h"

namespace {

// 生成一个临时数据库路径，避免污染真实数据（沿用 test_searcher.cpp 夹具模式）
std::string makeTempDbPath() {
    auto dir = std::filesystem::temp_directory_path() /
               ("docseek_test_synonyms_v018_" + std::to_string(::getpid()));
    std::filesystem::create_directories(dir);
    return (dir / "test.db").string();
}

// 在 expansions 列表中查找是否包含指定词（expansions 为 const char* 数组）
bool containsExpansion(const docseek::SynonymEntry* r, const std::string& want) {
    if (r == nullptr) {
        return false;
    }
    for (std::size_t i = 0; i < r->expansionCount; ++i) {
        if (r->expansions[i] != nullptr && want == r->expansions[i]) {
            return true;
        }
    }
    return false;
}

}  // namespace

// ---------------------------------------------------------------------------
// 1. 直接调用公开 API findSynonyms：新增边「人群」→「人挤人」
// ---------------------------------------------------------------------------
TEST(SynonymsRenQun, FindsRenQunEdge) {
    const docseek::SynonymEntry* r = docseek::findSynonyms("人群");

    // 边必须存在（非空）
    ASSERT_NE(r, nullptr) << "同义词表应新增「人群」边";

    // expansions 非空且包含「人挤人」
    EXPECT_GT(r->expansionCount, 0u);
    EXPECT_TRUE(containsExpansion(r, "人挤人"))
        << "「人群」的 expansions 必须含「人挤人」";

    // 反向不应把自身塞进 expansions（避免自扩展噪声）
    EXPECT_FALSE(containsExpansion(r, "人群"));
}

// ---------------------------------------------------------------------------
// 2. 未登记词返回 nullptr
// ---------------------------------------------------------------------------
TEST(SynonymsMissing, ReturnsNullptrForUnknownTerm) {
    EXPECT_EQ(docseek::findSynonyms("不存在的词"), nullptr);
    // 空串与纯空白同样不应命中任何边
    EXPECT_EQ(docseek::findSynonyms(""), nullptr);
}

// ---------------------------------------------------------------------------
// 3. 黑盒：search() 用「人群」查询，应召回正文含「人挤人」的文档
//    （query 侧同义词扩展：token 恰为「人群」时展开为「人挤人」）
// ---------------------------------------------------------------------------
TEST(SearchSynonymsRenQun, RecallsDocWithRenJiRen) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        // 期望文档：标题含「人挤人」，全文无「人群」
        db.upsert("/syn/renji.txt", "地铁人挤人", "早高峰的地铁里全是人挤人，动弹不得", 100, 30);
        // 干扰文档：既不匹配「人群」也不匹配「人挤人」
        db.upsert("/syn/other.txt", "安静的书房", "午后阳光落在书页上，非常安静", 100, 30);

        docseek::Searcher s(db);

        // 查询侧「人群」应被扩展，从而命中含「人挤人」的文档
        auto hits = s.search("人群", 10);
        ASSERT_FALSE(hits.empty()) << "「人群」查询应通过同义词扩展召回「人挤人」文档";

        bool found = false;
        for (const auto& h : hits) {
            if (h.path == "/syn/renji.txt") {
                found = true;
                break;
            }
        }
        EXPECT_TRUE(found) << "命中集合应包含标题/正文含「人挤人」的文档";

        // 干扰文档不应被召回
        for (const auto& h : hits) {
            EXPECT_NE(h.path, "/syn/other.txt");
        }
    }
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}

// ---------------------------------------------------------------------------
// 4. 不污染：不含「人群」的查询不应因该边召回「人挤人」文档
//    （findSynonyms 是 std::strcmp 整串精确匹配，非子串）
// ---------------------------------------------------------------------------
TEST(SearchSynonymsRenQun, DoesNotPolluteOtherQueries) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert("/syn/renji.txt", "地铁人挤人", "早高峰的地铁里全是人挤人，动弹不得", 100, 30);
        db.upsert("/syn/quiet.txt", "安静的书房", "午后阳光落在书页上，非常安静", 100, 30);

        docseek::Searcher s(db);

        // 「安静」与「人群」无关，不应召回「人挤人」文档
        auto hits = s.search("安静", 10);
        ASSERT_EQ(hits.size(), 1u);
        EXPECT_EQ(hits[0].path, "/syn/quiet.txt");

        // 「人群」作为更长查询的一部分时，token 不等于「人群」整串，
        // 该边不应被触发（例如「人群拥挤」不应等同于「人群」）
        auto partial = s.search("人群拥挤", 10);
        for (const auto& h : partial) {
            EXPECT_NE(h.path, "/syn/renji.txt")
                << "非整串「人群」的 token 不应触发该同义词边";
        }
    }
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}

// ---------------------------------------------------------------------------
// 5. 公开 API parseNaturalQuery 可直接调用：断言「人群」被识别为关键词
//    （用于确认查询侧分词把「人群」切为独立 token，从而命中整串匹配）
// ---------------------------------------------------------------------------
TEST(ParseNaturalQueryRenQun, KeepsRenQunAsKeyword) {
    auto parsed = docseek::parseNaturalQuery("人群");

    // 关键词列表应非空
    ASSERT_FALSE(parsed.keywords.empty());

    // 关键词中应出现「人群」
    bool hasRenQun = false;
    for (const auto& kw : parsed.keywords) {
        if (kw == "人群") {
            hasRenQun = true;
            break;
        }
    }
    EXPECT_TRUE(hasRenQun) << "「人群」应作为独立关键词出现在 parseNaturalQuery 结果中";
}
