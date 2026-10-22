#pragma once

#include <string>
#include <vector>

namespace docseek {

// R3'（行首命中）精度收紧：判定行首命中是否为"条目式"强信号。
bool isEntryLikeLineStart(const std::string& strippedLine, bool hadListMarker,
                          size_t queryByteLen);

// R6'（行首命中 + 数字）精度收紧：判定行内数字与查询语义是否一致。
bool digitConsistentWithQuery(const std::string& strippedLine,
                              const std::string& query);

// R1（标题行加成）精度收紧：标题须与查询词强对应才给 1.5。
double r1StartsWithBonusForToken(const std::vector<std::string>& headings,
                                 const std::string& token);

}  // namespace docseek
