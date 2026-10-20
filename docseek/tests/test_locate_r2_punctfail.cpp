#include <gtest/gtest.h>

#include "docseek/database.h"
#include "docseek/searcher.h"
#include "docseek/locator.h"

TEST(LocatePunctFailR2, StopwordOnlyQueryDoesNotThrow) {
    docseek::Database db = docseek::Database::open(":memory:");
    std::string content = "第一行\n第二行\n第三行\n第四行\n全文检索定位器";
    db.upsert("/doc/a.txt", "标题", content, 1, (int64_t)content.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);
    EXPECT_NO_THROW({
        auto ps = locator.locate("的了在了");
        (void)ps;
    });
}

TEST(LocatePunctFailR2, WhitespaceQueryReturnsEmpty) {
    docseek::Database db = docseek::Database::open(":memory:");
    std::string content = "第一行\n第二行\n第三行\n第四行\n全文检索定位器";
    db.upsert("/doc/a.txt", "标题", content, 1, (int64_t)content.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);
    auto ps = locator.locate("   ");
    EXPECT_TRUE(ps.empty());
}

TEST(LocatePunctFailR2, EmptyDatabaseReturnsEmpty) {
    docseek::Database db = docseek::Database::open(":memory:");
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);
    std::vector<docseek::Passage> ps;
    EXPECT_NO_THROW({
        ps = locator.locate("全文检索");
    });
    EXPECT_TRUE(ps.empty());
}