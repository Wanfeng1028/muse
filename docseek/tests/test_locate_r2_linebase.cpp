#include <gtest/gtest.h>

#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/searcher.h"
#include "docseek/locator.h"

namespace {

std::string BuildFirstLineDoc() {
    std::string content;
    content += "全文检索开篇语";
    content += "\n";
    for (int i = 0; i < 9; ++i) {
        content += "填充行";
        content += std::to_string(i);
        if (i != 8) {
            content += "\n";
        }
    }
    return content;
}

std::string MakeDoc() {
    return BuildFirstLineDoc();
}

}  // namespace

TEST(LocateLineBaseR2, FirstPassageStartsAtLineOne) {
    docseek::Database db = docseek::Database::open(":memory:");
    std::string content = MakeDoc();
    db.upsert("/doc/a.txt", "标题", content, 1, (int64_t)content.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto ps = locator.locate("全文检索");
    ASSERT_FALSE(ps.empty());
    EXPECT_EQ(ps.front().line_start, 1);
}

TEST(LocateLineBaseR2, LineRangeIsValid) {
    docseek::Database db = docseek::Database::open(":memory:");
    std::string content = MakeDoc();
    db.upsert("/doc/a.txt", "标题", content, 1, (int64_t)content.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto ps = locator.locate("全文检索");
    ASSERT_FALSE(ps.empty());
    for (const auto& p : ps) {
        EXPECT_GE(p.line_start, 1);
        EXPECT_GE(p.line_end, p.line_start);
    }
}

TEST(LocateLineBaseR2, TextLineCountMatchesRange) {
    docseek::Database db = docseek::Database::open(":memory:");
    std::string content = MakeDoc();
    db.upsert("/doc/a.txt", "标题", content, 1, (int64_t)content.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto ps = locator.locate("全文检索");
    ASSERT_FALSE(ps.empty());
    for (const auto& p : ps) {
        int count = 1;
        for (char c : p.text) {
            if (c == '\n') {
                ++count;
            }
        }
        EXPECT_EQ(count, p.line_end - p.line_start + 1);
    }
}