
#include "docseek/token_locate.h"

namespace docseek {

std::vector<LocatedToken> claimTokenPositions(
    const std::string& text,
    const std::vector<std::string>& words,
    std::set<std::pair<std::string, size_t>>& claimed) {
    std::vector<LocatedToken> located;
    for (const std::string& w : words) {
        if (w.empty()) continue;
        size_t chosen = std::string::npos;
        for (size_t p = text.find(w, 0); p != std::string::npos;
             p = text.find(w, p + 1)) {
            if (claimed.find(std::make_pair(w, p)) == claimed.end()) {
                chosen = p;
                break;
            }
        }
        if (chosen != std::string::npos) {
            claimed.insert(std::make_pair(w, chosen));
            located.push_back(LocatedToken{w, chosen});
        }
    }
    return located;
}

std::vector<LocatedToken> claimTokenPositionsBatched(
    const std::string& text,
    const std::vector<std::string>& words,
    std::set<std::pair<std::string, size_t>>& claimed) {
    std::vector<LocatedToken> located;

    // 步骤 1：按 words 顺序去重（跳过空词），得到 uniq 词表（保持首次
    // 出现顺序），并统计每个 uniq 词在 words 中的出现次数 need。
    std::vector<std::string> uniq;
    std::vector<size_t> need;
    for (const std::string& w : words) {
        if (w.empty()) continue;
        size_t idx = uniq.size();
        for (size_t k = 0; k < uniq.size(); ++k) {
            if (uniq[k] == w) {
                idx = k;
                break;
            }
        }
        if (idx == uniq.size()) {
            uniq.push_back(w);
            need.push_back(1);
        } else {
            ++need[idx];
        }
    }

    // 步骤 2：对每个 uniq 词 w 做单遍全文扫描，按位置升序收集全部出现
    // 位置，跳过 claimed 中已存在 (w,p) 的位置，取前 need 个未被认领的
    // 位置：每个认领都插入 claimed，并按位置顺序存入 w 的位置队列。
    std::vector<std::vector<size_t>> queues(uniq.size());
    for (size_t k = 0; k < uniq.size(); ++k) {
        const std::string& w = uniq[k];
        size_t remaining = need[k];
        for (size_t p = text.find(w, 0); p != std::string::npos && remaining > 0;
             p = text.find(w, p + 1)) {
            if (claimed.find(std::make_pair(w, p)) == claimed.end()) {
                claimed.insert(std::make_pair(w, p));
                queues[k].push_back(p);
                --remaining;
            }
        }
    }

    // 步骤 3：按 words 原顺序遍历（跳过空词）：从该词的位置队列头部弹出
    // 一个位置组装 LocatedToken{w, pos} 追加到结果；若队列为空（定位失败）
    // 则跳过该词实例。返回结果顺序与 words 一致。
    std::vector<size_t> cursor(uniq.size(), 0);
    for (const std::string& w : words) {
        if (w.empty()) continue;
        size_t idx = uniq.size();
        for (size_t k = 0; k < uniq.size(); ++k) {
            if (uniq[k] == w) {
                idx = k;
                break;
            }
        }
        if (idx == uniq.size()) continue;
        if (cursor[idx] < queues[idx].size()) {
            size_t pos = queues[idx][cursor[idx]];
            ++cursor[idx];
            located.push_back(LocatedToken{w, pos});
        }
    }

    return located;
}

}  // namespace docseek
