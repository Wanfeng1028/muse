#pragma once
// 搜索器：将用户查询转换为 FTS5 MATCH 查询并检索数据库。
#include <string>
#include <vector>
#include "docseek/database.h"

namespace docseek {

class Searcher {
public:
    explicit Searcher(Database& db);

    std::vector<Hit> search(const std::string& query, int limit);

    static std::string buildMatchQuery(const std::string& query);

private:
    Database& db_;
};

}  // namespace docseek
