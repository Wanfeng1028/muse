#include <gtest/gtest.h>

#include "docseek/jieba_tokenizer.h"

#include <string>
#include <vector>

namespace {

using std::string;
using std::vector;

vector<string> cut(const cppjieba::Jieba* j, const string& text) {
    vector<string> words;
    j->CutForSearch(text, words);
    return words;
}

void expectTokens(const cppjieba::Jieba* j, const string& text,
                  const vector<string>& expected) {
    const vector<string> actual = cut(j, text);
    ASSERT_EQ(actual.size(), expected.size()) << "text=" << text;
    for (size_t i = 0; i < expected.size(); ++i) {
        EXPECT_EQ(actual[i], expected[i]) << "text=" << text << " index=" << i;
    }
}

}  // namespace

TEST(TokenizerDeepV019, AmbiguousSegmentation) {
    const cppjieba::Jieba* j = docseek::jiebaInstance();
    if (!j) GTEST_SKIP();

    expectTokens(j, "咬死了猎人的狗",
                 {"咬", "死", "了", "猎人", "的", "狗"});
    expectTokens(j, "三个学校的老师来了",
                 {"三个", "学校", "的", "老师", "来", "了"});
    expectTokens(j, "热爱人民的总理",
                 {"热爱", "爱人", "人民", "热爱人民", "的", "总理"});
}

TEST(TokenizerDeepV019, AmbiguousSegmentationMore) {
    const cppjieba::Jieba* j = docseek::jiebaInstance();
    if (!j) GTEST_SKIP();

    expectTokens(j, "对售货员的态度不好",
                 {"对", "售货", "货员", "售货员", "的", "态度", "不好"});
    expectTokens(j, "发现敌人的哨兵回来了",
                 {"发现", "敌人", "的", "哨兵", "回来", "了"});
    expectTokens(j, "咬伤了他的狗",
                 {"咬伤", "了", "他", "的", "狗"});
    expectTokens(j, "白天鹅在湖边飞",
                 {"白天", "天鹅", "白天鹅", "在", "湖边", "飞"});
}

TEST(TokenizerDeepV019, AmbiguousSegmentationFinal) {
    const cppjieba::Jieba* j = docseek::jiebaInstance();
    if (!j) GTEST_SKIP();

    expectTokens(j, "研究生命的起源",
                 {"研究", "生命", "的", "起源"});
    expectTokens(j, "打倒敌人的方法",
                 {"打倒", "敌人", "的", "方法"});
    expectTokens(j, "下雨天留客天留我不留",
                 {"下雨", "雨天", "下雨天", "留客", "天留", "我", "不留"});
}

TEST(TokenizerDeepV019, Neologism) {
    const cppjieba::Jieba* j = docseek::jiebaInstance();
    if (!j) GTEST_SKIP();

    expectTokens(j, "绝绝子", {"绝绝子"});
    expectTokens(j, "破防了", {"破防", "了"});
    expectTokens(j, "内卷", {"内卷"});
    expectTokens(j, "躺平", {"躺平"});
    expectTokens(j, "栓Q", {"栓", "Q"});
    expectTokens(j, "emo了", {"emo", "了"});
    expectTokens(j, "显眼包", {"显眼", "包"});
    expectTokens(j, "搭子", {"搭子"});
    expectTokens(j, "特种兵旅游", {"特种", "特种兵", "旅游"});
    expectTokens(j, "数智化", {"数智化"});
}

TEST(TokenizerDeepV019, MixedAsciiDigit) {
    const cppjieba::Jieba* j = docseek::jiebaInstance();
    if (!j) GTEST_SKIP();

    expectTokens(j, "iPhone15的WiFi6配置说明",
                 {"iPhone15", "的", "WiFi6", "配置", "说明"});
    expectTokens(j, "5G套餐降到99元",
                 {"5", "G", "套餐", "降到", "99", "元"});
    expectTokens(j, "Python3的pip安装教程",
                 {"Python3", "的", "pip", "安装", "教程"});
    expectTokens(j, "用C++17写本地检索",
                 {"用", "C++", "17", "写", "本地", "检索"});
    expectTokens(j, "GPT4模型API调用示例",
                 {"GPT4", "模型", "API", "调用", "示例"});
}

TEST(TokenizerDeepV019, MixedAsciiDigitMore) {
    const cppjieba::Jieba* j = docseek::jiebaInstance();
    if (!j) GTEST_SKIP();

    expectTokens(j, "RTX4090显卡功耗测试",
                 {"RTX4090", "显卡", "功耗", "测试"});
    expectTokens(j, "macOS14系统更新日志",
                 {"macOS14", "系统", "更新", "日志"});
    expectTokens(j, "蓝牙5.3协议兼容性",
                 {"蓝牙", "5.3", "协议", "兼容", "容性", "兼容性"});
    expectTokens(j, "A股三大指数集体上涨",
                 {"A", "股三大", "指数", "集体", "上涨"});
    expectTokens(j, "WiFi7路由器推荐",
                 {"WiFi7", "路由", "路由器", "推荐"});
}

TEST(TokenizerDeepV019, LongWord) {
    const cppjieba::Jieba* j = docseek::jiebaInstance();
    if (!j) GTEST_SKIP();

    expectTokens(j, "中华人民共和国国家标准",
                 {"中华", "华人", "人民", "共和", "共和国",
                  "中华人民共和国", "国家", "标准", "国家标准"});
    expectTokens(j, "开开心心快快乐乐",
                 {"开开", "开心", "心心", "开开心", "开开心心",
                  "快快", "快乐", "乐乐", "快快乐乐"});
    expectTokens(j, "高高兴兴平平安安",
                 {"高高", "高兴", "高高兴兴", "平平", "平安",
                  "安安", "平平安安"});
    expectTokens(j, "中国互联网信息中心",
                 {"中国", "互联", "联网", "互联网", "信息", "中心",
                  "信息中心"});
}

TEST(TokenizerDeepV019, LongWordMore) {
    const cppjieba::Jieba* j = docseek::jiebaInstance();
    if (!j) GTEST_SKIP();

    expectTokens(j, "全国人民代表大会常务委员会",
                 {"全国", "国人", "人民", "代表", "大会", "常务",
                  "委员", "委员会", "全国人民代表大会常务委员会"});
    expectTokens(j, "密密麻麻层层叠叠",
                 {"密密", "麻麻", "密麻麻", "密密麻麻", "层层",
                  "层叠", "叠叠", "层层叠叠"});
    expectTokens(j, "兢兢业业勤勤恳恳",
                 {"兢兢业业", "勤恳", "勤勤恳恳"});
    expectTokens(j, "大大方方清清楚楚",
                 {"大大", "大方", "方方", "大大方方", "清清",
                  "清楚", "楚楚", "清清楚楚"});
}

TEST(TokenizerDeepV019, LongWordFinal) {
    const cppjieba::Jieba* j = docseek::jiebaInstance();
    if (!j) GTEST_SKIP();

    expectTokens(j, "国家语言文字工作委员会",
                 {"国家", "语言", "文字", "工作", "委员", "委员会",
                  "语言文字工作委员会"});
    expectTokens(j, "晃晃悠悠跌跌撞撞",
                 {"晃晃", "晃悠", "悠悠", "晃悠悠", "晃晃悠悠",
                  "跌跌", "跌跌撞撞"});
}

TEST(TokenizerDeepV019, ClassicalTerm) {
    const cppjieba::Jieba* j = docseek::jiebaInstance();
    if (!j) GTEST_SKIP();

    expectTokens(j, "子曰学而时习之",
                 {"子", "曰", "学而", "时习", "之"});
    expectTokens(j, "己所不欲勿施于人",
                 {"己所不欲", "勿施于人"});
    expectTokens(j, "千里之行始于足下",
                 {"千里", "之行", "千里之行", "始于", "足下", "始于足下"});
    expectTokens(j, "天行健君子以自强不息",
                 {"行健", "天行健", "君子", "以", "自强", "不息",
                  "自强不息"});
}

TEST(TokenizerDeepV019, TechnicalTerm) {
    const cppjieba::Jieba* j = docseek::jiebaInstance();
    if (!j) GTEST_SKIP();

    expectTokens(j, "心肌梗死溶栓治疗",
                 {"心肌", "梗死", "心肌梗死", "溶栓", "治疗"});
    expectTokens(j, "不当得利返还请求权",
                 {"不当", "当得", "得利", "不当得利", "返还",
                  "请求", "请求权"});
    expectTokens(j, "慢性阻塞性肺疾病",
                 {"慢性", "阻塞", "阻塞性", "肺", "疾病"});
    expectTokens(j, "预应力混凝土结构",
                 {"应力", "预应力", "混凝土", "结构"});
    expectTokens(j, "不可抗力免责条款",
                 {"不可", "抗力", "不可抗力", "免责", "条款"});
    expectTokens(j, "冠状动脉粥样硬化",
                 {"冠状", "动脉", "冠状动脉", "粥样", "硬化"});
}

TEST(TokenizerDeepV019, TradMixed) {
    const cppjieba::Jieba* j = docseek::jiebaInstance();
    if (!j) GTEST_SKIP();

    expectTokens(j, "軟體開發工程師的简历",
                 {"軟體", "開發", "工程", "師的", "简历"});
    expectTokens(j, "數據庫索引優化方案",
                 {"數據庫", "索引", "優化", "方案"});
    expectTokens(j, "雲端運算與邊緣計算",
                 {"雲端", "運算", "與", "邊緣", "計算"});
    expectTokens(j, "機器學習模型訓練",
                 {"機器", "學習", "模型", "訓練"});
}

TEST(TokenizerDeepV019, TradMixedMore) {
    const cppjieba::Jieba* j = docseek::jiebaInstance();
    if (!j) GTEST_SKIP();

    expectTokens(j, "網絡安全防護措施",
                 {"網絡", "安全", "防護", "措施"});
    expectTokens(j, "電商平台用戶體驗",
                 {"電商", "平台", "用戶", "體驗"});
    expectTokens(j, "人工智能與大數據",
                 {"人工", "智能", "人工智能", "與", "大數據"});
    expectTokens(j, "區塊鏈技術應用",
                 {"區塊", "鏈技術", "應用"});
    expectTokens(j, "自動駕駛汽車測試",
                 {"自動", "駕駛", "汽車", "測試"});
    expectTokens(j, "醫療器械註冊管理",
                 {"醫療", "器械", "註", "冊", "管理"});
}

TEST(TokenizerDeepV019, Determinism) {
    const cppjieba::Jieba* j = docseek::jiebaInstance();
    if (!j) GTEST_SKIP();

    const string text = "iPhone15的WiFi6配置说明";
    const vector<string> first = cut(j, text);
    const vector<string> second = cut(j, text);
    ASSERT_EQ(first.size(), second.size());
    for (size_t i = 0; i < first.size(); ++i) {
        EXPECT_EQ(first[i], second[i]) << "index=" << i;
    }
}

TEST(TokenizerDeepV019, NoEmptyTokens) {
    const cppjieba::Jieba* j = docseek::jiebaInstance();
    if (!j) GTEST_SKIP();

    const vector<string> texts = {
        "咬死了猎人的狗",
        "三个学校的老师来了",
        "热爱人民的总理",
        "对售货员的态度不好",
        "发现敌人的哨兵回来了",
        "咬伤了他的狗",
        "白天鹅在湖边飞",
        "研究生命的起源",
        "打倒敌人的方法",
        "下雨天留客天留我不留",
        "绝绝子",
        "破防了",
        "内卷",
        "躺平",
        "栓Q",
        "emo了",
        "显眼包",
        "搭子",
        "特种兵旅游",
        "数智化",
        "iPhone15的WiFi6配置说明",
        "5G套餐降到99元",
        "Python3的pip安装教程",
        "用C++17写本地检索",
        "GPT4模型API调用示例",
        "RTX4090显卡功耗测试",
        "macOS14系统更新日志",
        "蓝牙5.3协议兼容性",
        "A股三大指数集体上涨",
        "WiFi7路由器推荐",
        "中华人民共和国国家标准",
        "开开心心快快乐乐",
        "高高兴兴平平安安",
        "中国互联网信息中心",
        "全国人民代表大会常务委员会",
        "密密麻麻层层叠叠",
        "兢兢业业勤勤恳恳",
        "大大方方清清楚楚",
        "国家语言文字工作委员会",
        "晃晃悠悠跌跌撞撞",
        "子曰学而时习之",
        "心肌梗死溶栓治疗",
        "己所不欲勿施于人",
        "不当得利返还请求权",
        "慢性阻塞性肺疾病",
        "预应力混凝土结构",
        "千里之行始于足下",
        "不可抗力免责条款",
        "冠状动脉粥样硬化",
        "天行健君子以自强不息",
        "軟體開發工程師的简历",
        "數據庫索引優化方案",
        "雲端運算與邊緣計算",
        "機器學習模型訓練",
        "網絡安全防護措施",
        "電商平台用戶體驗",
        "人工智能與大數據",
        "區塊鏈技術應用",
        "自動駕駛汽車測試",
        "醫療器械註冊管理",
    };

    for (const string& text : texts) {
        SCOPED_TRACE(text);
        const vector<string> words = cut(j, text);
        EXPECT_FALSE(words.empty());
        for (size_t i = 0; i < words.size(); ++i) {
            EXPECT_FALSE(words[i].empty()) << "index=" << i;
        }
    }
}
