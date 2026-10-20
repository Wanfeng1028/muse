#include <gtest/gtest.h>

#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/searcher.h"
#include "docseek/locator.h"
#include "docseek/passage_ranker.h"

namespace {

std::string makeDoc() {
    std::string content;
    for (int i = 1; i <= 30; ++i) {
        content += "第";
        content += std::to_string(i);
        content += "行内容";
        if (i == 5) {
            content += "这里放一个关键词自然语言定位";
        }
        if (i == 12) {
            content += "另一个关键词段落重排测试";
        }
        content += "\n";
    }
    return content;
}

docseek::Database makeDb() {
    docseek::Database db = docseek::Database::open(":memory:");
    std::string content = makeDoc();
    db.upsert("/doc/a.txt", "标题", content, 1,
              static_cast<int64_t>(content.size()));
    return db;
}

}  // namespace

TEST(LocateNonsenseR2, LocateNonsenseQueryReturnsEmpty) {
    docseek::Database db = makeDb();
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    std::vector<docseek::Passage> ps;
    EXPECT_NO_THROW(ps = locator.locate("xyzqwe123不存在的词"));
    EXPECT_TRUE(ps.empty());
}

TEST(LocateNonsenseR2, LocateWithContextNonsenseQueryReturnsEmpty) {
    docseek::Database db = makeDb();
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    std::vector<docseek::PassageContext> pcs;
    EXPECT_NO_THROW(pcs = locator.locateWithContext("xyzqwe123不存在的词"));
    EXPECT_TRUE(pcs.empty());
}

TEST(LocateNonsenseR2, LocateEmptyQueryReturnsEmpty) {
    docseek::Database db = makeDb();
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    std::vector<docseek::Passage> ps;
    EXPECT_NO_THROW(ps = locator.locate(""));
    EXPECT_TRUE(ps.empty());
}

TEST(LocateNonsenseR2, LocatePunctuationOnlyDoesNotCrash) {
    docseek::Database db = makeDb();
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    std::vector<docseek::Passage> ps;
    EXPECT_NO_THROW(ps = locator.locate("，。！？"));
    for (const auto& p : ps) {
        EXPECT_GE(p.line_start, 1);
        EXPECT_GE(p.line_end, p.line_start);
    }
}
