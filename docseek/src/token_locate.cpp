
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

}  // namespace docseek
