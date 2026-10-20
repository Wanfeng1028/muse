#include <gtest/gtest.h>

#include <algorithm>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/locator.h"
#include "docseek/passage_ranker.h"
#include "docseek/searcher.h"

namespace {

std::string buildContent(const std::string& keyword, int lineNo) {
    std::string content;
    for (int i = 1; i <= 10; ++i) {
        if (i == lineNo) {
            content += keyword;
        } else {
            content += "普通文本行" + std::to_string(i);
        }
        if (i != 10) {
            content += "\n";
        }
    }
    return content;
}

bool containsPath(const std::vector<docseek::Passage>& passages,
                  const std::string& path) {
    return std::any_of(passages.begin(), passages.end(),
                       [&path](const docseek::Passage& p) {
                           return p.path == path;
                       });
}

}  // namespace

TEST(LocateMultiDocR2, LocateReturnsDocAAndDocB) {
    docseek::Database db = docseek::Database::open(":memory:");
    const std::string contentA = buildContent("全文检索技术详解", 5);
    const std::string contentB = buildContent("全文检索应用案例", 5);
    const std::string contentC = buildContent("无关内容示例", 5);
    db.upsert("/doc/a.txt", "标题A", contentA, 1, (int64_t)contentA.size());
    db.upsert("/doc/b.txt", "标题B", contentB, 1, (int64_t)contentB.size());
    db.upsert("/doc/c.txt", "标题C", contentC, 1, (int64_t)contentC.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto ps = locator.locate("全文检索");

    EXPECT_TRUE(containsPath(ps, "/doc/a.txt"));
    EXPECT_TRUE(containsPath(ps, "/doc/b.txt"));
}

TEST(LocateMultiDocR2, DocCNotInResults) {
    docseek::Database db = docseek::Database::open(":memory:");
    const std::string contentA = buildContent("全文检索技术详解", 5);
    const std::string contentB = buildContent("全文检索应用案例", 5);
    const std::string contentC = buildContent("无关内容示例", 5);
    db.upsert("/doc/a.txt", "标题A", contentA, 1, (int64_t)contentA.size());
    db.upsert("/doc/b.txt", "标题B", contentB, 1, (int64_t)contentB.size());
    db.upsert("/doc/c.txt", "标题C", contentC, 1, (int64_t)contentC.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto ps = locator.locate("全文检索");

    EXPECT_FALSE(containsPath(ps, "/doc/c.txt"));
}

TEST(LocateMultiDocR2, PassagePathAndDocIdValid) {
    docseek::Database db = docseek::Database::open(":memory:");
    const std::string contentA = buildContent("全文检索技术详解", 5);
    const std::string contentB = buildContent("全文检索应用案例", 5);
    db.upsert("/doc/a.txt", "标题A", contentA, 1, (int64_t)contentA.size());
    db.upsert("/doc/b.txt", "标题B", contentB, 1, (int64_t)contentB.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto ps = locator.locate("全文检索");

    EXPECT_FALSE(ps.empty());
    for (const auto& p : ps) {
        EXPECT_FALSE(p.path.empty());
        EXPECT_GT(p.doc_id, 0);
    }
}