#include "docseek/locator.h"

#include <algorithm>
#include <string>
#include <vector>

#include "docseek/query_parser.h"

namespace docseek {

Locator::Locator(Database& db, Searcher& searcher)
    : db_(db), searcher_(searcher) {}

std::vector<Passage> Locator::locate(const std::string& rawQuery,
                                     const LocateOptions& opts) {
    std::vector<Passage> result;

    ParsedQuery pq = parseNaturalQuery(rawQuery);

    // 若解析后无词，退化为整串作为关键词。
    if (pq.keywords.empty() && pq.phrases.empty()) {
        // rawQuery 去空白后仍为空则直接返回。
        bool hasNonSpace = false;
        for (char c : rawQuery) {
            if (c != ' ' && c != '\t' && c != '\n' && c != '\r' && c != '\f' &&
                c != '\v') {
                hasNonSpace = true;
                break;
            }
        }
        if (!hasNonSpace) return result;
        pq.keywords.push_back(rawQuery);
    }

    // 拼接 recallQuery。
    std::string recallQuery;
    for (const auto& k : pq.keywords) {
        if (!recallQuery.empty()) recallQuery.push_back(' ');
        recallQuery += k;
    }
    for (const auto& p : pq.phrases) {
        if (!recallQuery.empty()) recallQuery.push_back(' ');
        recallQuery += p;
    }

    if (recallQuery.empty()) return result;

    std::vector<Hit> hits = searcher_.search(recallQuery, opts.recallDocs);

    std::vector<Passage> all;
    for (const auto& h : hits) {
        std::optional<std::string> content = db_.getContentById(h.doc_id);
        if (!content.has_value()) continue;
        std::vector<Passage> passages =
            rankPassages(h.doc_id, h.path, *content, pq, 3);
        for (auto& p : passages) {
            all.push_back(std::move(p));
        }
    }

    std::sort(all.begin(), all.end(),
              [](const Passage& a, const Passage& b) {
                  if (a.score != b.score) return a.score > b.score;
                  return a.line_start < b.line_start;
              });

    if (opts.limit > 0 && static_cast<int>(all.size()) > opts.limit) {
        all.resize(opts.limit);
    }
    return all;
}

}  // namespace docseek
