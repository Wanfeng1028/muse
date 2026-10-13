#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "docseek/database.h"

namespace docseek {

// Hit 定义见 docseek/database.h（score 越大越相关）。

class Searcher {
public:
    explicit Searcher(Database& db);

    // 混合检索 v1（纯词法，无模型、无 GPU）：
    //   1. 精确 AND（FTS5 隐式 AND）
    //   2. OR 回退（AND 无结果且 token 数 >= 2）
    //   3. 词法重排序（bm25 基础分 + title 加成 + 短语加成）
    std::vector<Hit> search(const std::string& query, int limit);

    // 将查询按空白切分，每个 token 双引号包裹转义，空格连接（FTS5 隐式 AND）。
    static std::string buildMatchQuery(const std::string& query);

    // 将查询按空白切分，每个 token 双引号包裹转义，用 " OR " 连接。
    static std::string buildOrMatchQuery(const std::string& query);

private:
    Database& db_;
};

}  // namespace docseek
