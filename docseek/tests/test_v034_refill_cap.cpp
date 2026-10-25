#include <gtest/gtest.h>
#include <filesystem>
#include <string>
#include <vector>
#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "docseek/searcher.h"

namespace docseek { namespace {

static long currentPid() { return static_cast<long>(::getpid()); }

std::string makeTempDir(const std::string& name) {
    std::filesystem::path base = std::filesystem::current_path() / "test-tmp";
    std::filesystem::create_directories(base);
    std::filesystem::path dir = base / (name + "_" + std::to_string(currentPid()));
    std::filesystem::remove_all(dir);
    std::filesystem::create_directories(dir);
    return dir.string();
}

void requireJiebaReady() {
    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr) << "jieba init error: " << docseek::jiebaInitError();
}

std::string basenameOf(const std::string& p) {
    return std::filesystem::path(p).filename().string();
}

} }

using namespace docseek;

TEST(RefillCapV034, RefillCapRanksAndHitFirst) {
    requireJiebaReady();
    std::string dir = makeTempDir("refill_cap_v034_1");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());

    std::string path_and = (std::filesystem::path(dir) / "doc_and.txt").string();
    std::string path_refill = (std::filesystem::path(dir) / "doc_refill.txt").string();

    db.upsert(path_and, "and", "三色激光投影仪色彩很好。激光光源亮度高寿命长。三色激光色域覆盖广。", 100, 20);
    db.upsert(path_refill, "refill", "第三优先级看亮度。白色字幕边缘有散斑。激光亮度高但可能有散斑。", 100, 20);

    Searcher s(db);
    auto hits = s.search("三色激光散斑", 10);

    ASSERT_GE(hits.size(), 2u);
    EXPECT_EQ(basenameOf(hits[0].path), "doc_and.txt");

    bool refill_found = false;
    for (const auto& h : hits) {
        if (basenameOf(h.path) == "doc_refill.txt") {
            refill_found = true;
            break;
        }
    }
    EXPECT_TRUE(refill_found);
}

TEST(RefillCapV034, RefillHitStillPresent) {
    requireJiebaReady();
    std::string dir = makeTempDir("refill_cap_v034_2");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());

    std::string path_and = (std::filesystem::path(dir) / "doc_and.txt").string();
    std::string path_refill = (std::filesystem::path(dir) / "doc_refill.txt").string();

    db.upsert(path_and, "and", "三色激光投影仪色彩很好。激光光源亮度高寿命长。三色激光色域覆盖广。", 100, 20);
    db.upsert(path_refill, "refill", "第三优先级看亮度。白色字幕边缘有散斑。激光亮度高但可能有散斑。", 100, 20);

    Searcher s(db);
    auto hits = s.search("三色激光散斑", 10);

    bool refill_found = false;
    for (const auto& h : hits) {
        if (basenameOf(h.path) == "doc_refill.txt") {
            refill_found = true;
            break;
        }
    }
    EXPECT_TRUE(refill_found);
}

TEST(RefillCapV034, AndOnlyQueryUnaffected) {
    requireJiebaReady();
    std::string dir = makeTempDir("refill_cap_v034_3");
    Database db = Database::open((std::filesystem::path(dir) / "idx.db").string());

    std::string path_and = (std::filesystem::path(dir) / "doc_and.txt").string();
    std::string path_refill = (std::filesystem::path(dir) / "doc_refill.txt").string();

    db.upsert(path_and, "and", "三色激光投影仪色彩很好。激光光源亮度高寿命长。三色激光色域覆盖广。", 100, 20);
    db.upsert(path_refill, "refill", "第三优先级看亮度。白色字幕边缘有散斑。激光亮度高但可能有散斑。", 100, 20);

    Searcher s(db);
    auto hits = s.search("三色激光", 10);

    ASSERT_GE(hits.size(), 1u);
    EXPECT_EQ(basenameOf(hits[0].path), "doc_and.txt");
}