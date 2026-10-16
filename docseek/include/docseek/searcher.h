#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "docseek/database.h"

namespace docseek {

// Hit 定义见 docseek/database.h（score 越大越相关）。

// 混合检索权重（可配置）。
struct SearchWeights {
    double titleBoost = 1.0;
    double phraseBoost = 2.0;
};

class Searcher {
public:
    explicit Searcher(Database& db);
    explicit Searcher(Database& db, SearchWeights weights);

    // 设置检索权重。
    void setWeights(SearchWeights weights);

    // 读取当前检索权重。
    SearchWeights weights() const;

    // 混合检索 v2（纯词法，无模型、无 GPU，权重可配置）：
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
    SearchWeights weights_;
};


}  // namespace docseek
