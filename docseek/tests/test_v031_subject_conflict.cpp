#include <gtest/gtest.h>
#include <docseek/passage_ranker.h>
#include <docseek/query_parser.h>
#include <string>
#include <vector>

using namespace docseek;

namespace {

inline ParsedQuery makePqNo(const std::vector<std::string>& keywords,
                            const std::string& subjectNo) {
  ParsedQuery pq;
  pq.keywords = keywords;
  pq.querySubjectNo = subjectNo;
  return pq;
}

inline TermWeights makeWeights() { return TermWeights{}; }

} // namespace

TEST(SubjectConflictV031, DetectPositive) {
  // "科目一" 被识别，返回 "一"
  auto pq = parseNaturalQuery("科目一考试的时候到底要不要改答案？");
  EXPECT_EQ(pq.querySubjectNo, "一");
}

TEST(SubjectConflictV031, DetectKeShorthand) {
  // "科二" 简写被识别，返回 "二"
  auto pq = parseNaturalQuery("科二考试当天流程是怎样的");
  EXPECT_EQ(pq.querySubjectNo, "二");
}

TEST(SubjectConflictV031, DetectAmbiguousFailSafe) {
  // 同时出现"科目一"和"科目二"，编号矛盾，fail-safe 返回空串
  auto pq = parseNaturalQuery("科目一和科目二有什么区别");
  EXPECT_EQ(pq.querySubjectNo, "");
}

TEST(SubjectConflictV031, DetectNone) {
  // 无科目编号，返回空串
  auto pq = parseNaturalQuery("今天天气怎么样");
  EXPECT_EQ(pq.querySubjectNo, "");
}

TEST(SubjectConflictV031, DetectSameNumberTwice) {
  // 同一编号出现两次不算歧义，仍返回 "一"
  auto pq = parseNaturalQuery("科目一 科目一 挂科了怎么办");
  EXPECT_EQ(pq.querySubjectNo, "一");
}

TEST(SubjectConflictV031, PenaltyApplied) {
  // 查询编号为"一"，窗口含冲突编号"科目二"且不含"科目一"，应扣 0.08
  std::string contentA = "科目二考试流程\n第二行内容";
  std::vector<std::string> keywords = {"科目", "考试"};
  auto pqA = makePqNo(keywords, "一");
  auto pqB = makePqNo(keywords, "");

  auto passagesA = rankPassages(0, "", contentA, pqA, 10, makeWeights(), "");
  auto passagesB = rankPassages(0, "", contentA, pqB, 10, makeWeights(), "");

  ASSERT_FALSE(passagesA.empty());
  ASSERT_FALSE(passagesB.empty());
  // 有矛盾惩罚时 score 应严格小于无惩罚时
  EXPECT_LT(passagesA[0].score, passagesB[0].score);
}

TEST(SubjectConflictV031, AgreementNoPenalty) {
  // 查询编号为"一"，窗口含"科目一"，编号一致不扣分
  std::string contentB = "科目一考试流程\n第二行内容";
  std::vector<std::string> keywords = {"科目", "考试"};
  auto pqA = makePqNo(keywords, "一");
  auto pqB = makePqNo(keywords, "");

  auto passagesA = rankPassages(0, "", contentB, pqA, 10, makeWeights(), "");
  auto passagesB = rankPassages(0, "", contentB, pqB, 10, makeWeights(), "");

  ASSERT_FALSE(passagesA.empty());
  ASSERT_FALSE(passagesB.empty());
  // 窗口含查询编号，一致不罚，两者 score 相等
  EXPECT_DOUBLE_EQ(passagesA[0].score, passagesB[0].score);
}
