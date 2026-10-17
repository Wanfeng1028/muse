#include "docseek/query_parser.h"

#include <algorithm>
#include <cctype>
#include <string>
#include <unordered_set>
#include <vector>

#include "docseek/jieba_tokenizer.h"

namespace docseek {
namespace {

// 判断是否为 ASCII 纯符号 token（无字母数字）。
bool isAsciiSymbolOnly(const std::string& s) {
    if (s.empty()) return false;
    for (unsigned char c : s) {
        if (c >= 0x80) return false;  // 含非 ASCII，不算纯符号
        if (std::isalnum(c)) return false;
    }
    return true;
}

// 判断是否为纯 ASCII 字母数字（用于 ASCII token 长度判断）。
bool isAsciiWord(const std::string& s) {
    if (s.empty()) return false;
    for (unsigned char c : s) {
        if (c >= 0x80) return false;
        if (!std::isalnum(c) && c != '_' && c != '-') return false;
    }
    return true;
}

// 单字中文停用词。
const std::unordered_set<std::string>& singleCharStopwords() {
    static const std::unordered_set<std::string> kSet = {
        "的", "了", "在", "是", "有", "和", "与", "或", "个", "上", "下", "中",
        "之", "为", "于", "由", "把", "被", "给", "对", "就", "都", "也", "还",
        "要", "会", "可", "以", "及"};
    return kSet;
}

// 计算 UTF-8 码点数（非法字节按 1 推进）。
int countUtf8Codepoints(const std::string& s) {
    int n = 0;
    size_t i = 0;
    while (i < s.size()) {
        unsigned char c = static_cast<unsigned char>(s[i]);
        size_t step = 1;
        if (c >= 0xF0 && c <= 0xF7) {
            step = 4;
        } else if (c >= 0xE0 && c <= 0xEF) {
            step = 3;
        } else if (c >= 0xC0 && c <= 0xDF) {
            step = 2;
        }
        i += step;
        ++n;
    }
    return n;
}

// 判断字符串是否为单个中文码点（>=0x80 且码点数为 1）。
bool isSingleCjk(const std::string& s) {
    if (s.empty()) return false;
    unsigned char c = static_cast<unsigned char>(s[0]);
    if (c < 0x80) return false;
    return countUtf8Codepoints(s) == 1;
}

// 判断是否含至少一个中文字符（>=0x80 字节）。
bool hasNonAscii(const std::string& s) {
    for (unsigned char c : s) {
        if (c >= 0x80) return true;
    }
    return false;
}

// 去重保序 push。
void pushUnique(std::vector<std::string>& v, std::unordered_set<std::string>& seen,
                const std::string& s) {
    if (s.empty()) return;
    if (seen.insert(s).second) v.push_back(s);
}

// 压缩空白：多个空白合并为一个，去首尾空白。
std::string squeezeWhitespace(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    bool inSpace = false;
    for (unsigned char c : s) {
        bool isSpace = (c == ' ' || c == '\t' || c == '\n' || c == '\r' ||
                        c == '\f' || c == '\v');
        if (isSpace) {
            inSpace = true;
        } else {
            if (inSpace && !out.empty()) out.push_back(' ');
            inSpace = false;
            out.push_back(static_cast<char>(c));
        }
    }
    return out;
}

// 抽取引号短语：支持 "..."、「...」、“...” 三种。返回移除短语后的文本。
void extractPhrases(const std::string& in, std::vector<std::string>& phrases,
                    std::string& rest) {
    // 配对定界符（UTF-8 字节序列）。
    struct Pair {
        std::string open;
        std::string close;
    };
    static const Pair kPairs[] = {
        {"\"", "\""},
        {"\xE3\x80\x8C", "\xE3\x80\x8D"},  // 「 」
        {"\xE2\x80\x9C", "\xE2\x80\x9D"},  // “ ”
    };

    rest.clear();
    std::unordered_set<std::string> seen;
    size_t i = 0;
    const size_t n = in.size();
    while (i < n) {
        bool matched = false;
        for (const auto& p : kPairs) {
            if (i + p.open.size() <= n &&
                in.compare(i, p.open.size(), p.open) == 0) {
                // 找闭合定界符。
                size_t closePos = in.find(p.close, i + p.open.size());
                if (closePos != std::string::npos) {
                    std::string phrase =
                        in.substr(i + p.open.size(), closePos - i - p.open.size());
                    // 压缩空白后加入。
                    std::string sq = squeezeWhitespace(phrase);
                    pushUnique(phrases, seen, sq);
                    i = closePos + p.close.size();
                    matched = true;
                    break;
                }
            }
        }
        if (!matched) {
            rest.push_back(in[i]);
            ++i;
        }
    }
}

// 按顺序整体替换为空的疑问/语气词表。
// 注意：单字 "的"、"了" 已由 singleCharStopwords 在分词阶段过滤，
// 此处不再列入，避免把名词短语（如"密码的规则"）切碎。
// 表按字节长度严格降序排列，消除 "在哪"/"在哪里"、"哪段"/"哪一段" 等
// 前后缀重叠对遍历顺序的依赖（先长后短，短词不会误吃长词前缀）。
const std::vector<std::string>& fillerWords() {
    static const std::vector<std::string> kWords = {
        "帮我找一下", "哪一篇", "有没有", "在哪里", "哪一段", "哪一句",
        "帮我找", "找一下", "是什么", "为什么", "哪段", "哪句", "哪个",
        "哪些", "怎么", "如何", "怎样", "多少", "哪篇", "请问", "在哪",
        "为啥", "一下", "吗", "呢", "啊", "吧"};
    return kWords;
}

// 替换所有出现的 from 为 ""。
std::string eraseAll(const std::string& s, const std::string& from) {
    if (from.empty()) return s;
    std::string out;
    out.reserve(s.size());
    size_t pos = 0;
    while (pos < s.size()) {
        size_t found = s.find(from, pos);
        if (found == std::string::npos) {
            out.append(s, pos, std::string::npos);
            break;
        }
        out.append(s, pos, found - pos);
        pos = found + from.size();
    }
    return out;
}

// 尾部谓语/动词残留剥离表（长度降序）。
// 只含谓语/动词类，不含名词主题词（"备份"/"方法"/"政策"/"规则"/"方案"/
// "权益"/"流程"/"步骤" 等名词一律保留）。
// 剥离仅作用于字符串尾部，循环直到稳定，避免误伤串中间的名词。
const std::vector<std::string>& trailingPredicates() {
    static const std::vector<std::string> kWords = {
        "写在哪", "写在", "说明", "介绍", "申请", "开具", "重置", "阐述", "写"};
    return kWords;
}

// 反复剥掉 rest 尾部的谓语/动词残留，直到稳定。
// 按长度降序尝试；每次命中一个后缀即剥掉并重新尝试。
std::string stripTrailingPredicates(const std::string& s) {
    std::string out = s;
    bool changed = true;
    while (changed) {
        changed = false;
        for (const auto& w : trailingPredicates()) {
            if (w.empty()) continue;
            if (out.size() >= w.size() &&
                out.compare(out.size() - w.size(), w.size(), w) == 0) {
                out.resize(out.size() - w.size());
                changed = true;
                break;
            }
        }
    }
    return out;
}

// passageIntent 触发词。
bool detectPassageIntent(const std::string& raw) {
    static const std::vector<std::string> kTriggers = {
        "哪段", "哪句", "哪一句", "哪一段", "原文", "定位", "具体", "怎么说", "写了什么"};
    for (const auto& t : kTriggers) {
        if (raw.find(t) != std::string::npos) return true;
    }
    return false;
}

}  // namespace

// 单字中文停用词判断（供查询展开等复用）。
bool isSingleCharStopword(const std::string& w) {
    return singleCharStopwords().count(w) > 0;
}

ParsedQuery parseNaturalQuery(const std::string& raw) {
    ParsedQuery pq;

    // 空输入判断。
    std::string trimmed = squeezeWhitespace(raw);
    if (trimmed.empty()) {
        return pq;
    }

    pq.passageIntent = detectPassageIntent(raw);

    // 1. 抽取引号短语。
    std::string rest;
    extractPhrases(raw, pq.phrases, rest);

    // 2. 删除疑问/语气词（按表顺序，长度降序）。
    for (const auto& w : fillerWords()) {
        rest = eraseAll(rest, w);
    }
    rest = squeezeWhitespace(rest);

    // 2.5 尾部谓语/动词残留剥离（只剥尾部，保护串中间名词）。
    // 处理 "写在"/"写"/"说明"/"申请" 等问句谓语，避免其进入 keywords。
    rest = stripTrailingPredicates(rest);
    rest = squeezeWhitespace(rest);

    // 3. jieba 分词 + 过滤。
    std::unordered_set<std::string> seen;
    if (!rest.empty()) {
        const cppjieba::Jieba* jieba = jiebaInstance();
        if (jieba != nullptr) {
            std::vector<std::string> words;
            jieba->CutForSearch(rest, words);
            for (const auto& w : words) {
                if (w.empty()) continue;
                if (!hasNonAscii(w)) {
                    // ASCII token。
                    if (isAsciiSymbolOnly(w)) continue;  // 纯符号丢弃
                    if (!isAsciiWord(w)) continue;       // 含符号丢弃
                    if (w.size() < 2) continue;          // 长度 >= 2
                    pushUnique(pq.keywords, seen, w);
                } else {
                    // 中文（或含非 ASCII）token。
                    if (isSingleCjk(w) &&
                        singleCharStopwords().count(w) > 0) {
                        continue;
                    }
                    pushUnique(pq.keywords, seen, w);
                }
            }
        }
    }

    // 4. 兜底：keywords 与 phrases 皆空，按空白切分原 raw。
    if (pq.keywords.empty() && pq.phrases.empty()) {
        std::string s = squeezeWhitespace(raw);
        size_t pos = 0;
        while (pos < s.size()) {
            size_t sp = s.find(' ', pos);
            std::string tok =
                (sp == std::string::npos) ? s.substr(pos) : s.substr(pos, sp - pos);
            if (!tok.empty()) pushUnique(pq.keywords, seen, tok);
            if (sp == std::string::npos) break;
            pos = sp + 1;
        }
    }

    return pq;
}

}  // namespace docseek
