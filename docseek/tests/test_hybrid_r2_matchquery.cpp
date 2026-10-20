#include <gtest/gtest.h>

#include <filesystem>
#include <string>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

namespace {

fs::path makeUniqueDir(const std::string& name) {
    fs::path base = fs::current_path() / "test-tmp" / name;
    std::error_code ec;
    fs::remove_all(base, ec);
    fs::create_directories(base, ec);
    return base;
}

}  // namespace

TEST(MatchQueryR2, BuildMatchQueryHasAndAndTokens) {
    fs::path dir = makeUniqueDir("matchquery_r2_and");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    std::string out = docseek::Searcher::buildMatchQuery("苹果 香蕉");
    EXPECT_NE(out.find(" AND "), std::string::npos);
    EXPECT_NE(out.find("苹果"), std::string::npos);
    EXPECT_NE(out.find("香蕉"), std::string::npos);
}

TEST(MatchQueryR2, BuildOrMatchQueryHasOrAndTokens) {
    fs::path dir = makeUniqueDir("matchquery_r2_or");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    std::string out = docseek::Searcher::buildOrMatchQuery("苹果 香蕉");
    EXPECT_NE(out.find(" OR "), std::string::npos);
    EXPECT_NE(out.find("苹果"), std::string::npos);
    EXPECT_NE(out.find("香蕉"), std::string::npos);
}

TEST(MatchQueryR2, AndOrOutputsDiffer) {
    fs::path dir = makeUniqueDir("matchquery_r2_diff");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    std::string andOut = docseek::Searcher::buildMatchQuery("苹果 香蕉");
    std::string orOut = docseek::Searcher::buildOrMatchQuery("苹果 香蕉");
    EXPECT_NE(andOut, orOut);
}

TEST(MatchQueryR2, SingleTokenNonEmptyAndContains) {
    fs::path dir = makeUniqueDir("matchquery_r2_single");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    std::string andOut = docseek::Searcher::buildMatchQuery("检索");
    std::string orOut = docseek::Searcher::buildOrMatchQuery("检索");
    EXPECT_FALSE(andOut.empty());
    EXPECT_NE(andOut.find("检索"), std::string::npos);
    EXPECT_FALSE(orOut.empty());
    EXPECT_NE(orOut.find("检索"), std::string::npos);
}

TEST(MatchQueryR2, QuoteInputAndEmptyInput) {
    fs::path dir = makeUniqueDir("matchquery_r2_quote");
    docseek::Database db = docseek::Database::open((dir / "x.db").string());
    std::string quoted;
    EXPECT_NO_THROW(quoted = docseek::Searcher::buildMatchQuery("a\"b"));
    EXPECT_FALSE(quoted.empty());
    std::string emptyOut = docseek::Searcher::buildMatchQuery("");
    EXPECT_TRUE(emptyOut.empty());
}