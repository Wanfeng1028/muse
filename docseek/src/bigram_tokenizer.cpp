#include "docseek/bigram_tokenizer.h"

#include <algorithm>
#include <cstddef>
#include <cstring>
#include <new>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace docseek {

namespace bigram_detail {

// ---------------------------------------------------------------------------
// UTF-8 解码：把字节串转换为码点序列。
// 非法序列（孤立续字节、越界、过长编码、代理区、超过 U+10FFFF）直接丢弃。
// ---------------------------------------------------------------------------
std::vector<uint32_t> decodeUtf8(const std::string& s) {
    std::vector<uint32_t> out;
    out.reserve(s.size());
    const unsigned char* p = reinterpret_cast<const unsigned char*>(s.data());
    const size_t n = s.size();
    size_t i = 0;
    while (i < n) {
        unsigned char c = p[i];
        uint32_t cp = 0;
        size_t len = 0;
        if (c < 0x80) {
            cp = c;
            len = 1;
        } else if ((c & 0xE0) == 0xC0) {
            cp = c & 0x1F;
            len = 2;
        } else if ((c & 0xF0) == 0xE0) {
            cp = c & 0x0F;
            len = 3;
        } else if ((c & 0xF8) == 0xF0) {
            cp = c & 0x07;
            len = 4;
        } else {
            // 非法起始字节，丢弃该字节。
            ++i;
            continue;
        }
        if (i + len > n) {
            // 截断序列，丢弃该起始字节。
            ++i;
            continue;
        }
        bool ok = true;
        for (size_t k = 1; k < len; ++k) {
            unsigned char cc = p[i + k];
            if ((cc & 0xC0) != 0x80) {
                ok = false;
                break;
            }
            cp = (cp << 6) | (cc & 0x3F);
        }
        if (!ok) {
            ++i;
            continue;
        }
        // 过长编码与非法范围检查。
        if ((len == 2 && cp < 0x80) || (len == 3 && cp < 0x800) ||
            (len == 4 && cp < 0x10000)) {
            ++i;
            continue;
        }
        if (cp >= 0xD800 && cp <= 0xDFFF) {  // 代理区
            ++i;
            continue;
        }
        if (cp > 0x10FFFF) {
            ++i;
            continue;
        }
        out.push_back(cp);
        i += len;
    }
    return out;
}

// ---------------------------------------------------------------------------
// 编码单个码点为 UTF-8 字符串。
// ---------------------------------------------------------------------------
std::string encodeUtf8(uint32_t cp) {
    std::string s;
    if (cp < 0x80) {
        s.push_back(static_cast<char>(cp));
    } else if (cp < 0x800) {
        s.push_back(static_cast<char>(0xC0 | (cp >> 6)));
        s.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else if (cp < 0x10000) {
        s.push_back(static_cast<char>(0xE0 | (cp >> 12)));
        s.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
        s.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else {
        s.push_back(static_cast<char>(0xF0 | (cp >> 18)));
        s.push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F)));
        s.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
        s.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    }
    return s;
}

// ---------------------------------------------------------------------------
// CJK 判定：覆盖常用汉字、扩展 A、扩展 B 部分、日文假名、韩文音节。
// ---------------------------------------------------------------------------
bool isCjk(uint32_t cp) {
    if (cp >= 0x4E00 && cp <= 0x9FFF) return true;    // CJK 统一表意文字
    if (cp >= 0x3400 && cp <= 0x4DBF) return true;    // 扩展 A
    if (cp >= 0x20000 && cp <= 0x2A6DF) return true;  // 扩展 B
    if (cp >= 0x3040 && cp <= 0x30FF) return true;    // 日文假名
    if (cp >= 0xAC00 && cp <= 0xD7A3) return true;    // 韩文音节
    return false;
}

// ---------------------------------------------------------------------------
// ASCII 字母数字判定。
// ---------------------------------------------------------------------------
bool isAsciiAlnum(uint32_t cp) {
    if (cp >= '0' && cp <= '9') return true;
    if (cp >= 'a' && cp <= 'z') return true;
    if (cp >= 'A' && cp <= 'Z') return true;
    return false;
}

// ---------------------------------------------------------------------------
// 单字停用词表（码点）。
// ---------------------------------------------------------------------------
bool isCjkStopword(uint32_t cp) {
    switch (cp) {
        case 0x7684:  // 的
        case 0x4E86:  // 了
        case 0x662F:  // 是
        case 0x5728:  // 在
        case 0x548C:  // 和
        case 0x6709:  // 有
        case 0x6211:  // 我
        case 0x4F60:  // 你
        case 0x4ED6:  // 他
        case 0x4E2A:  // 个
        case 0x8FD9:  // 这
        case 0x90A3:  // 那
        case 0x4E0E:  // 与
        case 0x4E3A:  // 为
        case 0x4E4B:  // 之
        case 0x53CA:  // 及
        case 0x6216:  // 或
        case 0x7B49:  // 等
        case 0x5C31:  // 就
        case 0x90FD:  // 都
        case 0x4E5F:  // 也
        case 0x4E0D:  // 不
        case 0x6CA1:  // 没
        case 0x5F88:  // 很
        case 0x4F46:  // 但
        case 0x800C:  // 而
        case 0x5176:  // 其
        case 0x6240:  // 所
        case 0x88AB:  // 被
        case 0x628A:  // 把
        case 0x5BF9:  // 对
        case 0x5411:  // 向
        case 0x4ECE:  // 从
        case 0x4E8E:  // 于
        case 0x4E0A:  // 上
        case 0x4E0B:  // 下
        case 0x4E2D:  // 中
        case 0x5185:  // 内
        case 0x5916:  // 外
        case 0x524D:  // 前
        case 0x540E:  // 后
            return true;
        default:
            return false;
    }
}

// ---------------------------------------------------------------------------
// 对一段纯 CJK 码点做 bigram 滑动切分。
// (c0,c1),(c1,c2),…；奇数个码点时末字输出单字 token。
// 停用词规则：单字 token 若 isCjkStopword 则丢弃；
//            bigram token 仅当两个字都是停用词时丢弃。
// ---------------------------------------------------------------------------
std::vector<std::string> cutCjkRun(const std::vector<uint32_t>& cps) {
    std::vector<std::string> out;
    const size_t n = cps.size();
    if (n == 0) return out;
    if (n == 1) {
        if (!isCjkStopword(cps[0])) {
            out.push_back(encodeUtf8(cps[0]));
        }
        return out;
    }
    for (size_t i = 0; i + 1 < n; ++i) {
        uint32_t a = cps[i];
        uint32_t b = cps[i + 1];
        if (isCjkStopword(a) && isCjkStopword(b)) continue;
        std::string tok;
        tok += encodeUtf8(a);
        tok += encodeUtf8(b);
        out.push_back(std::move(tok));
    }
    // 奇数个码点：末字输出单字 token。
    if (n % 2 == 1) {
        uint32_t last = cps[n - 1];
        if (!isCjkStopword(last)) {
            out.push_back(encodeUtf8(last));
        }
    }
    return out;
}

}  // namespace bigram_detail

namespace {

using bigram_detail::decodeUtf8;
using bigram_detail::encodeUtf8;
using bigram_detail::isAsciiAlnum;
using bigram_detail::isCjk;
using bigram_detail::isCjkStopword;
using bigram_detail::cutCjkRun;

// ---------------------------------------------------------------------------
// 单个 token 的内部表示：文本 + 输入字节起止偏移 + 是否 colocated。
// ---------------------------------------------------------------------------
struct BigramToken {
    std::string text;
    int start = 0;
    int end = 0;
    bool colocated = false;
};

// ---------------------------------------------------------------------------
// 后缀字集合（用于专名附加 (a)）。
// ---------------------------------------------------------------------------
bool isSuffixChar(uint32_t cp) {
    switch (cp) {
        case 0x7701:  // 省
        case 0x5E02:  // 市
        case 0x533A:  // 区
        case 0x53BF:  // 县
        case 0x9547:  // 镇
        case 0x4E61:  // 乡
        case 0x6751:  // 村
        case 0x8DEF:  // 路
        case 0x8857:  // 街
        case 0x9053:  // 道
        case 0x53F7:  // 号
        case 0x697C:  // 楼
            return true;
        default:
            return false;
    }
}

// ---------------------------------------------------------------------------
// 百家姓首字集合（用于专名附加 (b)）。
// ---------------------------------------------------------------------------
bool isSurnameChar(uint32_t cp) {
    static const uint32_t kSurnames[] = {
        0x738B,  // 王
        0x674E,  // 李
        0x5F20,  // 张
        0x5218,  // 刘
        0x9648,  // 陈
        0x6768,  // 杨
        0x9EC4,  // 黄
        0x8D75,  // 赵
        0x5434,  // 吴
        0x5468,  // 周
        0x5F90,  // 徐
        0x5B59,  // 孙
        0x9A6C,  // 马
        0x6731,  // 朱
        0x80E1,  // 胡
        0x90ED,  // 郭
        0x4F55,  // 何
        0x9AD8,  // 高
        0x6797,  // 林
        0x7F57,  // 罗
        0x90D1,  // 郑
        0x6881,  // 梁
        0x8C22,  // 谢
        0x5B8B,  // 宋
        0x5510,  // 唐
        0x8BB8,  // 许
        0x97E9,  // 韩
        0x51AF,  // 冯
        0x8463,  // 董
        0x8427,  // 萧
        0x7A0B,  // 程
        0x66F9,  // 曹
        0x8881,  // 袁
        0x9093,  // 邓
        0x5085,  // 傅
        0x6C88,  // 沈
        0x66FE,  // 曾
        0x5F6D,  // 彭
        0x5415,  // 吕
        0x82CF,  // 苏
        0x5362,  // 卢
        0x848B,  // 蒋
        0x8521,  // 蔡
        0x8D3E,  // 贾
        0x4E01,  // 丁
        0x9B4F,  // 魏
        0x859B,  // 薛
        0x53F6,  // 叶
        0x960E,  // 阎
        0x4F59,  // 余
        0x6F58,  // 潘
        0x675C,  // 杜
        0x6234,  // 戴
        0x590F,  // 夏
        0x949F,  // 钟
        0x6C6A,  // 汪
        0x7530,  // 田
        0x4EFB,  // 任
        0x59DC,  // 姜
        0x8303,  // 范
        0x65B9,  // 方
        0x77F3,  // 石
        0x59DA,  // 姚
        0x8C2D,  // 谭
        0x5ED6,  // 廖
        0x90B9,  // 邹
        0x718A,  // 熊
        0x91D1,  // 金
        0x9646,  // 陆
        0x90DD,  // 郝
        0x5B54,  // 孔
        0x767D,  // 白
        0x5D14,  // 崔
        0x5EB7,  // 康
        0x6BDB,  // 毛
        0x90B1,  // 邱
        0x79E6,  // 秦
        0x6C5F,  // 江
        0x53F2,  // 史
        0x987E,  // 顾
        0x4FAF,  // 侯
        0x90B5,  // 邵
        0x5B5F,  // 孟
        0x9F99,  // 龙
        0x4E07,  // 万
        0x6BB5,  // 段
        0x96F7,  // 雷
        0x94B1,  // 钱
        0x6C64,  // 汤
        0x5C39,  // 尹
        0x9ECE,  // 黎
        0x6613,  // 易
        0x5E38,  // 常
        0x6B66,  // 武
        0x4E54,  // 乔
        0x8D3A,  // 贺
        0x8D56,  // 赖
        0x9F9A,  // 龚
        0x6587,  // 文
    };
    for (uint32_t c : kSurnames) {
        if (c == cp) return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// 一次性切分：输入文本 → token 列表（含专名附加）。
// 索引侧与查询侧共用同一逻辑，保证一致。
// ---------------------------------------------------------------------------
// cutWithOffsets：一次性切分，输入文本 → BigramToken 列表。
//
// 规则：
//   - CJK 码点攒成 run，run 内按 bigram 滑动：
//       run 长度 1 → 输出单字（若是停用词则丢弃）；
//       长度 >= 2 → 依次输出 (0,1) (2,3) ...；若长度为奇数，最后一字单独输出；
//       相邻两个字都是停用词时，该 bigram 丢弃。
//   - ASCII 字母数字攒词：字母折叠为小写；遇到空白 / 标点 / 非 alnum 结束。
//   - 数字串保护：[0-9]+ 后允许 ('.'|','|数字) 继续，末尾若紧跟 '%'/'％' 则一并吞入。
//   - 专名附加（只增不减，不删除已产出的 bigram）：
//       (a) 地名后缀字前 1..5 个 CJK 字成段，标记 colocated=true；
//       (b) 姓氏首字后 1..2 个 CJK 字成姓名，标记 colocated=true。
// ---------------------------------------------------------------------------
std::vector<BigramToken> cutWithOffsets(const std::string& text) {
    std::vector<BigramToken> out;

    // 解码：记录每个码点的 (codepoint, byteStart, byteEnd)。
    struct CpInfo {
        uint32_t cp;
        int byteStart;
        int byteEnd;
    };
    std::vector<CpInfo> cps;
    {
        const std::vector<uint32_t> decoded = decodeUtf8(text);
        int off = 0;
        for (uint32_t cp : decoded) {
            const int len = static_cast<int>(encodeUtf8(cp).size());
            cps.push_back(CpInfo{cp, off, off + len});
            off += len;
        }
    }

    const size_t n = cps.size();
    size_t i = 0;

    auto pushToken = [&](size_t a, size_t b, bool colocated) {
        // [a, b) 为码点下标闭开区间。
        if (a >= b || b > n) return;
        int bs = cps[a].byteStart;
        int be = cps[b - 1].byteEnd;
        if (bs >= be) return;
        BigramToken t;
        t.text = text.substr(static_cast<size_t>(bs),
                             static_cast<size_t>(be - bs));
        t.start = bs;
        t.end = be;
        t.colocated = colocated;
        out.push_back(std::move(t));
    };

    // 记录已产出的 bigram 覆盖区间，供专名附加阶段判断是否重复。
    // 专名附加"只增不减"：即使区间与已有 bigram 相同，也不删除已有 token；
    // 这里仅用于避免生成完全相同的重复附加 token。
    std::set<std::pair<int, int>> emitted;

    auto emitRange = [&](size_t a, size_t b, bool colocated) {
        if (a >= b || b > n) return;
        int bs = cps[a].byteStart;
        int be = cps[b - 1].byteEnd;
        if (bs >= be) return;
        if (!colocated && emitted.count({bs, be})) return;
        if (colocated && emitted.count({bs, be})) return;
        emitted.insert({bs, be});
        pushToken(a, b, colocated);
    };

    // -----------------------------------------------------------------------
    // 主扫描。
    // -----------------------------------------------------------------------
    while (i < n) {
        uint32_t cp = cps[i].cp;

        // ---- CJK run ----
        if (isCjk(cp)) {
            size_t j = i;
            while (j < n && isCjk(cps[j].cp)) ++j;
            size_t runLen = j - i;

            if (runLen == 1) {
                // 单字：停用词丢弃，否则输出。
                if (!isCjkStopword(cps[i].cp)) {
                    emitRange(i, i + 1, false);
                }
            } else {
                // bigram 滑动。
                size_t k = i;
                while (k + 1 < j) {
                    uint32_t c0 = cps[k].cp;
                    uint32_t c1 = cps[k + 1].cp;
                    if (!(isCjkStopword(c0) && isCjkStopword(c1))) {
                        emitRange(k, k + 2, false);
                    }
                    k += 1;
                }
                // 奇数尾：最后一字单独输出（若停用词则丢弃）。
                if ((runLen % 2) == 1) {
                    if (!isCjkStopword(cps[j - 1].cp)) {
                        emitRange(j - 1, j, false);
                    }
                }
            }
            i = j;
            continue;
        }

        // ---- ASCII 字母数字词 ----
        if (isAsciiAlnum(cp)) {
            size_t j = i;
            std::string word;
            while (j < n && isAsciiAlnum(cps[j].cp)) {
                uint32_t c = cps[j].cp;
                if (c >= 'A' && c <= 'Z') {
                    word.push_back(static_cast<char>(c - 'A' + 'a'));
                } else {
                    word.push_back(static_cast<char>(c));
                }
                ++j;
            }
            // 数字串保护：若首字符是数字，允许吞入内部 '.'/','，末尾可选 '%'/'％'。
            bool startsDigit = (cp >= '0' && cp <= '9');
            if (startsDigit) {
                // 继续吞入 '.' / ',' / 数字（isAsciiAlnum 已含数字）。
                while (j < n) {
                    uint32_t c = cps[j].cp;
                    if (c == '.' || c == ',') {
                        // 只有后面紧跟数字才吞入，避免吞掉句末标点。
                        if (j + 1 < n && cps[j + 1].cp >= '0' &&
                            cps[j + 1].cp <= '9') {
                            word.push_back(static_cast<char>(c));
                            ++j;
                            continue;
                        }
                        break;
                    }
                    if (c >= '0' && c <= '9') {
                        word.push_back(static_cast<char>(c));
                        ++j;
                        continue;
                    }
                    break;
                }
                // 可选百分号。
                if (j < n && (cps[j].cp == '%' || cps[j].cp == 0xFF05)) {
                    if (cps[j].cp == '%') {
                        word.push_back('%');
                    } else {
                        word += "\xEF\xBC\x85";  // ％
                    }
                    ++j;
                }
            }
            if (!word.empty()) {
                int bs = cps[i].byteStart;
                int be = cps[j - 1].byteEnd;
                if (bs < be) {
                    BigramToken t;
                    t.text = word;
                    t.start = bs;
                    t.end = be;
                    t.colocated = false;
                    out.push_back(std::move(t));
                    emitted.insert({bs, be});
                }
            }
            i = j;
            continue;
        }

        // ---- 其它（空白、标点、非 CJK 非 alnum）：跳过 ----
        ++i;
    }

    // -----------------------------------------------------------------------
    // 专名附加（只增不减）：
    //   (a) 地名后缀字前 1..5 个 CJK 字成段；
    //   (b) 姓氏首字后 1..2 个 CJK 字成姓名。
    // -----------------------------------------------------------------------
    std::vector<BigramToken> extra;
    for (size_t idx = 0; idx < n; ++idx) {
        uint32_t cp = cps[idx].cp;

        // (a) 地名后缀：后缀字前 1..5 个连续 CJK 字。
        if (isSuffixChar(cp)) {
            size_t avail = 0;
            size_t back = idx;
            while (back > 0 && avail < 5 && isCjk(cps[back - 1].cp)) {
                --back;
                ++avail;
            }
            for (size_t take = 1; take <= avail; ++take) {
                size_t a = idx - take;
                size_t b = idx + 1;  // 含后缀字
                if (b > n) break;
                int bs = cps[a].byteStart;
                int be = cps[b - 1].byteEnd;
                if (bs >= be) continue;
                if (emitted.count({bs, be})) continue;
                BigramToken t;
                t.text = text.substr(static_cast<size_t>(bs),
                                     static_cast<size_t>(be - bs));
                t.start = bs;
                t.end = be;
                t.colocated = true;
                emitted.insert({bs, be});
                extra.push_back(std::move(t));
            }
        }

        // (b) 姓氏：首字后 1..2 个连续 CJK 字。
        // 约束：姓氏字必须是 CJK run 的开头（idx == 0 或前一个码点非 CJK），
        // 否则 run 中间的普通字（如 "全文检索" 中的 "文"）会被误当姓氏首字，
        // 从而附加 "文检索" 之类的伪姓名 token。
        bool atRunStart = (idx == 0) || !isCjk(cps[idx - 1].cp);
        if (isSurnameChar(cp) && atRunStart) {
            size_t avail = 0;
            size_t fwd = idx + 1;
            while (fwd < n && avail < 2 && isCjk(cps[fwd].cp)) {
                ++fwd;
                ++avail;
            }
            for (size_t take = 1; take <= avail; ++take) {
                size_t a = idx;
                size_t b = idx + 1 + take;
                if (b > n) break;
                int bs = cps[a].byteStart;
                int be = cps[b - 1].byteEnd;
                if (bs >= be) continue;
                if (emitted.count({bs, be})) continue;
                BigramToken t;
                t.text = text.substr(static_cast<size_t>(bs),
                                     static_cast<size_t>(be - bs));
                t.start = bs;
                t.end = be;
                t.colocated = true;
                emitted.insert({bs, be});
                extra.push_back(std::move(t));
            }
        }
    }

    for (auto& t : extra) {
        out.push_back(std::move(t));
    }

    return out;
}


// ---------------------------------------------------------------------------
// FTS5 分词器上下文：无状态，占位即可。
// ---------------------------------------------------------------------------
struct BigramTokenizer {
    int unused = 0;
};

// ---------------------------------------------------------------------------
// xCreate：初始化分词器上下文。
// ---------------------------------------------------------------------------
int bigramXCreate(void* /*pUnused*/, const char** /*azArg*/, int /*nArg*/,
                  Fts5Tokenizer** ppOut) {
    BigramTokenizer* ctx = new (std::nothrow) BigramTokenizer();
    if (ctx == nullptr) {
        return SQLITE_NOMEM;
    }
    *ppOut = reinterpret_cast<Fts5Tokenizer*>(ctx);
    return SQLITE_OK;
}

// ---------------------------------------------------------------------------
// xDelete：释放分词器上下文。
// ---------------------------------------------------------------------------
void bigramXDelete(Fts5Tokenizer* pTokenizer) {
    BigramTokenizer* ctx = reinterpret_cast<BigramTokenizer*>(pTokenizer);
    delete ctx;
}

// ---------------------------------------------------------------------------
// xTokenize：对输入文本分词，逐个 token 回调 xToken。
// ---------------------------------------------------------------------------
int bigramXTokenize(Fts5Tokenizer* /*pTokenizer*/, void* pCtx, int /*flags*/,
                    const char* pText, int nText, const char* /*pLocale*/,
                    int /*nLocale*/,
                    int (*xToken)(void*, int, const char*, int, int, int)) {
    if (pText == nullptr || nText <= 0) {
        return SQLITE_OK;
    }

    std::string input(pText, static_cast<size_t>(nText));
    std::vector<BigramToken> tokens;
    try {
        tokens = cutWithOffsets(input);
    } catch (...) {
        return SQLITE_ERROR;
    }

    for (const BigramToken& t : tokens) {
        if (t.text.empty() || t.start >= t.end) continue;
        int rc = xToken(pCtx,
                        t.colocated ? FTS5_TOKEN_COLOCATED : 0,
                        t.text.data(), static_cast<int>(t.text.size()),
                        t.start, t.end);
        if (rc != SQLITE_OK) {
            return rc;
        }
    }
    return SQLITE_OK;
}

}  // namespace

// ---------------------------------------------------------------------------
// bigramCutForSearch：对 text 切分后去重保序，返回 token 文本序列。
// ---------------------------------------------------------------------------
std::vector<std::string> bigramCutForSearch(const std::string& text) {
    std::vector<BigramToken> tokens = cutWithOffsets(text);
    std::vector<std::string> result;
    std::set<std::string> seen;
    result.reserve(tokens.size());
    for (auto& t : tokens) {
        if (t.text.empty()) continue;
        if (seen.insert(t.text).second) {
            result.push_back(std::move(t.text));
        }
    }
    return result;
}

// ---------------------------------------------------------------------------
// 注册入口：注册名为 "bigram" 的 FTS5 分词器。
// ---------------------------------------------------------------------------
int registerBigramTokenizer(sqlite3* db) {
    if (db == nullptr) {
        return SQLITE_ERROR;
    }

    // 获取 fts5_api：通过 SELECT fts5(?1) 并绑定名为 "fts5_api_ptr" 的指针。
    fts5_api* api = nullptr;
    sqlite3_stmt* stmt = nullptr;
    int rc = sqlite3_prepare_v2(db, "SELECT fts5(?1);", -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        return SQLITE_ERROR;
    }
    rc = sqlite3_bind_pointer(stmt, 1, static_cast<void*>(&api),
                              "fts5_api_ptr", nullptr);
    if (rc == SQLITE_OK) {
        rc = sqlite3_step(stmt);
    }
    sqlite3_finalize(stmt);
    if (rc != SQLITE_ROW || api == nullptr) {
        return SQLITE_ERROR;
    }

    static BigramTokenizer g_ctx;  // pUserData 占位；实际上下文在 xCreate 中创建。

    fts5_tokenizer_v2 tokenizer;
    tokenizer.iVersion = 2;
    tokenizer.xCreate = bigramXCreate;
    tokenizer.xDelete = bigramXDelete;
    tokenizer.xTokenize = bigramXTokenize;

    int rc2 = api->xCreateTokenizer_v2(
        api, "bigram", reinterpret_cast<void*>(&g_ctx), &tokenizer, nullptr);
    if (rc2 != SQLITE_OK) {
        return rc2;
    }
    return SQLITE_OK;
}

}  // namespace docseek
