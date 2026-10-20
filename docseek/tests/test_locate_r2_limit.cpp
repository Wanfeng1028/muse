#include <gtest/gtest.h>

#include <string>

#include "docseek/database.h"
#include "docseek/searcher.h"
#include "docseek/locator.h"

namespace {

std::string MakeContent(int lines) {
    std::string content;
    for (int i = 1; i <= lines; ++i) {
        content += "第" + std::to_string(i) + "行：全文检索技术介绍\n";
    }
    return content;
}

}  // namespace

TEST(LocateLimitR2, DefaultLimitAtMostFive) {
    docseek::Database db = docseek::Database::open(":memory:");
    std::string content = MakeContent(20);
    db.upsert("/doc/a.txt", "标题", content, 1, (int64_t)content.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto ps = locator.locate("全文检索");
    EXPECT_LE(ps.size(), 5u);
}

TEST(LocateLimitR2, LimitTwoAtMostTwo) {
    docseek::Database db = docseek::Database::open(":memory:");
    std::string content = MakeContent(20);
    db.upsert("/doc/a.txt", "标题", content, 1, (int64_t)content.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    docseek::LocateOptions opts;
    opts.limit = 2;
    auto ps = locator.locate("全文检索", opts);
    EXPECT_LE(ps.size(), 2u);
}

TEST(LocateLimitR2, LimitOneExactlyOne) {
    docseek::Database db = docseek::Database::open(":memory:");
    std::string content = MakeContent(20);
    db.upsert("/doc/a.txt", "标题", content, 1, (int64_t)content.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    docseek::LocateOptions opts;
    opts.limit = 1;
    auto ps = locator.locate("全文检索", opts);
    EXPECT_EQ(ps.size(), 1u);
}

TEST(LocateLimitR2, WithContextLimitThreeAtMostThree) {
    docseek::Database db = docseek::Database::open(":memory:");
    std::string content = MakeContent(20);
    db.upsert("/doc/a.txt", "标题", content, 1, (int64_t)content.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    docseek::LocateOptions opts;
    opts.limit = 3;
    auto pcs = locator.locateWithContext("全文检索", opts);
    EXPECT_LE(pcs.size(), 3u);
}