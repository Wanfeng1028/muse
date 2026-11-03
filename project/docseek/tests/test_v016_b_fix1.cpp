// tests/test_v016_b_fix1.cpp
// 验证查询中疑问词/填充词被剥离后仍能正确命中，并单测 stripFillerWords 的剥离行为。

#include <gtest/gtest.h>
#include <filesystem>
#include <string>
#include <vector>
#include <unistd.h>
#include "docseek/database.h"
#include "docseek/query_parser.h"
#include "docseek/searcher.h"

namespace {

std::string makeTempDbPath() {
    const std::string dir = "/tmp/docseek_test_b_fix1_" + std::to_string(::getpid());
    std::filesystem::create_directories(dir);
    return dir + "/test.db";
}

}  // namespace

// 红：若疑问词"怎么办"未被剥离，查询词会变成"怕水""怎么办"的隐式 AND，
// doc A 正文并不含"怎么办"字面，命中为空，hits[0] 取不到。
// 绿：stripFillerWords 剥离"怎么办"后查询词为"怕水"，
// doc A 命中且唯一（doc B 不含"怕水"），hits[0].path 为 /b1/a.html。
TEST(BFix1, InterrogativeWordStrippedInSearch) {
    const std::string dbPath = makeTempDbPath();
    {
        auto db = docseek::Database::open(dbPath);
        db.upsert("/b1/a.html", "零基础学游泳：从怕水到敢下水", "先解决怕水，再谈动作。怕水的人最怕的是脚踩不到底的感觉。", 100, 20);
        db.upsert("/b1/b.html", "滑板轴承保养", "轴承异响怎么办？先清洁再上油。如果还有异响怎么办，那就换新的。", 100, 20);
        docseek::Searcher s(db);
        auto hits = s.search("怕水怎么办", 10);
        ASSERT_FALSE(hits.empty());
        EXPECT_EQ(hits[0].path, "/b1/a.html");
        EXPECT_EQ(hits.size(), 1u);
    }
    std::filesystem::remove_all(std::filesystem::path(dbPath).parent_path());
}

// 单测填充词剥离：疑问词/语气词被去掉，非填充词原样保留。
TEST(BFix1, StripFillerWordsUnit) {
    EXPECT_EQ(docseek::stripFillerWords("怕水怎么办"), "怕水");
    EXPECT_EQ(docseek::stripFillerWords("什么时候换机油"), "换机油");
    EXPECT_EQ(docseek::stripFillerWords("不建议熬夜"), "不建议熬夜");
    EXPECT_EQ(docseek::stripFillerWords(""), "");
}
