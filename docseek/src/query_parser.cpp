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

// 判断是否为纯标点 token（含全角标点，如"，""。""？"等）。
// 用于丢弃分词后残留的纯标点 token。
bool isPunctuationOnly(const std::string& s) {
    if (s.empty()) return false;
    size_t i = 0;
    while (i < s.size()) {
        unsigned char c = static_cast<unsigned char>(s[i]);
        if (c < 0x80) {
            if (std::isalnum(c)) return false;
            ++i;
            continue;
        }
        // UTF-8 多字节：解析码点，判断是否属于 Unicode 标点区。
        int len = 1;
        unsigned int cp = 0;
        if ((c & 0xE0) == 0xC0) { len = 2; cp = c & 0x1F; }
        else if ((c & 0xF0) == 0xE0) { len = 3; cp = c & 0x0F; }
        else if ((c & 0xF8) == 0xF0) { len = 4; cp = c & 0x07; }
        else { return false; }  // 非法首字节，按非标点处理
        if (i + len > s.size()) return false;
        for (int k = 1; k < len; ++k) {
            unsigned char cc = static_cast<unsigned char>(s[i + k]);
            if ((cc & 0xC0) != 0x80) return false;
            cp = (cp << 6) | (cc & 0x3F);
        }
        // 常见 Unicode 标点范围：
        // 0x3000-0x303F CJK 符号与标点（含 。、「」）
        // 0xFF00-0xFFEF 全角/半角形式（含 ，．？！：；）
        // 0x2000-0x206F 常用标点（含 ……、“”‘’）
        bool isPunct = (cp >= 0x3000 && cp <= 0x303F) ||
                       (cp >= 0xFF00 && cp <= 0xFFEF) ||
                       (cp >= 0x2000 && cp <= 0x206F);
        if (!isPunct) return false;
        i += len;
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
// 注：「得」为结构助词/情态动词（"发货得几天"），不承载检索信息，加入本表；
// 实义词如"得到/觉得/值得"由 jieba 整体切出，不会被本表命中。
const std::unordered_set<std::string>& singleCharStopwords() {
    static const std::unordered_set<std::string> kSet = {
        "的", "了", "在", "是", "有", "和", "与", "或", "个", "上", "下", "中",
        "之", "为", "于", "由", "把", "被", "给", "对", "就", "都", "也", "还",
        "要", "会", "可", "以", "及", "得"};
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

// 按顺序整体替换为空的疑问/语气词表。
// 注意：单字 "的"、"了" 已由 singleCharStopwords 在分词阶段过滤，
// 此处不再列入，避免把名词短语（如"密码的规则"）切碎。
// 表按字节长度严格降序排列，消除 "在哪"/"在哪里"、"哪段"/"哪一段" 等
// 前后缀重叠对遍历顺序的依赖（先长后短，短词不会误吃长词前缀）。
// 2026-10-18 补全"知道/什么/什么时候/怎么办/的话/比较"（D 类长问句噪音）；
// "不"字永不入表——否定语义保护（如"不建议"），v08-qa-09d 教训。
const std::vector<std::string>& fillerWords() {
    static const std::vector<std::string> kWords = {
        "帮我找一下", "有没有建议", "我想知道", "想知道", "比较合适", "哪一篇", "有没有",
        "在哪里", "哪一段", "哪一句", "帮我找", "找一下", "是什么", "为什么",
        "什么时候", "怎么办", "哪段", "哪句", "哪个", "哪些", "怎么", "如何",
        "怎样", "多少", "哪篇", "请问", "在哪", "哪儿", "为啥", "一下", "你们",
        "应该", "知道", "什么", "的话", "比较好", "比较", "多高", "区别", "吗", "呢", "啊", "吧", "我",
        "想", "该", "才"};
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

// 替换所有出现的 from 为单个空格（D1 修复：eraseAll 直接删除会把被删词前后
// 的 token 粘成一个新词，如"报班多少钱"删"多少"后变成"报班钱"，FTS5 恒为 0 命中）。
std::string replaceAllWithSpace(const std::string& s, const std::string& from) {
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
        out.push_back(' ');
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

// 方位/时间单字封闭集（封闭语言学类）。
bool isDirectionTimeChar(const std::string& s) {
    // 集合：前 后 上 下 左 右 里 外 内 中（10 个单字）。
    // 实现：static const std::unordered_set<std::string>，count(s) > 0。
    static const std::unordered_set<std::string> kSet = {
        "前", "后", "上", "下", "左", "右", "里", "外", "内", "中"
    };
    return kSet.count(s) > 0;
}

// 取首个 UTF-8 码点子串。
std::string firstCodepoint(const std::string& s) {
    // 空串返回空串；按首字节判定码点长度（1/2/3/4），截取返回；
    // 长度超过 s.size() 时截断到 s.size()。
    if (s.empty()) {
        return std::string();
    }
    unsigned char c = static_cast<unsigned char>(s[0]);
    std::size_t len = 1;
    if ((c & 0x80) == 0x00) {
        len = 1;
    } else if ((c & 0xE0) == 0xC0) {
        len = 2;
    } else if ((c & 0xF0) == 0xE0) {
        len = 3;
    } else if ((c & 0xF8) == 0xF0) {
        len = 4;
    }
    if (len > s.size()) {
        len = s.size();
    }
    return s.substr(0, len);
}

// 取末个 UTF-8 码点子串。
std::string lastCodepoint(const std::string& s) {
    // 空串返回空串；从末尾向前跳过 10xxxxxx 后续字节，截取返回。
    if (s.empty()) {
        return std::string();
    }
    std::size_t i = s.size();
    std::size_t start = i - 1;
    while (start > 0) {
        unsigned char c = static_cast<unsigned char>(s[start]);
        if ((c & 0xC0) == 0x80) {
            --start;
        } else {
            break;
        }
    }
    return s.substr(start, i - start);
}

// 是否为双 CJK 码点（用 countUtf8Codepoints(s) == 2 且 hasNonAscii(s) 判定）。
bool isTwoCharCjk(const std::string& s) {
    return countUtf8Codepoints(s) == 2 && hasNonAscii(s);
}

// 精确模式往返验证：Cut(s) 恰好切出自身则为词典词。只用公开 Cut API。
bool isDictWord(const cppjieba::Jieba* jieba, const std::string& s) {
    // jieba 为空或 s 为空返回 false；
    // vector<string> out; jieba->Cut(s, out); 返回 out.size()==1 && out[0]==s。
    if (jieba == nullptr || s.empty()) {
        return false;
    }
    std::vector<std::string> out;
    jieba->Cut(s, out);
    return out.size() == 1 && out[0] == s;
}

// 歧义重切（通用机制）：扫描 words，对每个相邻对 (words[i], words[i+1])，
// 若 isSingleCjk(words[i]) 为真、isTwoCharCjk(words[i+1]) 为真、
// isDirectionTimeChar(lastCodepoint(words[i+1])) 为真、
// 且 isDictWord(jieba, words[i] + firstCodepoint(words[i+1])) 为真，
// 则发射合并 token (words[i] + firstCodepoint(words[i+1]))，i 前进 2；
// 否则发射 words[i]，i 前进 1。
std::vector<std::string> resegmentDirectionTime(const cppjieba::Jieba* jieba,
                                                 const std::vector<std::string>& words,
                                                 std::vector<std::string>& outCompounds) {
    std::vector<std::string> result;
    std::unordered_set<std::string> seenCompound;
    std::size_t i = 0;
    while (i < words.size()) {
        if (i + 1 < words.size() &&
            isSingleCjk(words[i]) &&
            isTwoCharCjk(words[i + 1]) &&
            isDirectionTimeChar(lastCodepoint(words[i + 1])) &&
            isDictWord(jieba, words[i] + firstCodepoint(words[i + 1]))) {
            std::string merged = words[i] + firstCodepoint(words[i + 1]);
            result.push_back(merged);
            if (i + 2 < words.size()) {
                const std::string& nxt = words[i + 2];
                if (!nxt.empty() &&
                    !isPunctuationOnly(nxt) &&
                    !isAsciiSymbolOnly(nxt) &&
                    seenCompound.insert(merged + nxt).second) {
                    outCompounds.push_back(merged + nxt);
                }
            }
            i += 2;
        } else {
            result.push_back(words[i]);
            i += 1;
        }
}
return result;
}

}  // namespace

// 剥离疑问/语气词：复用匿名 namespace 内的 fillerWords()/replaceAllWithSpace()/squeezeWhitespace()
// （同文件 isSingleCharStopword 已有此先例）。先 squeezeWhitespace 规范化空白，
// 再按表顺序 replaceAllWithSpace 替换为空格（避免 token 粘连），最后再 squeezeWhitespace 清理残留空白。
std::string stripFillerWords(const std::string& raw) {
    std::string rest = squeezeWhitespace(raw);
    for (const auto& w : fillerWords()) {
        rest = replaceAllWithSpace(rest, w);
    }
    rest = squeezeWhitespace(rest);
    return rest;
}

// 问句胶水词：疑问句式里的场景状语/泛动词/反身代词，信息量极低，进入 keywords
// 只会拉低 coverage 分母。独立于 singleCharStopwords()（后者被 searcher.cpp 共用，不许动）。
// 收 10 个：「住」「里」「用」「到」「唱」「时」「自己」「好」「让」「下来」。
// 「好」为评价性单字（"比较好/处理好"里的"好"），中文里极高频、对区分度零贡献，
// 在 OR 并集召回里会开一条超宽通道稀释排序（v09-t019-q12 根因：期望文档 AND 命中
// 但被含"好"的无关文档在 OR 并集里压过），故并入本表。
// 「不」字有否定保护，不入此表；「自己」为反身代词（对等英文停用词 myself/yourself）。
// 「让」是使役动词/介词（v09-t021-q12："怎么用呼吸让自己稳下来"），无独立检索信息。
// 「下来」是趋向补语残留（v09-t021-q12："稳下来" → "稳"+"下来"，"下来"不承载检索信息）；
// 只精确收录"下来"，不做通用尾字剥离，避免误伤"未来/回来/过去"等含尾字的实义词。
bool isQuestionGlueWord(const std::string& w) {
    static const std::unordered_set<std::string> kSet = {
        "住", "里", "用", "到", "唱", "时", "自己", "好", "让", "下来"};
    return kSet.count(w) > 0;
}

// 单字中文停用词判断（供查询展开等复用）。
bool isSingleCharStopword(const std::string& w) {
    return singleCharStopwords().count(w) > 0;
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
    // 分两步：
    //   2a. token 边界删除（精确模式 Cut 切分后，把 fillerWords 表项在 token
    //       边界上整段换成单个空格），避免字符串级 eraseAll 把相邻 token 粘连成
    //       胶水词（如 q4"才算好按"删"才"后"算好按"粘连）。
    //   2b. 字符串级 eraseAll（原有行为，保持原样、原顺序），负责处理 token 边界
    //       删除覆盖不到的残余（如"才能"这类整词，2a 不动它，交给 2b 按现有行为
    //       撕成"能"——v09-t004-q09 依赖这个"能"，不许动）。
    // 注意：2b 用 eraseAll（直接删除）而非 replaceAllWithSpace——实测 replaceAllWithSpace
    // 在 locate 路径会导致单字 token（如“好”）被空格隔离成独立 AND 组，BM25 排序劣化
    // （v08-qa-09b 回归）。search 路径的 stripFillerWords 仍用空格版（修“报班钱”粘连）。

    // 2a. token 边界疑问词删除：先用精确模式 Cut 分词（非 CutForSearch，因为后者
    //     返回重叠的搜索词，不能拼接回字符串），把 fillerWords 表项在 token 边界上
    //     整段删掉，用单个空格占位（防止左右 token 粘连）。fillerWords() 已按长度降序。
    //     - 多 token 序列：连续子序列直接拼接等于 w（至少两个 token）→ 整个子序列替换为一个 " "。
    //     - 单 token：toks[i] == w → 替换为 " "。
    //     - "才能"这类整词：没有任何 w 与之相等，也拼不出（"才"是单字，子序列至少两个 token
    //       才能触发），因此完整保留，留给后面的字符串级 eraseAll 按现有行为撕成"能"
    //       （v09-t004-q09 依赖这个"能"，不许动）。
    //     之后把 toks 直接拼接（concatenate，不加额外空格）回 rest。
    //     示例："有没有建议"被切成 [有没有][建议] → 两个 token 一起换成一个 " "，[建议] 不会残留。
    //     示例：q4 的 [才] → " "，得到 "范围 算 好按"，[算][好按] 分离。
    //     若 jiebaInstance() 返回空指针，跳过本预处理。
    if (!rest.empty()) {
        const cppjieba::Jieba* jieba = jiebaInstance();
        if (jieba != nullptr) {
            std::vector<std::string> toks;
            jieba->Cut(rest, toks);
            const auto& fillers = fillerWords();  // 已按长度降序
            // 外层按 filler 长度降序遍历：避免短词在前面位置贪掉长词的 token
            //（如"在哪"吃掉"哪一段"中的"在""哪"，导致"一段"残留，v07 回归）。
            for (const auto& w : fillers) {
                if (w.empty()) continue;
                for (size_t i = 0; i < toks.size();) {
                    // 单 token 精确命中。
                    if (toks[i] == w) {
                        toks[i] = " ";
                        ++i;
                        continue;
                    }
                    // 多 token 连续子序列拼接命中（至少两个 token）。
                    std::string acc;
                    size_t j = i;
                    while (j < toks.size() && acc.size() < w.size()) {
                        acc += toks[j];
                        ++j;
                    }
                    if (j - i >= 2 && acc == w) {
                        toks[i] = " ";
                        toks.erase(toks.begin() + i + 1, toks.begin() + j);
                        // i 不变，继续检查当前位置
                    } else {
                        ++i;
                    }
                }
            }
            // 直接拼接（不加额外空格）回 rest。" " 占位符保留以防粘连。
            std::string joined;
            for (const auto& t : toks) joined += t;
            rest = joined;
        }
    }

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
            // 方位时间歧义重切（通用）：[单字][双字词] 的方位时间结构还原为词典词；
            // 同时收集理解层重构的复合概念候选。
            std::vector<std::string> reconCompounds;
            words = resegmentDirectionTime(jieba, words, reconCompounds);
            pq.reconstructedCompounds = reconCompounds;
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
                    if (isPunctuationOnly(w)) continue;  // 全角标点丢弃
                    if (isSingleCjk(w) &&
                        singleCharStopwords().count(w) > 0) {
                        continue;
                    }
                    if (isQuestionGlueWord(w)) continue;
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

namespace {

// 去掉首尾的 UTF-8 空白与常见中英文标点（不引入正则，逐字节判断）。
bool isTrimmableByte(unsigned char c) {
    if (c == ' ' || c == '\t' || c == '\n' || c == '\r') return true;
    return false;
}

// 判断某个 UTF-8 编码的标点是否应被剥离（仅识别常见 3 字节全角标点与 ASCII 标点）。
bool isPunctAt(const std::string& s, size_t i, size_t& len) {
    unsigned char c = static_cast<unsigned char>(s[i]);
    if (c < 0x80) {
        len = 1;
        switch (c) {
            case ',': case '.': case '!': case '?': case ';': case ':':
            case '\'': case '"': case '(': case ')': case '[': case ']':
            case '{': case '}': case '<': case '>': case '~': case '`':
            case '-': case '_': case '=': case '+': case '*': case '/':
            case '\\': case '|': case '@': case '#': case '$': case '%':
            case '^': case '&':
                return true;
            default:
                return false;
        }
    }
    // 全角标点：以 UTF-8 3 字节序列判断首字节 0xE3/0xEF 等。
    if (i + 2 < s.size()) {
        unsigned char b1 = static_cast<unsigned char>(s[i + 1]);
        unsigned char b2 = static_cast<unsigned char>(s[i + 2]);
        // ！ U+FF01
        if (c == 0xEF && b1 == 0xBC && b2 == 0x81) { len = 3; return true; }
        // ？ U+FF1F
        if (c == 0xEF && b1 == 0xBC && b2 == 0x9F) { len = 3; return true; }
        // 。 U+3002
        if (c == 0xE3 && b1 == 0x80 && b2 == 0x82) { len = 3; return true; }
        // ， U+FF0C
        if (c == 0xEF && b1 == 0xBC && b2 == 0x8C) { len = 3; return true; }
        // 、 U+3001
        if (c == 0xE3 && b1 == 0x80 && b2 == 0x81) { len = 3; return true; }
        // ： U+FF1A
        if (c == 0xEF && b1 == 0xBC && b2 == 0x9A) { len = 3; return true; }
        // ； U+FF1B
        if (c == 0xEF && b1 == 0xBC && b2 == 0x9B) { len = 3; return true; }
    }
    len = 0;
    return false;
}

// 去除首尾空白与标点；全部为空白/标点时返回空串。
std::string trimWhitespaceAndPunct(const std::string& in) {
    size_t b = 0;
    size_t e = in.size();
    while (b < e) {
        unsigned char c = static_cast<unsigned char>(in[b]);
        if (isTrimmableByte(c)) { ++b; continue; }
        size_t plen = 0;
        if (isPunctAt(in, b, plen) && plen > 0) { b += plen; continue; }
        break;
    }
    while (e > b) {
        // 反向判断：需要检查尾部最后一个 UTF-8 码点。
        size_t start = e - 1;
        // 回退到码点起始。
        while (start > b &&
               (static_cast<unsigned char>(in[start]) & 0xC0) == 0x80) {
            --start;
        }
        unsigned char c = static_cast<unsigned char>(in[start]);
        if (isTrimmableByte(c)) { e = start; continue; }
        size_t plen = 0;
        if (isPunctAt(in, start, plen) && plen > 0 && start + plen == e) {
            e = start;
            continue;
        }
        break;
    }
    if (e <= b) return std::string();
    return in.substr(b, e - b);
}

// 反复剥离前导疑问词/指代词与空白标点。
std::string stripLeadingFiller(const std::string& in) {
    static const std::vector<std::string> leads = {
        "请问", "请告诉我", "帮我找", "帮我查", "找出",
        "查找", "搜索", "那个", "这个"};
    std::string s = in;
    bool changed = true;
    while (changed) {
        changed = false;
        s = trimWhitespaceAndPunct(s);
        if (s.empty()) break;
        for (const auto& w : leads) {
            if (w.empty()) continue;
            if (s.size() >= w.size() && s.compare(0, w.size(), w) == 0) {
                s = s.substr(w.size());
                changed = true;
                break;
            }
        }
    }
    return trimWhitespaceAndPunct(s);
}

}  // namespace

std::string extractLocateTarget(const std::string& raw) {
    if (raw.empty()) return std::string();

    // ① 引号短语优先。
    std::vector<std::string> phrases;
    std::string rest;
    extractPhrases(raw, phrases, rest);
    if (!phrases.empty()) return phrases[0];

    // ② 触发词之后、最近终结词之前。
    static const std::vector<std::string> triggers = {
        "提到", "写到", "说到", "讲到", "谈到", "介绍"};
    static const std::vector<std::string> ends = {
        "的那段", "的那句", "的那部分", "在哪里", "在哪", "哪里",
        "哪一段", "哪一句", "是什么", "吗", "？", "?", "。"};

    size_t trigPos = std::string::npos;
    size_t trigLen = 0;
    for (const auto& t : triggers) {
        size_t p = raw.find(t);
        if (p != std::string::npos) {
            if (trigPos == std::string::npos || p < trigPos) {
                trigPos = p;
                trigLen = t.size();
            }
        }
    }
    if (trigPos != std::string::npos) {
        size_t begin = trigPos + trigLen;
        size_t endPos = raw.size();
        for (const auto& e : ends) {
            size_t p = raw.find(e, begin);
            if (p != std::string::npos && p < endPos) {
                endPos = p;
            }
        }
        for (const auto& t : triggers) {
            size_t p = raw.find(t, begin);
            if (p != std::string::npos && p < endPos) {
                endPos = p;
            }
        }
        if (endPos > begin) {
            std::string cand = trimWhitespaceAndPunct(raw.substr(begin, endPos - begin));
            static const std::vector<std::string> leadParticles = {
                "了", "的", "着", "过", "呢", "吗", "啊"};
            bool stripped = true;
            while (stripped && !cand.empty()) {
                stripped = false;
                for (const auto& lp : leadParticles) {
                    if (cand.size() >= lp.size() && cand.compare(0, lp.size(), lp) == 0) {
                        cand = cand.substr(lp.size());
                        stripped = true;
                        break;
                    }
                }
            }
            cand = trimWhitespaceAndPunct(cand);
            static const std::vector<std::string> tailParticles = {
                "是", "的", "了", "呢", "吗", "啊", "吧"};
            bool tailStripped = true;
            while (tailStripped && !cand.empty()) {
                tailStripped = false;
                for (const auto& tp : tailParticles) {
                    if (cand.size() >= tp.size() &&
                        cand.compare(cand.size() - tp.size(), tp.size(), tp) == 0) {
                        cand = cand.substr(0, cand.size() - tp.size());
                        tailStripped = true;
                        break;
                    }
                }
            }
            cand = trimWhitespaceAndPunct(cand);
            if (!cand.empty()) return cand;
        }
    }

    // ③ 位置词之前的核心词。
    static const std::vector<std::string> locs = {
        "写在哪", "在哪", "哪里", "何处",
        "那部分", "那段", "那句", "那一段", "那一句"};
    size_t locPos = std::string::npos;
    for (const auto& l : locs) {
        size_t p = raw.find(l);
        if (p != std::string::npos) {
            if (locPos == std::string::npos || p < locPos) {
                locPos = p;
            }
        }
    }
    if (locPos != std::string::npos && locPos > 0) {
        std::string cand = stripLeadingFiller(raw.substr(0, locPos));
        static const std::vector<std::string> leadParticles = {"一下"};
        bool stripped = true;
        while (stripped && !cand.empty()) {
            stripped = false;
            for (const auto& lp : leadParticles) {
                if (cand.size() >= lp.size() && cand.compare(0, lp.size(), lp) == 0) {
                    cand = cand.substr(lp.size());
                    stripped = true;
                    break;
                }
            }
        }
        cand = trimWhitespaceAndPunct(cand);
        static const std::vector<std::string> tailParticles = {"是","的","了","呢","吗","啊","吧"};
        bool tailStripped = true;
        while (tailStripped && !cand.empty()) {
            tailStripped = false;
            for (const auto& tp : tailParticles) {
                if (cand.size() >= tp.size() && cand.compare(cand.size() - tp.size(), tp.size(), tp) == 0) {
                    cand = cand.substr(0, cand.size() - tp.size());
                    tailStripped = true;
                    break;
                }
            }
        }
        cand = trimWhitespaceAndPunct(cand);
        if (!cand.empty()) return cand;
    }

    // ④ 未抽到目标。
    return std::string();
}

}  // namespace docseek
