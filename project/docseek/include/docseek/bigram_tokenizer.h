#pragma once
#include <sqlite3.h>
#include <cstdint>
#include <string>
#include <vector>
namespace docseek {
// 注册名为 "bigram" 的 FTS5 自定义分词器；成功返回 SQLITE_OK。
int registerBigramTokenizer(sqlite3* db);
// 查询侧切分：与索引侧一致的 token 序列（去停用词后）。
std::vector<std::string> bigramCutForSearch(const std::string& text);
namespace bigram_detail {
std::vector<uint32_t> decodeUtf8(const std::string& s);  // 非法序列直接丢弃
bool isCjk(uint32_t cp);
bool isAsciiAlnum(uint32_t cp);
bool isCjkStopword(uint32_t cp);  // 单字停用词
std::string encodeUtf8(uint32_t cp);
std::vector<std::string> cutCjkRun(const std::vector<uint32_t>& cps);
}  // namespace bigram_detail
}  // namespace docseek
