#include <gtest/gtest.h>

#include <algorithm>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/locator.h"
#include "docseek/passage_ranker.h"
#include "docseek/searcher.h"

namespace {

std::string MakeContent() {
    return "第一行：苹果手机评测。\n第二行：香蕉营养价值。\n第三行：苹果手机电池测试。";
}

}  // namespace

TEST(LocateMatchedR2, MatchedTermsAppearInText) {
    docseek::Database db = docseek::Database::open(":memory:");
    std::string content = MakeContent();
    db.upsert("/doc/a.txt", "标题", content, 1, (int64_t)content.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto ps = locator.locate("苹果手机");
    ASSERT_FALSE(ps.empty());
    for (const auto& p : ps) {
        for (const auto& term : p.matched_terms) {
            EXPECT_NE(p.text.find(term), std::string::npos)
                << "term not found in text: " << term;
        }
    }
}

TEST(LocateMatchedR2, MatchedTermsAreUnique) {
    docseek::Database db = docseek::Database::open(":memory:");
    std::string content = MakeContent();
    db.upsert("/doc/a.txt", "标题", content, 1, (int64_t)content.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto ps = locator.locate("苹果手机");
    ASSERT_FALSE(ps.empty());
    for (const auto& p : ps) {
        std::vector<std::string> sorted = p.matched_terms;
        std::sort(sorted.begin(), sorted.end());
        auto it = std::adjacent_find(sorted.begin(), sorted.end());
        EXPECT_EQ(it, sorted.end()) << "duplicate matched term: "
                                    << (it != sorted.end() ? *it : std::string());
    }
}

TEST(LocateMatchedR2, PassagesSortedByScoreDescending) {
    docseek::Database db = docseek::Database::open(":memory:");
    std::string content = MakeContent();
    db.upsert("/doc/a.txt", "标题", content, 1, (int64_t)content.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto ps = locator.locate("苹果手机");
    ASSERT_FALSE(ps.empty());
    for (size_t i = 1; i < ps.size(); ++i) {
        EXPECT_LE(ps[i].score, ps[i - 1].score);
    }
}
