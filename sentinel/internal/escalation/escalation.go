package escalation

import "time"

// Level 升级链的一级。
type Level struct {
AfterMinutes int
Channels []string
}

// DueLevels 返回从 openedAt 到 now 已达到阈值、且不在 sent 中的级别（保持 policy 原顺序）。
func DueLevels(openedAt, now time.Time, sent []int, policy []Level) []Level {
sentSet := make(map[int]bool, len(sent))
for _, s := range sent {
sentSet[s] = true
}

elapsed := now.Sub(openedAt)
var out []Level
for _, lv := range policy {
if lv.AfterMinutes <= 0 {
continue
}
if sentSet[lv.AfterMinutes] {
continue
}
if elapsed < time.Duration(lv.AfterMinutes)*time.Minute {
continue
}
out = append(out, lv)
}
return out
}
