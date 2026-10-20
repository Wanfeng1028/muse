#include <gtest/gtest.h>
#include <filesystem>
#include <string>
#include "docseek/database.h"
#include "docseek/searcher.h"
#include "docseek/locator.h"

using namespace docseek;
namespace fs = std::filesystem;

TEST(DocFrequency, EmptyTerm_Zero) {
    auto dir = fs::temp_directory_path() / "docseek_df_empty";
    Database db = Database::open((dir / "test.db").string());
    EXPECT_EQ(db.docFrequency(""), 0);
    std::error_code ec;
    fs::remove_all(dir, ec);
}

TEST(DocFrequency, UnknownTerm_Zero) {
    auto dir = fs::temp_directory_path() / "docseek_df_unknown";
    Database db = Database::open((dir / "test.db").string());
    db.upsert("doc1.txt", "标题", "这是一篇中文文档，用于测试不存在的词。", 1000, 100);
    EXPECT_EQ(db.docFrequency("不存在的词xyz"), 0);
    std::error_code ec;
    fs::remove_all(dir, ec);
}

TEST(DocFrequency, SingleDoc_One) {
    auto dir = fs::temp_directory_path() / "docseek_df_single";
    Database db = Database::open((dir / "test.db").string());
    db.upsert("doc1.txt", "标题", "今天需要进行数据备份操作。", 1000, 100);
    EXPECT_EQ(db.docFrequency("备份"), 1);
    std::error_code ec;
    fs::remove_all(dir, ec);
}

TEST(DocFrequency, MultiDoc_Count) {
    auto dir = fs::temp_directory_path() / "docseek_df_multi";
    Database db = Database::open((dir / "test.db").string());
    db.upsert("doc1.txt", "标题1", "今天需要进行数据备份操作。", 1000, 100);
    db.upsert("doc2.txt", "标题2", "备份是重要的工作。", 1000, 100);
    db.upsert("doc3.txt", "标题3", "这是一篇不包含目标词的文档。", 1000, 100);
    EXPECT_EQ(db.docFrequency("备份"), 2);
    std::error_code ec;
    fs::remove_all(dir, ec);
}

TEST(DocFrequency, UserIsolation) {
    auto dir = fs::temp_directory_path() / "docseek_df_user";
    Database db = Database::open((dir / "test.db").string());
    db.upsert("doc1.txt", "标题1", "今天需要进行数据备份操作。", 1000, 100);
    db.upsert("doc2.txt", "标题2", "alice 也需要备份。", 1000, 100, "alice");
    EXPECT_EQ(db.docFrequency("备份"), 1);
    EXPECT_EQ(db.docFrequency("备份", "alice"), 1);
    EXPECT_EQ(db.docCount(), 1);
    EXPECT_EQ(db.docCount("alice"), 1);
    std::error_code ec;
    fs::remove_all(dir, ec);
}

TEST(DocFrequency, SingleCharTerm_NotIndexed) {
    auto dir = fs::temp_directory_path() / "docseek_df_single2";
    Database db = Database::open((dir / "test.db").string());
    db.upsert("doc1.txt", "标题", "今天有云", 1000, 100);
    EXPECT_EQ(db.docFrequency("云"), 0);
    std::error_code ec;
    fs::remove_all(dir, ec);
}

TEST(DocFrequency, TitleOnly_Counts) {
    auto dir = fs::temp_directory_path() / "docseek_df_title";
    Database db = Database::open((dir / "test.db").string());
    db.upsert("doc2.txt", "备份指南", "今天天气不错", 1000, 100);
    EXPECT_EQ(db.docFrequency("备份"), 1);
    std::error_code ec;
    fs::remove_all(dir, ec);
}

TEST(DocFrequency, DocFrequency_English) {
    auto dir = fs::temp_directory_path() / "docseek_df_english";
    Database db = Database::open((dir / "test.db").string());
    db.upsert("doc3.txt", "Backup Guide", "This is a backup document", 1000, 100);
    EXPECT_EQ(db.docFrequency("backup"), 1);
    std::error_code ec;
    fs::remove_all(dir, ec);
}

TEST(DocFrequency, EmptyIndex_NoCrash) {
    auto dir = fs::temp_directory_path() / "docseek_df_empty";
    Database db = Database::open((dir / "test.db").string());
    EXPECT_EQ(db.docFrequency("备份"), 0);
    EXPECT_EQ(db.docCount(), 0);
    std::error_code ec;
    fs::remove_all(dir, ec);
}

TEST(DocFrequency, Locator_IdfWiring_EndToEnd) {
    auto dir = fs::temp_directory_path() / "docseek_df_locator";
    Database db = Database::open((dir / "test.db").string());
    db.upsert("a.md", "数据备份指南", "备份很重要。每天备份一次。增量备份每周做。", 1000, 100);
    db.upsert("b.md", "随笔", "今天天气不错，适合出门。建议大家多喝水。", 1000, 100);
    Searcher searcher(db);
    Locator locator(db, searcher);
    LocateOptions opts;
    opts.limit = 5;
    auto res = locator.locate("数据备份多久做一次比较好", opts);
    EXPECT_FALSE(res.empty());
    std::error_code ec;
    fs::remove_all(dir, ec);
}
