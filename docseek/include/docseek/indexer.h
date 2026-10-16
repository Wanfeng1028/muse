#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_set>
#include <vector>

namespace docseek {

class Database;

// 索引选项：扩展名白名单、单文件大小上限、是否跟随符号链接
struct IndexOptions {
    std::vector<std::string> extensions = {".txt", ".md", ".markdown", ".text", ".html", ".htm"};
    int64_t maxFileBytes = 5 * 1024 * 1024;
    bool followSymlinks = false;
};

// 索引统计：扫描、新增、更新、未变、删除、跳过数量及错误信息
struct IndexStats {
    size_t scanned = 0;
    size_t added = 0;
    size_t updated = 0;
    size_t unchanged = 0;
    size_t removed = 0;
    size_t skipped = 0;
    std::vector<std::string> errors;
};

// 索引器：遍历路径并将文本文件写入数据库
class Indexer {
public:
    // 构造索引器，绑定数据库并接收索引选项
    Indexer(Database& db, IndexOptions opts = {});

    // 索引给定根路径（文件或目录），返回本次索引统计
    IndexStats indexPaths(const std::vector<std::string>& roots);

    // 删除磁盘上已不存在的文档记录，返回删除条数
    size_t pruneMissing();

private:
    void indexOneFile(const std::string& path, IndexStats& st, std::unordered_set<std::string>& seen);

    Database& db_;
    IndexOptions opts_;
};

}  // namespace docseek
