#include <gtest/gtest.h>

#include "docseek/query_parser.h"

TEST(LocateTargetTest, DoubleQuote) {
    EXPECT_EQ(docseek::extractLocateTarget("找出提到\"退款政策\"的那段话"), "退款政策");
}

TEST(LocateTargetTest, CornerQuote) {
    EXPECT_EQ(docseek::extractLocateTarget("请问提到「售后流程」的部分"), "售后流程");
}

TEST(LocateTargetTest, CurlQuote) {
    EXPECT_EQ(docseek::extractLocateTarget("我想看“发票说明”那段"), "发票说明");
}

TEST(LocateTargetTest, TriggerTidao) {
    EXPECT_EQ(docseek::extractLocateTarget("哪里提到了退款政策？"), "退款政策");
}

TEST(LocateTargetTest, TriggerXiedao) {
    EXPECT_EQ(docseek::extractLocateTarget("文档写到退款政策在哪里"), "退款政策");
}

TEST(LocateTargetTest, TriggerShuodao) {
    EXPECT_EQ(docseek::extractLocateTarget("用户说到售后流程的那部分"), "售后流程");
}

TEST(LocateTargetTest, TriggerJiangdao) {
    EXPECT_EQ(docseek::extractLocateTarget("材料讲到物流时效的那段"), "物流时效");
}

TEST(LocateTargetTest, TriggerTandao) {
    EXPECT_EQ(docseek::extractLocateTarget("谈到会员权益是什么"), "会员权益");
}

TEST(LocateTargetTest, TriggerJieshao) {
    EXPECT_EQ(docseek::extractLocateTarget("请介绍支付方式的那句"), "支付方式");
}

TEST(LocateTargetTest, EndNaBufen) {
    EXPECT_EQ(docseek::extractLocateTarget("帮我找一下售后流程的那部分"), "售后流程");
}

TEST(LocateTargetTest, EndNaYiduan) {
    EXPECT_EQ(docseek::extractLocateTarget("退款政策写在哪一段"), "退款政策");
}

TEST(LocateTargetTest, EndNaYiju) {
    EXPECT_EQ(docseek::extractLocateTarget("讲到隐私协议是哪一句"), "隐私协议");
}

TEST(LocateTargetTest, EndChineseQuestion) {
    EXPECT_EQ(docseek::extractLocateTarget("提到账号注销？"), "账号注销");
}

TEST(LocateTargetTest, EndAsciiQuestion) {
    EXPECT_EQ(docseek::extractLocateTarget("介绍运费规则?"), "运费规则");
}

TEST(LocateTargetTest, EndPeriod) {
    EXPECT_EQ(docseek::extractLocateTarget("提到发票说明。"), "发票说明");
}

TEST(LocateTargetTest, LocXiezaina) {
    EXPECT_EQ(docseek::extractLocateTarget("退款政策写在哪"), "退款政策");
}

TEST(LocateTargetTest, LocZaina) {
    EXPECT_EQ(docseek::extractLocateTarget("发票说明在哪"), "发票说明");
}

TEST(LocateTargetTest, LocNali) {
    EXPECT_EQ(docseek::extractLocateTarget("会员权益哪里"), "会员权益");
}

TEST(LocateTargetTest, LocHechu) {
    EXPECT_EQ(docseek::extractLocateTarget("隐私政策何处"), "隐私政策");
}

TEST(LocateTargetTest, LeadQingwen) {
    EXPECT_EQ(docseek::extractLocateTarget("请问退款政策在哪"), "退款政策");
}

TEST(LocateTargetTest, LeadQingGaosu) {
    EXPECT_EQ(docseek::extractLocateTarget("请告诉我发票说明在哪里"), "发票说明");
}

TEST(LocateTargetTest, LeadBangwozhao) {
    EXPECT_EQ(docseek::extractLocateTarget("帮我找售后流程在哪"), "售后流程");
}

TEST(LocateTargetTest, LeadZhaochu) {
    EXPECT_EQ(docseek::extractLocateTarget("找出退款政策在哪里"), "退款政策");
}

TEST(LocateTargetTest, LeadNage) {
    EXPECT_EQ(docseek::extractLocateTarget("那个运费规则在哪里"), "运费规则");
}

TEST(LocateTargetTest, LeadZhege) {
    EXPECT_EQ(docseek::extractLocateTarget("这个支付方式在哪里"), "支付方式");
}

TEST(LocateTargetTest, NoTarget) {
    EXPECT_EQ(docseek::extractLocateTarget("今天天气怎么样"), "");
}

TEST(LocateTargetTest, EmptyInput) {
    EXPECT_EQ(docseek::extractLocateTarget(""), "");
}

TEST(LocateTargetTest, PunctOnly) {
    EXPECT_EQ(docseek::extractLocateTarget("？？？！！。"), "");
}

TEST(LocateTargetTest, TriggerAtStart) {
    EXPECT_EQ(docseek::extractLocateTarget("提到退款政策的那段"), "退款政策");
}

TEST(LocateTargetTest, TriggerAtEnd) {
    EXPECT_EQ(docseek::extractLocateTarget("退款政策提到"), "");
}

TEST(LocateTargetTest, MultipleTriggers) {
    EXPECT_EQ(docseek::extractLocateTarget("提到退款政策，介绍发票说明的那段"), "退款政策");
}

TEST(LocateTargetTest, UnclosedQuoteFallthrough) {
    EXPECT_EQ(docseek::extractLocateTarget("提到\"退款政策的那段"), "退款政策");
}

TEST(LocateTargetTest, QuotePriorityOverTrigger) {
    EXPECT_EQ(docseek::extractLocateTarget("提到别的，找到\"退款政策\"在哪"), "退款政策");
}

TEST(LocateTargetTest, EndPriorityOverLoc) {
    EXPECT_EQ(docseek::extractLocateTarget("介绍退款政策在哪一段"), "退款政策");
}

TEST(LocateTargetTest, WhitespaceInput) {
    EXPECT_EQ(docseek::extractLocateTarget("   \t  "), "");
}

