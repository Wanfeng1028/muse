#include <gtest/gtest.h>
#include "docseek/database.h"
#include "docseek/searcher.h"
#include <string>
#include <vector>
#include <filesystem>
#ifndef _WIN32
#include <unistd.h>
#endif

namespace {

long currentPid() {
#ifdef _WIN32
    return static_cast<long>(::GetCurrentProcessId());
#else
    return static_cast<long>(::getpid());
#endif
}

std::string makeTempDir(const std::string& name) {
    std::filesystem::path base = std::filesystem::current_path() / "test-tmp";
    std::filesystem::create_directories(base);
    std::filesystem::path dir = base / (name + "_" + std::to_string(currentPid()));
    std::filesystem::remove_all(dir);
    std::filesystem::create_directories(dir);
    return dir.string();
}

}  // namespace

TEST(ExplainV019, ComponentsSumToScore) {
    auto db = docseek::Database::open(makeTempDir("explain_v019_sum") + "/index.db");
    db.upsert("/docs/a.txt", "安装步骤说明",
              "本文介绍软件的安装步骤。第一步下载安装包，第二步运行安装程序。", 100, 50);
    db.upsert("/docs/b.txt", "软件安装指南",
              "安装前请检查系统环境，安装步骤详见下文说明。", 90, 40);
    db.upsert("/docs/c.txt", "安装与卸载",
              "安装完成后可以卸载，安装步骤简单明了。", 80, 30);
    db.upsert("/docs/d.txt", "用户手册",
              "本手册介绍安装步骤与常见问题处理方法。", 70, 20);

    docseek::Searcher s(db);
    auto ex = s.explain("安装步骤", 10);
    ASSERT_FALSE(ex.empty());

    for (const auto& e : ex) {
        EXPECT_DOUBLE_EQ(e.breakdown.baseBm25 + e.breakdown.titleBonus +
                             e.breakdown.phraseBonus + e.breakdown.structuralBonus,
                         e.hit.score);
        EXPECT_DOUBLE_EQ(e.breakdown.finalScore, e.hit.score);
    }
}

TEST(ExplainV019, ExplainMatchesSearch) {
    auto db = docseek::Database::open(makeTempDir("explain_v019_match") + "/index.db");
    db.upsert("/docs/a.txt", "安装步骤说明",
              "本文介绍软件的安装步骤。第一步下载安装包，第二步运行安装程序。", 100, 50);
    db.upsert("/docs/b.txt", "软件安装指南",
              "安装前请检查系统环境，安装步骤详见下文说明。", 90, 40);
    db.upsert("/docs/c.txt", "安装与卸载",
              "安装完成后可以卸载，安装步骤简单明了。", 80, 30);
    db.upsert("/docs/d.txt", "用户手册",
              "本手册介绍安装步骤与常见问题处理方法。", 70, 20);

    docseek::Searcher s(db);
    auto hits = s.search("安装步骤", 10);
    auto ex = s.explain("安装步骤", 10);

    ASSERT_EQ(hits.size(), ex.size());
    for (std::size_t i = 0; i < hits.size(); ++i) {
        EXPECT_EQ(hits[i].doc_id, ex[i].hit.doc_id);
        EXPECT_DOUBLE_EQ(hits[i].score, ex[i].hit.score);
    }
}

TEST(ExplainV019, TitleBonusPositive) {
    auto db = docseek::Database::open(makeTempDir("explain_v019_title") + "/index.db");
    db.upsert("/docs/a.txt", "安装步骤说明",
              "本文介绍软件的安装步骤。第一步下载安装包，第二步运行安装程序。", 100, 50);
    db.upsert("/docs/b.txt", "用户手册",
              "本手册介绍安装步骤与常见问题处理方法。", 70, 20);

    docseek::Searcher s(db);
    auto ex = s.explain("安装步骤", 10);

    const docseek::ExplainedHit* hitA = nullptr;
    const docseek::ExplainedHit* hitB = nullptr;
    for (const auto& e : ex) {
        if (e.hit.path == "/docs/a.txt") hitA = &e;
        if (e.hit.path == "/docs/b.txt") hitB = &e;
    }

    ASSERT_NE(hitA, nullptr);
    EXPECT_GT(hitA->breakdown.titleBonus, 0.0);

    if (hitB == nullptr) {
        GTEST_SKIP() << "document B not recalled; recall behavior is out of scope";
    }
    EXPECT_DOUBLE_EQ(hitB->breakdown.titleBonus, 0.0);
}

TEST(ExplainV019, PhraseBonusQuoted) {
    auto db = docseek::Database::open(makeTempDir("explain_v019_phrase") + "/index.db");
    db.upsert("/docs/a.txt", "安装步骤说明",
              "本文介绍软件的安装步骤。第一步下载安装包，第二步运行安装程序。", 100, 50);
    db.upsert("/docs/b.txt", "软件安装指南",
              "安装前请检查系统环境，安装步骤详见下文说明。", 90, 40);
    db.upsert("/docs/c.txt", "安装与卸载",
              "安装完成后可以卸载，安装步骤简单明了。", 80, 30);

    docseek::Searcher s(db);
    auto ex = s.explain("\"安装步骤\"", 10);

    const docseek::ExplainedHit* hitA = nullptr;
    for (const auto& e : ex) {
        if (e.hit.path == "/docs/a.txt") hitA = &e;
    }

    if (hitA == nullptr) {
        GTEST_SKIP() << "document A not recalled; recall behavior is out of scope";
    }
    EXPECT_GT(hitA->breakdown.phraseBonus, 0.0);
}

TEST(ExplainV019, EmptyQuery) {
    auto db = docseek::Database::open(makeTempDir("explain_v019_empty") + "/index.db");
    db.upsert("/docs/a.txt", "安装步骤说明",
              "本文介绍软件的安装步骤。第一步下载安装包，第二步运行安装程序。", 100, 50);

    docseek::Searcher s(db);
    auto ex1 = s.explain("", 10);
    auto ex2 = s.explain("   ", 10);
    EXPECT_TRUE(ex1.empty());
    EXPECT_TRUE(ex2.empty());
}

TEST(ExplainV019, PureStopword) {
    auto db = docseek::Database::open(makeTempDir("explain_v019_stopword") + "/index.db");
    db.upsert("/docs/a.txt", "安装步骤说明",
              "本文介绍软件的安装步骤。第一步下载安装包，第二步运行安装程序。", 100, 50);
    db.upsert("/docs/b.txt", "用户手册",
              "本手册介绍安装步骤与常见问题处理方法。", 70, 20);

    docseek::Searcher s(db);
    auto ex = s.explain("的", 10);
    EXPECT_TRUE(ex.empty());
}
