#include <gtest/gtest.h>
#include <filesystem>
#include <string>
#include <vector>
#include <unistd.h>
#include "docseek/database.h"
#include "docseek/jieba_tokenizer.h"
#include "docseek/searcher.h"

TEST(SectionHeadingV037, ExactSectionHeadingRanksFirst) {
    std::filesystem::path temp_dir = std::filesystem::current_path() / "test-tmp" / ("section_v037_1_" + std::to_string(getpid()));
    std::filesystem::remove_all(temp_dir);
    std::filesystem::create_directories(temp_dir);

    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr);

    docseek::Database db = docseek::Database::open((temp_dir / "idx.db").string());

    // Document H with exact heading "## 追肥"
    std::string h_path = (temp_dir / "H.txt").string();
    db.upsert(h_path, "阳台种菜笔记甲", "## 追肥\n追肥", 100, 20);

    // Document P without heading, mentions "追肥" twice
    std::string p_path = (temp_dir / "P.txt").string();
    db.upsert(p_path, "阳台种菜笔记乙", "一些无关内容。追肥 追肥", 100, 20);

    docseek::Searcher s(db);
    auto hits = s.search("追肥", 10);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(std::filesystem::path(hits[0].path).filename().string(), "H.txt");
}

TEST(SectionHeadingV037, PartialHeadingNoGain) {
    std::filesystem::path temp_dir = std::filesystem::current_path() / "test-tmp" / ("section_v037_2_" + std::to_string(getpid()));
    std::filesystem::remove_all(temp_dir);
    std::filesystem::create_directories(temp_dir);

    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr);

    docseek::Database db = docseek::Database::open((temp_dir / "idx.db").string());

    // Document A has heading "追肥方法" (contains "追肥" but not exact)
    std::string a_path = (temp_dir / "A.txt").string();
    db.upsert(a_path, "阳台种菜笔记丙", "# 追肥方法\n追肥", 100, 20);

    // Document B has no heading, mentions "追肥" twice
    std::string b_path = (temp_dir / "B.txt").string();
    db.upsert(b_path, "阳台种菜笔记丁", "追肥 追肥", 100, 20);

    docseek::Searcher s(db);
    auto hits = s.search("追肥", 10);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(std::filesystem::path(hits[0].path).filename().string(), "B.txt");
}

TEST(SectionHeadingV037, TwoExactHeadingsRankFirst) {
    std::filesystem::path temp_dir = std::filesystem::current_path() / "test-tmp" / ("section_v037_3_" + std::to_string(getpid()));
    std::filesystem::remove_all(temp_dir);
    std::filesystem::create_directories(temp_dir);

    const cppjieba::Jieba* jieba = docseek::jiebaInstance();
    ASSERT_NE(jieba, nullptr);

    docseek::Database db = docseek::Database::open((temp_dir / "idx.db").string());

    // Document H contains both "## 追肥" and "## 施肥" headings
    std::string h_path = (temp_dir / "H.txt").string();
    db.upsert(h_path, "阳台种菜笔记甲", "## 追肥\n## 施肥\n一些其他内容", 100, 20);

    // Document P contains only one exact heading "## 追肥", but many mentions of both words in body
    std::string p_path = (temp_dir / "P.txt").string();
    std::string p_content = "## 追肥\n";
    p_content += "阳台种菜需要注意光照和通风，每天检查土壤湿度，适时浇水，保持盆土疏松，定期清理枯叶，观察植株生长情况，及时调整摆放位置，避免强光直射，做好防虫措施，记录每次浇水的时间和用量。";
    p_content += "追肥 施肥";
    db.upsert(p_path, "阳台种菜笔记乙", p_content, 100, 20);

    docseek::Searcher s(db);
    auto hits = s.search("追肥 施肥", 10);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(std::filesystem::path(hits[0].path).filename().string(), "H.txt");
}