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

struct ScoreBreakdown {
    double baseBm25 = 0.0;
    double titleBonus = 0.0;
    double phraseBonus = 0.0;
    double structuralBonus = 0.0;
    double finalScore = 0.0;
};
struct ExplainedHit {
    Hit hit;
    ScoreBreakdown breakdown;
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

    // 问句召回放宽版检索：重排逻辑与 search() 逐行等价，
    // 区别仅在召回阶段——AND 结果与 OR 结果取并集（按 doc_id 去重，冲突保留 AND 版本），
    // tokens.size() >= 2 时 OR 查询恒执行（不论 AND 是否为空）。
    // 仅供 Locator 对问句调用；search() 本体行为不变。
    std::vector<Hit> searchQuestion(const std::string& query, int limit);

    std::vector<ExplainedHit> explain(const std::string& query, int limit);

    // 将查询按空白切分，每个 token 双引号包裹转义，空格连接（FTS5 隐式 AND）。
    static std::string buildMatchQuery(const std::string& query);

    // 将查询按空白切分，每个 token 双引号包裹转义，用 " OR " 连接。
    static std::string buildOrMatchQuery(const std::string& query);

private:
    std::vector<Hit> searchDetailed(const std::string& query, int limit, std::vector<ScoreBreakdown>* breakdowns);
    Database& db_;
    SearchWeights weights_;
};


}  // namespace docseek
