#pragma once

#include <vector>

#include "docseek/database.h"
#include "docseek/passage_ranker.h"
#include "docseek/searcher.h"

namespace docseek {

// 定位选项。
struct LocateOptions {
    int limit = 5;       // 最终返回段落数
    int recallDocs = 10; // 召回文档数
};

// 自然语言定位器：解析查询 -> 检索文档 -> 段落级重排。
class Locator {
public:
    Locator(Database& db, Searcher& searcher);

    std::vector<Passage> locate(const std::string& rawQuery,
                                const LocateOptions& opts = LocateOptions{});

private:
    Database& db_;
    Searcher& searcher_;
};

}  // namespace docseek
