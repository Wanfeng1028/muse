package scheduler

import (
"fmt"
"strings"
"time"

"sentinel/internal/escalation"
"sentinel/internal/log"
)

// SetEscalation 设置告警升级策略；空表示禁用。
func (s *Scheduler) SetEscalation(policy []escalation.Level) {
s.mu.Lock()
defer s.mu.Unlock()
s.escalation = policy
}

// checkEscalations 扫描未关闭 incident，对达到阈值且未发送的级别做升级通知（幂等）。
func (s *Scheduler) checkEscalations() {
s.mu.Lock()
policy := s.escalation
s.mu.Unlock()
if len(policy) == 0 {
return
}

incs, err := s.store.ListOpenIncidents()
if err != nil {
log.Logger().Error("查询未关闭 incident 失败", "err", err)
return
}

now := time.Now()
for _, inc := range incs {
openedAt, err := time.Parse(time.RFC3339, inc.StartedAt)
if err != nil {
continue
}

sent, err := s.store.SentEscalationLevels(inc.ID)
if err != nil {
log.Logger().Error("查询升级记录失败", "incidentID", inc.ID, "err", err)
continue
}

due := escalation.DueLevels(openedAt, now, sent, policy)
for _, lv := range due {
if err := s.store.MarkEscalationSent(inc.ID, lv.AfterMinutes); err != nil {
log.Logger().Error("记录升级发送失败", "incidentID", inc.ID, "levelMinutes", lv.AfterMinutes, "err", err)
continue
}

m, err := s.store.GetMonitor(inc.MonitorID)
if err != nil {
log.Logger().Error("查询监控失败", "monitorID", inc.MonitorID, "err", err)
continue
}

m2 := m
m2.NotifyChannels = strings.Join(lv.Channels, ",")
at := now.UTC().Format(time.RFC3339)
errMsg := fmt.Sprintf("故障持续 %d 分钟未恢复（%s），已升级通知", lv.AfterMinutes, inc.StartError)
log.Logger().Info("告警升级", "monitorID", m.ID, "incidentID", inc.ID, "levelMinutes", lv.AfterMinutes)
s.notifyUnlessSilenced(m2, "escalated", m.Name, m.Target, at, errMsg)
}
}
}
