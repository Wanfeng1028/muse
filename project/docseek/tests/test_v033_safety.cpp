#include <gtest/gtest.h>
#include <docseek/passage_ranker.h>
#include <docseek/query_parser.h>
#include <string>
#include <vector>
using namespace docseek;

TEST(SafetyV033, DetectPositiveUnsafe) {
  // raw 含"不安全"，asksSafety 应为真
  auto pq = parseNaturalQuery("为什么运动鞋骑马不安全，脚会卡住吗");
  EXPECT_TRUE(pq.asksSafety);
}

TEST(SafetyV033, DetectPositiveDanger) {
  // raw 含"危险"，asksSafety 应为真
  auto pq = parseNaturalQuery("不戴头盔骑电动车危险吗");
  EXPECT_TRUE(pq.asksSafety);
}

TEST(SafetyV033, DetectNonePlainSafety) {
  // 只含"安全"，不含"不安全"/"危险"，asksSafety 应为假
  auto pq = parseNaturalQuery("马场安全规则");
  EXPECT_FALSE(pq.asksSafety);
}

TEST(SafetyV033, DetectNoneSafeWord) {
  // 含"安全"但非"不安全"，asksSafety 应为假
  auto pq = parseNaturalQuery("一个人 安全");
  EXPECT_FALSE(pq.asksSafety);
}

TEST(SafetyV033, DetectNoneKeyword) {
  // 无安全相关关键词，asksSafety 应为假
  auto pq = parseNaturalQuery("三色激光散斑");
  EXPECT_FALSE(pq.asksSafety);
}

TEST(SafetyV033, BonusApplied) {
  // asksSafety 为真且窗口含"危险"时加 0.08 一次
  std::string content = "运动鞋是常见的运动装备。\n穿运动鞋骑马是很危险的事，脚会卡住。";
  auto pq_true = parseNaturalQuery("运动鞋骑马不安全");
  auto pq_false = pq_true;
  pq_false.asksSafety = false;
  // 两组 pq 的 keywords 均为 {"运动鞋"}，除 asksSafety 外完全相同

  auto res_true  = rankPassages(0, "", content, pq_true,  10, TermWeights{}, "");
  auto res_false = rankPassages(0, "", content, pq_false, 10, TermWeights{}, "");

  ASSERT_FALSE(res_true.empty());
  ASSERT_FALSE(res_false.empty());
  EXPECT_NEAR(res_true[0].score - res_false[0].score, 0.08, 1e-9);
}

TEST(SafetyV033, NoBonusWithoutMarker) {
  // content 含"运动鞋"但不含"危险"，不应加 bonus
  std::string content = "运动鞋适合跑步和健身。\n运动鞋的选择很重要。";
  auto pq_true = parseNaturalQuery("运动鞋骑马不安全");
  auto pq_false = pq_true;
  pq_false.asksSafety = false;

  auto res_true  = rankPassages(0, "", content, pq_true,  10, TermWeights{}, "");
  auto res_false = rankPassages(0, "", content, pq_false, 10, TermWeights{}, "");

  ASSERT_FALSE(res_true.empty());
  ASSERT_FALSE(res_false.empty());
  EXPECT_NEAR(res_true[0].score - res_false[0].score, 0.0, 1e-9);
}

TEST(SafetyV033, MultipleMarkersSingleBonus) {
  // 同一窗口内含两次"危险"，bonus 只加一次，不叠加
  std::string content = "穿运动鞋骑马是危险且危险的行为。";
  auto pq_true = parseNaturalQuery("运动鞋骑马不安全");
  auto pq_false = pq_true;
  pq_false.asksSafety = false;

  auto res_true  = rankPassages(0, "", content, pq_true,  10, TermWeights{}, "");
  auto res_false = rankPassages(0, "", content, pq_false, 10, TermWeights{}, "");

  ASSERT_FALSE(res_true.empty());
  ASSERT_FALSE(res_false.empty());
  EXPECT_NEAR(res_true[0].score - res_false[0].score, 0.08, 1e-9);
}