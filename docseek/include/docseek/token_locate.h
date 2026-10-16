
#pragma once

#include <set>
#include <string>
#include <utility>
#include <vector>

namespace docseek {

// 一个已成功认领的词及其在 text 中的起始字节偏移。
struct LocatedToken {
    std::string word;
    size_t byteOffset;
};

// 对 words 中每个非空词，在 text 中做 occurrence 扫描：
//   - 使用 std::string::find(w, p + 1) 按字节推进，允许重叠出现；
//   - 取第一个尚未被 (词, 起始字节) 认领的位置；
//   - 成功则把 (词, 位置) 插入 claimed，并按 words 顺序追加到返回 vector；
//   - 定位失败的词跳过不返回，由调用方决定回退或退化处理。
//
// claimed 由调用方传入传出，允许多次调用共享同一集合（例如 tokenizer 的
// 码点回退路径）。循环推进严格递增，天然有界，不可能死循环。
// 空 text 或空 words 返回空 vector。
std::vector<LocatedToken> claimTokenPositions(
    const std::string& text,
    const std::vector<std::string>& words,
    std::set<std::pair<std::string, size_t>>& claimed);

}  // namespace docseek
