#include <gtest/gtest.h>

#include <optional>

#include <cstdint>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/locator.h"
#include "docseek/passage_ranker.h"
#include "docseek/searcher.h"

namespace {

std::string BuildTenLineDoc() {
    std::string content;
    for (int i = 1; i <= 10; ++i) {
        if (i == 5) {
            content += "全文检索是信息检索的核心技术";
        } else {
            content += "这是第" + std::to_string(i) + "行填充内容";
        }
        if (i != 10) {
            content += "\n";
        }
    }
    return content;
}

class LocatePrecisionR2 : public ::testing::Test {
protected:
    void SetUp() override {
        db_.emplace(docseek::Database::open(":memory:"));
        content_ = BuildTenLineDoc();
        db_->upsert("/doc/a.txt", "标题", content_, 1,
                   (int64_t)content_.size());
        searcher_ = new docseek::Searcher(*db_);
        locator_ = new docseek::Locator(*db_, *searcher_);
    }

    void TearDown() override {
        delete locator_;
        delete searcher_;
    }

    std::optional<docseek::Database> db_;
    docseek::Searcher* searcher_ = nullptr;
    docseek::Locator* locator_ = nullptr;
    std::string content_;
};

TEST_F(LocatePrecisionR2, WindowCoversKeywordLine) {
    auto ps = locator_->locate("请找出讲全文检索的那段话");
    ASSERT_FALSE(ps.empty());
    EXPECT_LE(ps.front().line_start, 5);
    EXPECT_GE(ps.front().line_end, 5);
}

TEST_F(LocatePrecisionR2, TextContainsKeyword) {
    auto ps = locator_->locate("请找出讲全文检索的那段话");
    ASSERT_FALSE(ps.empty());
    EXPECT_NE(ps.front().text.find("全文检索"), std::string::npos);
}

TEST_F(LocatePrecisionR2, MatchedTermsNonEmpty) {
    auto ps = locator_->locate("请找出讲全文检索的那段话");
    ASSERT_FALSE(ps.empty());
    EXPECT_FALSE(ps.front().matched_terms.empty());
}

TEST_F(LocatePrecisionR2, ContextContainsKeywordAndHighlightsValid) {
    auto pcs = locator_->locateWithContext("请找出讲全文检索的那段话");
    ASSERT_FALSE(pcs.empty());
    const auto& pc = pcs.front();
    EXPECT_NE(pc.context.find("全文检索"), std::string::npos);
    EXPECT_FALSE(pc.highlights.empty());
    for (const auto& h : pc.highlights) {
        EXPECT_GE(h.first, 0);
        EXPECT_LT(h.first, h.second);
        EXPECT_LE(h.second, (int)pc.context.size());
    }
}

}  // namespace