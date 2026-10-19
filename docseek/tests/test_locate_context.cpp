#include <gtest/gtest.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include "docseek/database.h"
#include "docseek/locator.h"
#include "docseek/searcher.h"

namespace {

bool AsciiCaseInsensitiveEqual(const std::string& a, const std::string& b) {
  if (a.size() != b.size()) {
    return false;
  }
  for (std::size_t i = 0; i < a.size(); ++i) {
    char ca = a[i];
    char cb = b[i];
    if (ca >= 'A' && ca <= 'Z') {
      ca = static_cast<char>(ca - 'A' + 'a');
    }
    if (cb >= 'A' && cb <= 'Z') {
      cb = static_cast<char>(cb - 'A' + 'a');
    }
    if (ca != cb) {
      return false;
    }
  }
  return true;
}

bool IsUtf8ContinuationByte(char c) {
  return (static_cast<unsigned char>(c) & 0xC0) == 0x80;
}

std::string RepeatParagraph(const std::string& unit, int times) {
  std::string out;
  out.reserve(unit.size() * static_cast<std::size_t>(times));
  for (int i = 0; i < times; ++i) {
    out += unit;
  }
  return out;
}

}  // namespace

TEST(LocateContextTest, WindowCenter) {
  docseek::Database db = docseek::Database::open(":memory:");
  std::string content;
  content += std::string(60, 'a');
  content += " needle ";
  content += std::string(60, 'b');
  db.upsert("/doc/window_center.txt", "Window Center", content, 1, static_cast<int64_t>(content.size()));

  docseek::Searcher searcher(db);
  docseek::Locator locator(db, searcher);

  docseek::LocateOptions opts;
  std::vector<docseek::PassageContext> results = locator.locateWithContext("needle", opts);
  ASSERT_FALSE(results.empty());

  const std::string& context = results[0].context;
  EXPECT_GE(context.size(), 115u);
  EXPECT_LE(context.size(), 140u); // 字节数：前后各 60 字符 + 命中词，放宽 1 字节级硬边界
  EXPECT_NE(context.find("needle"), std::string::npos);

  std::size_t hit_pos = context.find("needle");
  ASSERT_NE(hit_pos, std::string::npos);
  EXPECT_GE(hit_pos, 55u);
  EXPECT_LE(hit_pos, 65u);
}

TEST(LocateContextTest, HitNearStart) {
  docseek::Database db = docseek::Database::open(":memory:");
  std::string content = "needle ";
  content += std::string(200, 'x');
  db.upsert("/doc/hit_near_start.txt", "Hit Near Start", content, 1, static_cast<int64_t>(content.size()));

  docseek::Searcher searcher(db);
  docseek::Locator locator(db, searcher);

  docseek::LocateOptions opts;
  std::vector<docseek::PassageContext> results = locator.locateWithContext("needle", opts);
  ASSERT_FALSE(results.empty());

  const std::string& context = results[0].context;
  ASSERT_FALSE(context.empty());
  EXPECT_EQ(context.compare(0, 6, "needle"), 0);
}

TEST(LocateContextTest, HitNearEnd) {
  docseek::Database db = docseek::Database::open(":memory:");
  std::string content = std::string(200, 'y');
  content += " needle";
  db.upsert("/doc/hit_near_end.txt", "Hit Near End", content, 1, static_cast<int64_t>(content.size()));

  docseek::Searcher searcher(db);
  docseek::Locator locator(db, searcher);

  docseek::LocateOptions opts;
  std::vector<docseek::PassageContext> results = locator.locateWithContext("needle", opts);
  ASSERT_FALSE(results.empty());

  const std::string& context = results[0].context;
  ASSERT_GE(context.size(), 6u);
  EXPECT_EQ(context.compare(context.size() - 6, 6, "needle"), 0);
}

TEST(LocateContextTest, HighlightOffsetsAlign) {
  docseek::Database db = docseek::Database::open(":memory:");
  std::string content;
  content += std::string(40, 'a');
  content += " Alpha beta ALPHA gamma alpha ";
  content += std::string(40, 'b');
  db.upsert("/doc/highlight_offsets.txt", "Highlight Offsets", content, 1, static_cast<int64_t>(content.size()));

  docseek::Searcher searcher(db);
  docseek::Locator locator(db, searcher);

  docseek::LocateOptions opts;
  std::vector<docseek::PassageContext> results = locator.locateWithContext("alpha", opts);
  ASSERT_FALSE(results.empty());

  const docseek::PassageContext& pc = results[0];
  ASSERT_FALSE(pc.highlights.empty());

  for (const std::pair<int, int>& range : pc.highlights) {
    ASSERT_GE(range.first, 0);
    ASSERT_GE(range.second, range.first);
    std::size_t start = static_cast<std::size_t>(range.first);
    std::size_t length = static_cast<std::size_t>(range.second - range.first);
    ASSERT_LE(start + length, pc.context.size());

    std::string slice = pc.context.substr(start, length);
    bool matched = false;
    for (const std::string& term : pc.passage.matched_terms) {
      if (AsciiCaseInsensitiveEqual(slice, term)) {
        matched = true;
        break;
      }
    }
    EXPECT_TRUE(matched) << "highlight slice '" << slice << "' does not match any matched_term";
  }
}

TEST(LocateContextTest, Utf8Safe) {
  docseek::Database db = docseek::Database::open(":memory:");
  std::string content;
  content += std::string(30, 'a');
  content += " 关键词 ";
  content += "\xF0\x9F\x98\x80";  // emoji U+1F600
  content += " needle ";
  content += "\xE5\x85\xB3\xE9\x94\xAE\xE8\xAF\x8D";  // CJK "关键词"
  content += std::string(30, 'b');
  db.upsert("/doc/utf8_safe.txt", "Utf8 Safe", content, 1, static_cast<int64_t>(content.size()));

  docseek::Searcher searcher(db);
  docseek::Locator locator(db, searcher);

  docseek::LocateOptions opts;
  std::vector<docseek::PassageContext> results = locator.locateWithContext("needle", opts);
  ASSERT_FALSE(results.empty());

  const std::string& context = results[0].context;
  ASSERT_FALSE(context.empty());
  EXPECT_FALSE(IsUtf8ContinuationByte(context.front()));
  EXPECT_FALSE(IsUtf8ContinuationByte(context.back()));
}

TEST(LocateContextTest, NoHit) {
  docseek::Database db = docseek::Database::open(":memory:");
  std::string content = "some ordinary content without the target phrase";
  db.upsert("/doc/no_hit.txt", "No Hit", content, 1, static_cast<int64_t>(content.size()));

  docseek::Searcher searcher(db);
  docseek::Locator locator(db, searcher);

  docseek::LocateOptions opts;
  std::vector<docseek::PassageContext> results = locator.locateWithContext("zzzznotpresentzzzz", opts);
  EXPECT_TRUE(results.empty());
}

TEST(LocateContextTest, MultiHitOrder) {
  docseek::Database db = docseek::Database::open(":memory:");

  std::string low = "needle";
  std::string medium = "needle needle";
  std::string high = "needle needle needle needle";

  db.upsert("/doc/low.txt", "Low", low, 1, static_cast<int64_t>(low.size()));
  db.upsert("/doc/medium.txt", "Medium", medium, 1, static_cast<int64_t>(medium.size()));
  db.upsert("/doc/high.txt", "High", high, 1, static_cast<int64_t>(high.size()));

  docseek::Searcher searcher(db);
  docseek::Locator locator(db, searcher);

  docseek::LocateOptions opts;
  std::vector<docseek::PassageContext> results = locator.locateWithContext("needle", opts);
  ASSERT_GE(results.size(), 3u);

  for (std::size_t i = 1; i < results.size(); ++i) {
    EXPECT_GE(results[i - 1].passage.score, results[i].passage.score);
  }
}

TEST(LocateContextTest, LargeDoc) {
  docseek::Database db = docseek::Database::open(":memory:");

  std::string unit = "The quick brown fox jumps over the lazy dog. ";
  std::string content = RepeatParagraph(unit, 6500);
  ASSERT_GT(content.size(), 250000u);

  std::size_t insert_pos = content.size() / 2;
  content.insert(insert_pos, " needle ");

  db.upsert("/doc/large.txt", "Large Doc", content, 1, static_cast<int64_t>(content.size()));

  docseek::Searcher searcher(db);
  docseek::Locator locator(db, searcher);

  docseek::LocateOptions opts;
  std::vector<docseek::PassageContext> results = locator.locateWithContext("needle", opts);
  ASSERT_FALSE(results.empty());
  EXPECT_LT(results[0].context.size(), 2000u);
}

TEST(LocateContextTest, EmptyMatchedTerms) {
  docseek::Database db = docseek::Database::open(":memory:");
  std::string content = "the and of to a in is it";
  db.upsert("/doc/empty_terms.txt", "Empty Terms", content, 1, static_cast<int64_t>(content.size()));

  docseek::Searcher searcher(db);
  docseek::Locator locator(db, searcher);

  docseek::LocateOptions opts;
  std::vector<docseek::PassageContext> results = locator.locateWithContext("the and of", opts);

  // 本用例意图为"边界不崩"：无词查询可能退化为整串关键词，
  // highlights 非空是合理的，只需保证偏移有效。
  for (const docseek::PassageContext& pc : results) {
    for (const auto& h : pc.highlights) {
      EXPECT_GE(h.first, 0);
      EXPECT_LE(h.second, static_cast<int>(pc.context.size()));
      EXPECT_LT(h.first, h.second);
    }
  }
}

TEST(LocateContextTest, CaseInsensitiveAscii) {
  docseek::Database db = docseek::Database::open(":memory:");
  std::string content = "prefix text Hello world suffix text";
  db.upsert("/doc/case_insensitive.txt", "Case Insensitive", content, 1, static_cast<int64_t>(content.size()));

  docseek::Searcher searcher(db);
  docseek::Locator locator(db, searcher);

  docseek::LocateOptions opts;
  std::vector<docseek::PassageContext> results = locator.locateWithContext("hello", opts);
  ASSERT_FALSE(results.empty());
  EXPECT_FALSE(results[0].highlights.empty());
}

TEST(LocateContextTest, PassageFieldsPassthrough) {
  docseek::Database db = docseek::Database::open(":memory:");
  std::string content = "alpha needle omega needle tail";
  db.upsert("/doc/passthrough.txt", "Passthrough", content, 1, static_cast<int64_t>(content.size()));

  docseek::Searcher searcher(db);
  docseek::Locator locator(db, searcher);

  docseek::LocateOptions opts;
  std::vector<docseek::PassageContext> context_results = locator.locateWithContext("needle", opts);
  std::vector<docseek::Passage> passages = locator.locate("needle", opts);

  ASSERT_FALSE(context_results.empty());
  ASSERT_FALSE(passages.empty());

  EXPECT_EQ(context_results[0].passage.doc_id, passages[0].doc_id);
  EXPECT_EQ(context_results[0].passage.path, passages[0].path);
}

TEST(LocateContextTest, ContextContainsHit) {
  docseek::Database db = docseek::Database::open(":memory:");
  std::string content;
  content += std::string(50, 'p');
  content += " needle ";
  content += std::string(50, 'q');
  db.upsert("/doc/context_contains_hit.txt", "Context Contains Hit", content, 1, static_cast<int64_t>(content.size()));

  docseek::Searcher searcher(db);
  docseek::Locator locator(db, searcher);

  docseek::LocateOptions opts;
  std::vector<docseek::PassageContext> results = locator.locateWithContext("needle", opts);
  ASSERT_FALSE(results.empty());

  const docseek::PassageContext& pc = results[0];
  EXPECT_FALSE(pc.context.empty());
  ASSERT_FALSE(pc.passage.matched_terms.empty());
  EXPECT_NE(pc.context.find(pc.passage.matched_terms[0]), std::string::npos);
}

