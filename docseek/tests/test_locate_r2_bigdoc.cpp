#include <gtest/gtest.h>

#include <chrono>
#include <string>

#include "docseek/database.h"
#include "docseek/locator.h"
#include "docseek/passage_ranker.h"
#include "docseek/searcher.h"

namespace {

std::string makeFillerDoc(size_t targetBytes) {
    std::string line = std::string(100, 'a') + "\n";
    std::string content;
    while (content.size() < targetBytes) {
        content += line;
    }
    return content;
}

std::string makeBigDocWithKeyword(size_t fillerBytes, size_t& keywordLineOut) {
    std::string content = makeFillerDoc(fillerBytes);
    size_t lineCount = 0;
    for (char c : content) {
        if (c == '\n') ++lineCount;
    }
    content += "全文检索核心技术\n";
    keywordLineOut = lineCount + 1;
    return content;
}

}  // namespace

TEST(LocateBigDocR2, LocateWithContextBigDocScansFirst2MBOnly) {
    docseek::Database db = docseek::Database::open(":memory:");
    size_t keywordLine = 0;
    std::string content = makeBigDocWithKeyword(3 * 1024 * 1024, keywordLine);
    db.upsert("/doc/big.txt", "标题", content, 1, (int64_t)content.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto pcs = locator.locateWithContext("全文检索核心技术");
    for (const auto& pc : pcs) {
        EXPECT_GE(pc.passage.line_start, 1);
        EXPECT_LE(pc.passage.line_start, 21000);
    }
}

TEST(LocateBigDocR2, LocateWithContextSmallDocFindsKeyword) {
    docseek::Database db = docseek::Database::open(":memory:");
    std::string content = makeFillerDoc(1024 * 1024);
    content += "全文检索核心技术\n";
    db.upsert("/doc/small.txt", "标题", content, 1, (int64_t)content.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto pcs = locator.locateWithContext("全文检索核心技术");
    EXPECT_FALSE(pcs.empty());
    for (const auto& pc : pcs) {
        EXPECT_GE(pc.passage.line_start, 1);
        EXPECT_GE(pc.passage.line_end, pc.passage.line_start);
    }
}

TEST(LocateBigDocR2, LocateBigDocReturnsWithin5Seconds) {
    docseek::Database db = docseek::Database::open(":memory:");
    size_t keywordLine = 0;
    std::string content = makeBigDocWithKeyword(3 * 1024 * 1024, keywordLine);
    db.upsert("/doc/big2.txt", "标题", content, 1, (int64_t)content.size());
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto start = std::chrono::steady_clock::now();
    auto ps = locator.locate("全文检索核心技术");
    auto end = std::chrono::steady_clock::now();
    auto elapsedMs = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();
    EXPECT_LT(elapsedMs, 5000);
    for (const auto& p : ps) {
        EXPECT_GE(p.line_start, 1);
        EXPECT_GE(p.line_end, p.line_start);
    }
}