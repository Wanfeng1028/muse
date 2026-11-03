#include <gtest/gtest.h>

#include <chrono>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

#include "docseek/database.h"
#include "docseek/searcher.h"

namespace fs = std::filesystem;

namespace {

std::string makeUniqueDir(const std::string& name) {
    fs::path base = fs::current_path() / "test-tmp" / name;
    std::error_code ec;
    fs::remove_all(base, ec);
    fs::create_directories(base, ec);
    return base.string();
}

std::string longQuery() {
    const char* words[] = {
        "苹果", "香蕉", "橙子", "检索", "全文",
        "数据库", "索引", "分词", "定位", "高亮",
        "段落", "标题", "短语", "权重", "排序",
        "召回", "精排", "服务", "监控", "日志",
        "指标", "告警", "备份", "恢复", "密钥",
        "租户", "部署", "滚动", "更新", "资源",
        "容器", "安全", "注入", "鉴权", "限流",
        "超时", "熔断", "文档", "升级", "索引"
    };
    std::string q;
    for (size_t i = 0; i < sizeof(words) / sizeof(words[0]); ++i) {
        if (i != 0) q += ' ';
        q += words[i];
    }
    return q;
}

}  // namespace

TEST(HybridLongQueryR2, SearchDoesNotThrow) {
    std::string dir = makeUniqueDir("hybrid_longquery_search");
    docseek::Database db = docseek::Database::open(dir + "/x.db");
    docseek::Searcher searcher(db);

    std::string q = longQuery();
    std::vector<docseek::Hit> hits;
    ASSERT_NO_THROW(hits = searcher.search(q, 20));
    (void)hits;
}

TEST(HybridLongQueryR2, SearchQuestionDoesNotThrow) {
    std::string dir = makeUniqueDir("hybrid_longquery_question");
    docseek::Database db = docseek::Database::open(dir + "/x.db");
    docseek::Searcher searcher(db);

    std::string q = longQuery();
    std::vector<docseek::Hit> hits;
    ASSERT_NO_THROW(hits = searcher.searchQuestion(q, 20));
    (void)hits;
}

TEST(HybridLongQueryR2, SearchQuestionRecallsDocWithSomeTerms) {
    std::string dir = makeUniqueDir("hybrid_longquery_recall");
    docseek::Database db = docseek::Database::open(dir + "/x.db");

    db.upsert(dir + "/doc1.md", "苹果检索文档",
              "本文介绍苹果检索与全文索引的基础知识。", 100, 64);
    db.upsert(dir + "/doc2.md", "无关文档",
              "这是一篇与主题无关的内容。", 100, 64);

    docseek::Searcher searcher(db);

    std::string q = longQuery();
    std::vector<docseek::Hit> hits;
    ASSERT_NO_THROW(hits = searcher.searchQuestion(q, 20));

    bool found = false;
    for (const auto& h : hits) {
        if (h.path.find("doc1.md") != std::string::npos) {
            found = true;
            break;
        }
    }
    EXPECT_TRUE(found);

    auto start = std::chrono::steady_clock::now();
    std::vector<docseek::Hit> timed;
    ASSERT_NO_THROW(timed = searcher.search(q, 20));
    auto end = std::chrono::steady_clock::now();
    double secs = std::chrono::duration<double>(end - start).count();
    EXPECT_LT(secs, 5.0);
    (void)timed;
}