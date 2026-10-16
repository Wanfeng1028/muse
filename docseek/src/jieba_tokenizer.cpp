#include "docseek/jieba_tokenizer.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <mutex>
#include <set>
#include <string>
#include <vector>

#if defined(__linux__)
#include <unistd.h>
#endif

#include "cppjieba/Jieba.hpp"
#include "docseek/dict.h"

namespace docseek {

namespace {

// ---------------------------------------------------------------------------
// 进程级单例 Jieba
//
// cppjieba::Jieba 构造时会加载词典构建前缀 trie；构造完成后其
// CutForSearch 只对 trie 做只读查询，因此多个线程在 const Jieba 上
// 并发调用 CutForSearch 是安全的（cppjieba 官方说明 + 内部实现只读）。
// 我们通过 std::once_flag 保证初始化只发生一次。
// ---------------------------------------------------------------------------
cppjieba::Jieba* g_jieba = nullptr;
std::once_flag g_jiebaOnce;
std::string g_jiebaInitError;

// RAII：构造时把 stderr（fd 2）重定向到 /dev/null，析构时恢复。
// 用途：屏蔽 cppjieba/limonp 在加载词典时打印的大量噪音日志
// （如 "KeywordExtractor ... empty. skipped."，见 docs/eval.md 已知问题 #1）。
// 仅在 std::call_once 的单线程初始化路径使用，不考虑并发构造。
// 设 DOCSEEK_JIEBA_VERBOSE=1 可关闭屏蔽，用于排障。
class StderrSilencer {
public:
    StderrSilencer() {
#if defined(__linux__)
        const char* v = std::getenv("DOCSEEK_JIEBA_VERBOSE");
        if (v && v[0] == '1') return;  // 排障模式：保留原始 stderr
        std::fflush(stderr);
        saved_ = ::dup(STDERR_FILENO);
        if (saved_ < 0) return;
        int devnull = ::open("/dev/null", O_WRONLY);
        if (devnull < 0) return;
        ::dup2(devnull, STDERR_FILENO);
        ::close(devnull);
#else
        (void)0;
#endif
    }
    ~StderrSilencer() {
#if defined(__linux__)
        if (saved_ >= 0) {
            std::fflush(stderr);
            ::dup2(saved_, STDERR_FILENO);
            ::close(saved_);
        }
#endif
    }
    StderrSilencer(const StderrSilencer&) = delete;
    StderrSilencer& operator=(const StderrSilencer&) = delete;

private:
    int saved_ = -1;
};

// 初始化全局 Jieba；成功返回 true。多次调用只初始化一次。
bool ensureJieba() {
    std::call_once(g_jiebaOnce, []() {
        try {
            std::string dir = resolveDictDir();
            std::string dictPath = dir + "/jieba.dict.utf8";
            std::string hmmPath = dir + "/hmm_model.utf8";
            std::string idfPath = dir + "/idf.utf8";
            std::string stopPath = dir + "/stop_words.utf8";
            // cppjieba::Jieba 构造函数签名为：
            //   Jieba(dict_path, model_path, user_dict_path, idf_path,
            //         stop_word_path)
            // 注意参数顺序：idf 与 stop_words 不能错位（曾因此把 idf 当用户
            // 词典加载，导致切词异常）。无用户词典时传空字符串。
            StderrSilencer silence;  // 屏蔽 limonp 词典加载噪音（DOCSEEK_JIEBA_VERBOSE=1 恢复）
            g_jieba = new cppjieba::Jieba(dictPath, hmmPath, "",
                                          idfPath, stopPath);
        } catch (const std::exception& e) {
            g_jiebaInitError = e.what();
            g_jieba = nullptr;
        } catch (...) {
            g_jiebaInitError = "未知异常";
            g_jieba = nullptr;
        }
    });
    return g_jieba != nullptr;
}

// ---------------------------------------------------------------------------
// 分词器上下文
// ---------------------------------------------------------------------------
struct JiebaTokenizer {
    // fts5_tokenizer_v2 的 pUserData 指向本结构。
    // 本结构由 SQLite 在注册期间持有；进程级单例 Jieba 由 ensureJieba 管理。
    int dummy = 0;
};

// ---------------------------------------------------------------------------
// 工具：判断一个字节是否为 ASCII 字母。
// ---------------------------------------------------------------------------
inline bool isAsciiAlpha(unsigned char c) {
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z');
}

// ---------------------------------------------------------------------------
// 工具：解析 UTF-8 字符串，返回每个码点的字节起始偏移列表。
// 返回的 offsets 长度为码点数 + 1，最后一个元素为字符串字节长度。
// 遇到非法 UTF-8 时按单字节处理（保证不会死循环）。
// ---------------------------------------------------------------------------
std::vector<size_t> utf8CodepointOffsets(const char* text, int nText) {
    std::vector<size_t> offsets;
    offsets.reserve(static_cast<size_t>(nText) + 1);
    size_t i = 0;
    const size_t n = static_cast<size_t>(nText);
    while (i < n) {
        offsets.push_back(i);
        unsigned char c = static_cast<unsigned char>(text[i]);
        size_t len;
        if (c < 0x80) {
            len = 1;
        } else if ((c & 0xE0) == 0xC0) {
            len = 2;
        } else if ((c & 0xF0) == 0xE0) {
            len = 3;
        } else if ((c & 0xF8) == 0xF0) {
            len = 4;
        } else {
            // 非法起始字节，按单字节推进。
            len = 1;
        }
        // 确保不越界，并且后续字节确实是续字节（0b10xxxxxx）。
        if (i + len > n) {
            len = 1;
        } else {
            for (size_t k = 1; k < len; ++k) {
                unsigned char cc = static_cast<unsigned char>(text[i + k]);
                if ((cc & 0xC0) != 0x80) {
                    len = 1;
                    break;
                }
            }
        }
        i += len;
    }
    offsets.push_back(n);
    return offsets;
}

// ---------------------------------------------------------------------------
// xCreate：初始化分词器上下文。
// ---------------------------------------------------------------------------
int jiebaXCreate(void* /*pUnused*/, const char** /*azArg*/, int /*nArg*/,
                 Fts5Tokenizer** ppOut) {
    if (!ensureJieba()) {
        return SQLITE_ERROR;
    }
    JiebaTokenizer* ctx = new (std::nothrow) JiebaTokenizer();
    if (ctx == nullptr) {
        return SQLITE_NOMEM;
    }
    *ppOut = reinterpret_cast<Fts5Tokenizer*>(ctx);
    return SQLITE_OK;
}

// ---------------------------------------------------------------------------
// xDelete：释放分词器上下文。
// ---------------------------------------------------------------------------
void jiebaXDelete(Fts5Tokenizer* pTokenizer) {
    JiebaTokenizer* ctx = reinterpret_cast<JiebaTokenizer*>(pTokenizer);
    delete ctx;
}

// ---------------------------------------------------------------------------
// 对一个词做 ASCII 小写折叠后通过 xToken 回调输出。
// 若 start/end 无效（start >= end）则不输出。
// ---------------------------------------------------------------------------
void emitToken(const char* text, int start, int end, void* pCtx,
               int (*xToken)(void*, int, const char*, int, int, int)) {
    if (start >= end) {
        return;
    }
    // ASCII 小写折叠。CJK / 数字不受影响。
    std::string buf(text + start, static_cast<size_t>(end - start));
    bool changed = false;
    for (char& ch : buf) {
        unsigned char uc = static_cast<unsigned char>(ch);
        if (uc >= 'A' && uc <= 'Z') {
            ch = static_cast<char>(uc - 'A' + 'a');
            changed = true;
        }
    }
    if (changed) {
        xToken(pCtx, 0, buf.data(), static_cast<int>(buf.size()), start, end);
    } else {
        xToken(pCtx, 0, text + start, end - start, start, end);
    }
}

// ---------------------------------------------------------------------------
// xTokenize：对输入文本分词。
//
// 实现策略：
//   1. 用 CutForSearch 得到词序列；
//   2. 用游标 cursor 在原文中顺序查找每个词（处理重复词）；
//      - 若在 cursor 之后找到该词，计算 start/end（字节下标）；
//      - 若找不到（理论上不会，但为健壮性），回退为把该词按 Unicode
//        码点逐字切分，并在原文中定位每个字；
//   3. 任何情况下都保证 cursor 单调前进，不会死循环。
// ---------------------------------------------------------------------------
int jiebaXTokenize(Fts5Tokenizer* pTokenizer, void* pCtx, int /*flags*/,
                   const char* pText, int nText, const char* /*pLocale*/,
                   int /*nLocale*/,
                   int (*xToken)(void*, int, const char*, int, int, int)) {
    if (pText == nullptr || nText <= 0) {
        return SQLITE_OK;
    }
    JiebaTokenizer* ctx = reinterpret_cast<JiebaTokenizer*>(pTokenizer);
    (void)ctx;

    if (!ensureJieba() || g_jieba == nullptr) {
        return SQLITE_ERROR;
    }

    std::string input(pText, static_cast<size_t>(nText));
    std::vector<std::string> words;
    try {
        g_jieba->CutForSearch(input, words);
    } catch (...) {
        // 分词失败：退化为按码点逐字切分整段文本。
        words.clear();
    }

    // 记录已发出的 token 区间，避免重复输出（CutForSearch 可能产生重叠词）。
    // 但 FTS5 允许重叠 token；我们仍然允许重叠，只保证不越界。

    if (words.empty()) {
        // 退化路径：按 Unicode 码点逐字输出。
        std::vector<size_t> offsets = utf8CodepointOffsets(pText, nText);
        for (size_t i = 0; i + 1 < offsets.size(); ++i) {
            int s = static_cast<int>(offsets[i]);
            int e = static_cast<int>(offsets[i + 1]);
            emitToken(pText, s, e, pCtx, xToken);
        }
        return SQLITE_OK;
    }

    // 已发出的 (词, 起始字节偏移) 集合，防止同一位置重复输出。
    // 不同词允许同一位置重叠（如"计算"和"计算机"都在字节 0），
    // 因此 key 必须包含词本身。
    //
    // 改用"全文 occurrence 扫描 + 已认领集合"替代原来的单调游标：
    // CutForSearch 会输出重叠词（如"计算机技术" => <计算> <算机> <技术>
    // <计算机> <计算机技术>），排在后面的词其真实位置可能落在游标之前，
    // 单调游标 find 会返回 npos 静默丢词，甚至跳到后文同词处导致游标
    // 大幅前跳、级联丢失后续普通词。全文扫描则对每个词独立定位。
    std::set<std::pair<std::string, size_t>> claimed;

    for (const std::string& w : words) {
        if (w.empty()) continue;

        // 在全文 [0, n) 中枚举 w 的所有出现位置，取第一个尚未被认领的。
        // p + 1 按字节推进，允许重叠出现（如 "aa" 在 "aaa" 中的 0 和 1）。
        // 循环天然有界：words 有限、find 位置单调递增，不可能死循环。
        size_t chosen = std::string::npos;
        for (size_t p = input.find(w, 0); p != std::string::npos; p = input.find(w, p + 1)) {
            if (claimed.find(std::make_pair(w, p)) == claimed.end()) {
                chosen = p;
                break;
            }
        }

        if (chosen != std::string::npos) {
            emitToken(pText, (int)chosen, (int)(chosen + w.size()), pCtx, xToken);
            claimed.insert(std::make_pair(w, chosen));
        } else {
            // 回退路径：CutForSearch 可能对词做了归一化（如大小写折叠），
            // 导致 w 在原文中无法一字不差地找到。此时按 Unicode 码点切分 w，
            // 逐个码点在全文 [0, n) 中定位，同样用 claimed 集合避免重复认领。
            // （原实现从 cursor 起找；cursor 已删除，改为从 0 起找。）
            std::vector<size_t> offsets =
                utf8CodepointOffsets(w.data(), static_cast<int>(w.size()));
            for (size_t i = 0; i + 1 < offsets.size(); ++i) {
                std::string cp = w.substr(offsets[i], offsets[i + 1] - offsets[i]);
                size_t cpChosen = std::string::npos;
                for (size_t p = input.find(cp, 0); p != std::string::npos; p = input.find(cp, p + 1)) {
                    if (claimed.find(std::make_pair(cp, p)) == claimed.end()) {
                        cpChosen = p;
                        break;
                    }
                }
                if (cpChosen == std::string::npos) {
                    // 该码点无法在原文中定位，放弃该词剩余部分。
                    break;
                }
                emitToken(pText, (int)cpChosen, (int)(cpChosen + cp.size()), pCtx, xToken);
                claimed.insert(std::make_pair(cp, cpChosen));
            }
        }
    }


    return SQLITE_OK;
}

}  // namespace

// ---------------------------------------------------------------------------
// 注册入口
// ---------------------------------------------------------------------------
int registerJiebaTokenizer(sqlite3* db) {
    if (db == nullptr) {
        return SQLITE_ERROR;
    }

    // 获取 fts5_api：通过 SELECT fts5(?1) 并绑定名为 "fts5_api_ptr" 的指针。
    // 这是 SQLite 官方文档推荐的自定义分词器注册方式。
    fts5_api* api = nullptr;
    sqlite3_stmt* stmt = nullptr;
    int rc = sqlite3_prepare_v2(db, "SELECT fts5(?1);", -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        return SQLITE_ERROR;
    }
    rc = sqlite3_bind_pointer(stmt, 1, static_cast<void*>(&api), "fts5_api_ptr",
                              nullptr);
    if (rc == SQLITE_OK) {
        rc = sqlite3_step(stmt);
    }
    sqlite3_finalize(stmt);
    if (rc != SQLITE_ROW || api == nullptr) {
        return SQLITE_ERROR;
    }

    static JiebaTokenizer g_ctx;  // pUserData 占位；实际上下文在 xCreate 中创建。

    fts5_tokenizer_v2 tokenizer;
    tokenizer.iVersion = 2;
    tokenizer.xCreate = jiebaXCreate;
    tokenizer.xDelete = jiebaXDelete;
    tokenizer.xTokenize = jiebaXTokenize;

    int rc2 = api->xCreateTokenizer_v2(
        api, "jieba", reinterpret_cast<void*>(&g_ctx), &tokenizer, nullptr);
    if (rc2 != SQLITE_OK) {
        return rc2;
    }
    return SQLITE_OK;
}

const cppjieba::Jieba* jiebaInstance() {
    if (!ensureJieba()) return nullptr;
    return g_jieba;
}

std::string jiebaInitError() {
    ensureJieba();
    return g_jiebaInitError;
}

}  // namespace docseek
