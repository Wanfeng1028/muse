#include <gtest/gtest.h>

#include <string>
#include <vector>

#include "docseek/structural_precision.h"

namespace docseek {
namespace {

bool containsStr(const std::vector<std::string>& vec, const std::string& value) {
    for (const auto& item : vec) {
        if (item == value) return true;
    }
    return false;
}

TEST(StructuralPrecision, EntryListMarker) {
    EXPECT_TRUE(isEntryLikeLineStart("肩膀疼的三个原因", true, 9));
}

TEST(StructuralPrecision, EntryShortLine) {
    EXPECT_TRUE(isEntryLikeLineStart("忘词不丢人，处理得自然，很多人根本发现不了。", false, 6));
}

TEST(StructuralPrecision, EntryColon) {
    EXPECT_TRUE(isEntryLikeLineStart("肩膀疼：三个常见原因和恢复方法", false, 9));
}

TEST(StructuralPrecision, EntryLongProseRejected) {
    EXPECT_FALSE(isEntryLikeLineStart("肩膀疼通常是拉球动作不对，抡大臂而不是用腰腿发力。年纪大一点的球友肩袖本来就退化，更容易伤。", false, 9));
}

TEST(StructuralPrecision, EntryLongProseNoDigitPanic) {
    EXPECT_FALSE(isEntryLikeLineStart("忘词时不要停下来。可以哼着旋律往下走，或者用元音代替。观众往往听不出来，但你一停，所有人都知道了。", false, 6));
}

TEST(StructuralPrecision, EntryQueryLenOverflow) {
    EXPECT_TRUE(isEntryLikeLineStart("短", false, 100));
}

TEST(StructuralPrecision, DigitFarAccidental) {
    EXPECT_FALSE(digitConsistentWithQuery("肩膀疼通常是拉球动作不对。年纪大一点的球友肩袖本来就退化。", "肩膀疼"));
}

TEST(StructuralPrecision, DigitFarAccidental2) {
    EXPECT_FALSE(digitConsistentWithQuery("忘词时不要停下来。可以哼着旋律往下走。你一停，所有人都知道了。", "忘词"));
}

TEST(StructuralPrecision, DigitAdjacentCount) {
    EXPECT_TRUE(digitConsistentWithQuery("深蹲的5个常见错误", "深蹲"));
}

TEST(StructuralPrecision, DigitNoDigitAtAll) {
    EXPECT_FALSE(digitConsistentWithQuery("肩膀疼通常是拉球动作不对", "肩膀疼"));
}

TEST(StructuralPrecision, DigitQueryWithDigitMatch) {
    EXPECT_TRUE(digitConsistentWithQuery("5个拉伸动作：每个保持30秒", "5个拉伸动作"));
}

// 查询含数字时一致性恒成立：R6' 调用方保证行以查询开头，
// 行首即含查询中的数字，无需比对。本用例锁定该语义。
TEST(StructuralPrecision, DigitQueryWithDigitVacuous) {
    EXPECT_TRUE(digitConsistentWithQuery("5个拉伸动作：每个保持30秒", "5个拉伸动作"));
}

TEST(StructuralPrecision, R1StrongCorrespondence) {
    EXPECT_DOUBLE_EQ(r1StartsWithBonusForToken({"训练频率"}, "训练频率"), 1.5);
}

TEST(StructuralPrecision, R1LongHeadingDemoted) {
    EXPECT_DOUBLE_EQ(r1StartsWithBonusForToken({"训练频率和注意"}, "训练频率"), 0.75);
}

TEST(StructuralPrecision, R1QuestionHeadingDemoted) {
    EXPECT_DOUBLE_EQ(r1StartsWithBonusForToken({"忘词怎么办"}, "忘词"), 0.75);
}

TEST(StructuralPrecision, R1ContainsOnly) {
    EXPECT_DOUBLE_EQ(r1StartsWithBonusForToken({"如何缓解肩膀疼"}, "肩膀疼"), 0.25);
}

TEST(StructuralPrecision, R1NoMatch) {
    EXPECT_DOUBLE_EQ(r1StartsWithBonusForToken({"饮食指南"}, "肩膀疼"), 0.0);
}

TEST(StructuralPrecision, R1EmptyToken) {
    EXPECT_DOUBLE_EQ(r1StartsWithBonusForToken({"肩膀疼"}, ""), 0.0);
}

TEST(StructuralPrecision, R1StartsWithBeatsContains) {
    EXPECT_DOUBLE_EQ(r1StartsWithBonusForToken({"无关标题含肩膀疼字样", "肩膀疼"}, "肩膀疼"), 1.5);
}

}  // namespace
}  // namespace docseek
