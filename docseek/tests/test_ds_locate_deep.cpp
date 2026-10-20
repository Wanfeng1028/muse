#include "docseek/database.h"
#include "docseek/locator.h"
#include "docseek/passage_ranker.h"
#include "docseek/searcher.h"
#include <gtest/gtest.h>
#include <optional>
#include <cstdint>
#include <string>
#include <vector>

class LocateDeepDS : public ::testing::Test {
protected:
    void SetUp() override {
        db_.emplace(docseek::Database::open(":memory:"));
        std::string content;
        for (int i = 1; i <= 10; ++i) {
            content += (i == 5) ? "全文检索是信息检索的核心技术" : "这是第" + std::to_string(i) + "行填充内容";
            if (i != 10) content += "\n";
        }
        db_->upsert("/doc/a.txt", "标题", content, 1, (int64_t)content.size());
        searcher_ = new docseek::Searcher(*db_);
        locator_ = new docseek::Locator(*db_, *searcher_);
    }
    void TearDown() override { delete locator_; delete searcher_; }
    std::optional<docseek::Database> db_;
    docseek::Searcher* searcher_ = nullptr;
    docseek::Locator* locator_ = nullptr;
};

namespace {
size_t countCp(const std::string& s) {
    size_t n = 0;
    size_t i = 0;
    while (i < s.size()) {
        unsigned char c = static_cast<unsigned char>(s[i]);
        if (c < 0x80) {
            i += 1;
        } else if (c < 0xE0) {
            i += 2;
        } else if (c < 0xF0) {
            i += 3;
        } else {
            i += 4;
        }
        ++n;
    }
    return n;
}
}

TEST_F(LocateDeepDS, BasicLocate) {
    auto ps = locator_->locate("全文检索");
    EXPECT_FALSE(ps.empty());
    EXPECT_LE(ps[0].line_start, 5);
    EXPECT_GE(ps[0].line_end, 5);
    EXPECT_NE(ps[0].text.find("全文检索是信息检索的核心技术"), std::string::npos);
    EXPECT_FALSE(ps[0].matched_terms.empty());
}

TEST_F(LocateDeepDS, LineBase) {
    auto ps = locator_->locate("全文检索");
    for (const auto& p : ps) {
        EXPECT_GE(p.line_start, 1);
        EXPECT_GE(p.line_end, p.line_start);
        EXPECT_EQ(p.page_no, 0);
    }
}

TEST_F(LocateDeepDS, NoResult) {
    EXPECT_TRUE(locator_->locate("不存在的词qzxwvk").empty());
    EXPECT_TRUE(locator_->locate("").empty());
    EXPECT_TRUE(locator_->locate("   ").empty());
}

TEST_F(LocateDeepDS, LongDocPrecision) {
    auto db = docseek::Database::open(":memory:");
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);
    std::string content;
    for (int i = 1; i <= 200; ++i) {
        content += (i == 150) ? "量子纠缠" : "第" + std::to_string(i) + "行填充";
        if (i != 200) content += "\n";
    }
    db.upsert("/doc/long.txt", "标题", content, 1, (int64_t)content.size());
    auto ps = locator.locate("量子纠缠");
    EXPECT_FALSE(ps.empty());
    EXPECT_LE(ps[0].line_start, 150);
    EXPECT_GE(ps[0].line_end, 150);
}

TEST_F(LocateDeepDS, SortInvariant) {
    auto db = docseek::Database::open(":memory:");
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);
    std::string content;
    for (int i = 1; i <= 10; ++i) {
        content += (i == 2 || i == 8) ? "全文检索" : "第" + std::to_string(i) + "行填充";
        if (i != 10) content += "\n";
    }
    db.upsert("/doc/a.txt", "标题", content, 1, (int64_t)content.size());
    auto ps = locator.locate("全文检索");
    for (size_t i = 0; i + 1 < ps.size(); ++i) {
        EXPECT_TRUE(ps[i].score > ps[i + 1].score ||
                    (ps[i].score == ps[i + 1].score && ps[i].line_start <= ps[i + 1].line_start));
    }
}

TEST_F(LocateDeepDS, LimitTruncate) {
    docseek::LocateOptions o;
    o.limit = 2;
    auto ps = locator_->locate("全文检索", o);
    EXPECT_LE(ps.size(), 2u);
    auto full = locator_->locate("全文检索");
    for (size_t i = 0; i < ps.size(); ++i) {
        EXPECT_EQ(ps[i].line_start, full[i].line_start);
    }
}

TEST_F(LocateDeepDS, MultiDoc) {
    auto db = docseek::Database::open(":memory:");
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);
    db.upsert("/doc/a.txt", "标题", "全文检索", 1, 4);
    db.upsert("/doc/b.txt", "标题", "全文检索", 1, 4);
    auto ps = locator.locate("全文检索");
    std::vector<int64_t> ids;
    for (const auto& p : ps) {
        bool found = false;
        for (const auto& id : ids) {
            if (id == p.doc_id) {
                found = true;
                break;
            }
        }
        if (!found) ids.push_back(p.doc_id);
    }
    EXPECT_GE(ids.size(), 2u);
}

TEST_F(LocateDeepDS, WithContext) {
    auto cs = locator_->locateWithContext("全文检索");
    EXPECT_FALSE(cs.empty());
    EXPECT_FALSE(cs[0].context.empty());
    EXPECT_NE(cs[0].context.find("全文检索"), std::string::npos);
    EXPECT_FALSE(cs[0].highlights.empty());
    for (const auto& h : cs[0].highlights) {
        EXPECT_GE(h.first, 0);
        EXPECT_LT(h.first, h.second);
        EXPECT_LE(h.second, (int)cs[0].context.size());
    }
}

TEST_F(LocateDeepDS, ContextWindow) {
    auto cs = locator_->locateWithContext("全文检索");
    EXPECT_FALSE(cs.empty());
    EXPECT_LE(countCp(cs[0].context), 120u + countCp("全文检索") + 1u);
}

TEST_F(LocateDeepDS, QuestionPath) {
    EXPECT_FALSE(locator_->locate("全文检索在哪里？").empty());
}