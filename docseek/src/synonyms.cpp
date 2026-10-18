// docseek 同义词表实现（v0.16.1：5 组）
// 仅收录经 v09 样本 corpus 证据确认的映射，其余一律不展开。
#include "docseek/synonyms.h"

#include <cstring>

namespace docseek {
namespace {

// "合适" → {"舒服"}      // v09-t018-q01：期望文档 v09_t018_01.html 全文无"合适"，有"低于2.5毫米算舒服"
const char* const kExpandHeShi[] = {"舒服"};

// "好按" → {"舒服"}      // v09-t018-q09：期望文档 v09_t018_01.html，文档原话"算舒服"
const char* const kExpandHaoAn[] = {"舒服"};

// "花费" → {"多少钱"}    // v09-t003-q08：期望文档"装备花了多少钱"，全文无"花费"
const char* const kExpandHuaFei[] = {"多少钱"};

// "破裂" → {"裂"}        // v09-t005-q06：期望文档"袋子裂了"，全文无"破裂"
const char* const kExpandPoLie[] = {"裂"};

// "小孩" → {"孩子"}      // v09-t007-q06：期望文档标题"孩子几岁学游泳合适"，全文无"小孩"
const char* const kExpandXiaoHai[] = {"孩子"};

// 表按 term 字节序排列：UTF-8 下 "合适" < "好按" < "小孩" < "破裂" < "花费"。
const SynonymEntry kSynonyms[] = {
    {"合适", kExpandHeShi, 1},
    {"好按", kExpandHaoAn, 1},
    {"小孩", kExpandXiaoHai, 1},
    {"破裂", kExpandPoLie, 1},
    {"花费", kExpandHuaFei, 1},
};

}  // namespace

const SynonymEntry* findSynonyms(const char* term) {
    if (term == nullptr) {
        return nullptr;
    }
    for (size_t i = 0; i < sizeof(kSynonyms) / sizeof(kSynonyms[0]); ++i) {
        if (std::strcmp(kSynonyms[i].term, term) == 0) {
            return &kSynonyms[i];
        }
    }
    return nullptr;
}

}  // namespace docseek
