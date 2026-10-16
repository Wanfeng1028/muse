
#include <gtest/gtest.h>

#include "docseek/token_locate.h"

#include <set>
#include <string>
#include <utility>
#include <vector>

namespace docseek {
namespace {

TEST(TokenLocate, OverlappingWordsNotLost) {
    const std::string text = "计算机技术";
    const std::vector<std::string> words = {"计算", "算机", "技术", "计算机",
                                            "计算机技术"};
    std::set<std::pair<std::string, size_t>> claimed;

    const std::vector<LocatedToken> located =
        claimTokenPositions(text, words, claimed);

    ASSERT_EQ(located.size(), 5u);
    EXPECT_EQ(located[0].word, "计算");
    EXPECT_EQ(located[0].byteOffset, 0u);
    EXPECT_EQ(located[1].word, "算机");
    EXPECT_EQ(located[1].byteOffset, 3u);
    EXPECT_EQ(located[2].word, "技术");
    EXPECT_EQ(located[2].byteOffset, 9u);
    EXPECT_EQ(located[3].word, "计算机");
    EXPECT_EQ(located[3].byteOffset, 0u);
    EXPECT_EQ(located[4].word, "计算机技术");
    EXPECT_EQ(located[4].byteOffset, 0u);
}

TEST(TokenLocate, DuplicateWordClaimsNextOccurrence) {
    const std::string text = "ab ab";
    const std::vector<std::string> words = {"ab", "ab"};
    std::set<std::pair<std::string, size_t>> claimed;

    const std::vector<LocatedToken> located =
        claimTokenPositions(text, words, claimed);

    ASSERT_EQ(located.size(), 2u);
    EXPECT_EQ(located[0].word, "ab");
    EXPECT_EQ(located[0].byteOffset, 0u);
    EXPECT_EQ(located[1].word, "ab");
    EXPECT_EQ(located[1].byteOffset, 3u);
}

TEST(TokenLocate, DuplicateWordExhausted) {
    const std::string text = "ab";
    const std::vector<std::string> words = {"ab", "ab"};
    std::set<std::pair<std::string, size_t>> claimed;

    const std::vector<LocatedToken> located =
        claimTokenPositions(text, words, claimed);

    ASSERT_EQ(located.size(), 1u);
    EXPECT_EQ(located[0].word, "ab");
    EXPECT_EQ(located[0].byteOffset, 0u);
}

TEST(TokenLocate, UnlocatableWordSkipped) {
    const std::string text = "hello";
    const std::vector<std::string> words = {"xyz"};
    std::set<std::pair<std::string, size_t>> claimed;

    const std::vector<LocatedToken> located =
        claimTokenPositions(text, words, claimed);

    EXPECT_TRUE(located.empty());
}

TEST(TokenLocate, EmptyWordSkipped) {
    const std::string text = "abc";
    const std::vector<std::string> words = {"", "abc", ""};
    std::set<std::pair<std::string, size_t>> claimed;

    const std::vector<LocatedToken> located =
        claimTokenPositions(text, words, claimed);

    ASSERT_EQ(located.size(), 1u);
    EXPECT_EQ(located[0].word, "abc");
    EXPECT_EQ(located[0].byteOffset, 0u);
}

TEST(TokenLocate, SharedClaimedSetAcrossCalls) {
    const std::string text = "计算机技术";
    std::set<std::pair<std::string, size_t>> claimed;

    const std::vector<std::string> firstWords = {"计算"};
    const std::vector<LocatedToken> first =
        claimTokenPositions(text, firstWords, claimed);
    ASSERT_EQ(first.size(), 1u);
    EXPECT_EQ(first[0].byteOffset, 0u);

    const std::vector<std::string> secondWords = {"计算", "计算机"};
    const std::vector<LocatedToken> second =
        claimTokenPositions(text, secondWords, claimed);

    ASSERT_EQ(second.size(), 1u);
    EXPECT_EQ(second[0].word, "计算机");
    EXPECT_EQ(second[0].byteOffset, 0u);
}

TEST(TokenLocate, EmptyInput) {
    std::set<std::pair<std::string, size_t>> claimed;

    const std::vector<LocatedToken> emptyText =
        claimTokenPositions("", {"ab"}, claimed);
    EXPECT_TRUE(emptyText.empty());

    const std::vector<LocatedToken> emptyWords =
        claimTokenPositions("ab", {}, claimed);
    EXPECT_TRUE(emptyWords.empty());
}

}  // namespace
}  // namespace docseek
