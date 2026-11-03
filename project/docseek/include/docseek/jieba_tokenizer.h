#pragma once

#include <sqlite3.h>

#include <string>

#include "cppjieba/Jieba.hpp"

namespace docseek {

// 在给定的数据库连接上注册名为 "jieba" 的 FTS5 自定义分词器。
//
// 使用 sqlite3_fts5_api_from_db() 获取 fts5_api，并调用 xCreateTokenizer_v2。
// 分词器内部使用进程级单例的 cppjieba::Jieba（词典来自 resolveDictDir()）。
//
// 若注册失败返回 SQLITE_ERROR，成功返回 SQLITE_OK。
//
// 注意：本函数要求连接已启用 FTS5。
int registerJiebaTokenizer(sqlite3* db);

// 返回进程级只读 Jieba 单例（CutForSearch 并发只读安全）；词典初始化失败返回 nullptr。
const cppjieba::Jieba* jiebaInstance();
// 词典初始化失败时的错误信息；成功返回空串。
std::string jiebaInitError();

}  // namespace docseek
