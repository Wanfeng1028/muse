#include <gtest/gtest.h>

#include <cstdint>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/locator.h"
#include "docseek/passage_ranker.h"
#include "docseek/searcher.h"

namespace {

bool IsValidUtf8(const std::string& s) {
    size_t i = 0;
    const size_t n = s.size();
    while (i < n) {
        unsigned char c = static_cast<unsigned char>(s[i]);
        size_t extra = 0;
        if (c <= 0x7F) {
            extra = 0;
        } else if ((c & 0xE0) == 0xC0) {
            extra = 1;
        } else if ((c & 0xF0) == 0xE0) {
            extra = 2;
        } else if ((c & 0xF8) == 0xF0) {
            extra = 3;
        } else {
            return false;
        }
        if (i + extra >= n) {
            return false;
        }
        for (size_t k = 1; k <= extra; ++k) {
            unsigned char cc = static_cast<unsigned char>(s[i + k]);
            if ((cc & 0xC0) != 0x80) {
                return false;
            }
        }
        i += extra + 1;
    }
    return true;
}

const char* kContent =
    "苹果手机评测：苹果手机的摄像头很好，苹果手机的电池也不错。";

docseek::Database MakeDb() {
    docseek::Database db = docseek::Database::open(":memory:");
    std::string content(kContent);
    db.upsert("/doc/a.txt", "标题", content, 1, (int64_t)content.size());
    return db;
}

}  // namespace

TEST(LocateContextR2, NonEmptyAndHighlightsSorted) {
    docseek::Database db = MakeDb();
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto pcs = locator.locateWithContext("苹果手机");
    ASSERT_FALSE(pcs.empty());

    for (const auto& pc : pcs) {
        for (size_t i = 1; i < pc.highlights.size(); ++i) {
            EXPECT_GE(pc.highlights[i].first, pc.highlights[i - 1].first);
        }
    }
}

TEST(LocateContextR2, HighlightSlicesNonEmpty) {
    docseek::Database db = MakeDb();
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto pcs = locator.locateWithContext("苹果手机");
    ASSERT_FALSE(pcs.empty());

    for (const auto& pc : pcs) {
        for (const auto& h : pc.highlights) {
            int s = h.first;
            int e = h.second;
            EXPECT_GE(s, 0);
            EXPECT_GE(e, s);
            ASSERT_LE(static_cast<size_t>(e), pc.context.size());
            std::string slice = pc.context.substr(s, e - s);
            EXPECT_FALSE(slice.empty());
        }
    }
}

TEST(LocateContextR2, HighlightsNonOverlapping) {
    docseek::Database db = MakeDb();
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto pcs = locator.locateWithContext("苹果手机");
    ASSERT_FALSE(pcs.empty());

    for (const auto& pc : pcs) {
        for (size_t i = 1; i < pc.highlights.size(); ++i) {
            EXPECT_GE(pc.highlights[i].first, pc.highlights[i - 1].second);
        }
    }
}

TEST(LocateContextR2, ContextIsValidUtf8) {
    docseek::Database db = MakeDb();
    docseek::Searcher searcher(db);
    docseek::Locator locator(db, searcher);

    auto pcs = locator.locateWithContext("苹果手机");
    ASSERT_FALSE(pcs.empty());

    for (const auto& pc : pcs) {
        EXPECT_TRUE(IsValidUtf8(pc.context));
    }
}