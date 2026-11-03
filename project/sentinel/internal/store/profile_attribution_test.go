package store

import (
	"testing"
	"time"
)

func TestClassifyFailureCause(t *testing.T) {
	cases := []struct {
		name  string
		input string
		want  string
	}{
		{"deadline exceeded", "context deadline exceeded", "timeout"},
		{"client timeout", "Client.Timeout exceeded while awaiting headers", "timeout"},
		{"dns no such host", "dial tcp: lookup api.example.com: no such host", "dns"},
		{"connection refused", "dial tcp 1.2.3.4:80: connect: connection refused", "connection"},
		{"connection reset", "connection reset by peer", "connection"},
		{"cert expired", "x509: certificate has expired or is not yet valid", "cert"},
		{"cert chinese", "证书将于 3 天后过期，低于预警阈值 7 天", "cert"},
		{"keyword", "关键字断言失败：响应体不包含关键字", "keyword"},
		{"http 503", "状态码不符: 期望 200, 实际 503", "http_5xx"},
		{"http 404", "状态码不符: 期望 200, 实际 404", "other"},
		{"empty", "", "other"},
		{"generic", "构造请求失败: xxx", "other"},
		{"keyword priority over timeout", "关键字不匹配且 timeout exceeded", "keyword"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := ClassifyFailureCause(tc.input)
			if got != tc.want {
				t.Fatalf("ClassifyFailureCause(%q) = %q, want %q", tc.input, got, tc.want)
			}
		})
	}
}

func TestMonthlySLA_Attribution(t *testing.T) {
	now := time.Now().UTC()
	year, month := now.Year(), int(now.Month())

	st, db := newProfileTestStore(t)

	monID := int64(1)

	day15 := time.Date(year, time.Month(month), 15, 12, 0, 0, 0, time.UTC)
	for i := 0; i < 3; i++ {
		if _, err := st.InsertCheck(Check{
			MonitorID: monID,
			CheckedAt: day15.Add(time.Duration(i) * time.Minute).Format(time.RFC3339),
			Ok:        1,
			LatencyMs: 100,
		}); err != nil {
			t.Fatalf("InsertCheck ok#%d error: %v", i, err)
		}
	}
	if _, err := st.InsertCheck(Check{
		MonitorID: monID,
		CheckedAt: day15.Add(3 * time.Minute).Format(time.RFC3339),
		Ok:        0,
		LatencyMs: 0,
	}); err != nil {
		t.Fatalf("InsertCheck fail error: %v", err)
	}

	startedAt := day15.Format(time.RFC3339)
	for _, se := range []string{
		"context deadline exceeded",
		"状态码不符: 期望 200, 实际 503",
	} {
		if _, err := db.Exec(
			`INSERT INTO incidents(monitor_id, started_at, ended_at, downtime_sec, start_error) VALUES (?,?,?,?,?)`,
			monID, startedAt, nil, nil, se,
		); err != nil {
			t.Fatalf("insert incident %q error: %v", se, err)
		}
	}

	got, err := st.MonthlySLA(monID, year, month)
	if err != nil {
		t.Fatalf("MonthlySLA error: %v", err)
	}
	if got.DownIncidents != 2 {
		t.Fatalf("DownIncidents = %d, want 2", got.DownIncidents)
	}
	if got.Attribution["timeout"] != 1 {
		t.Fatalf("Attribution[timeout] = %d, want 1", got.Attribution["timeout"])
	}
	if got.Attribution["http_5xx"] != 1 {
		t.Fatalf("Attribution[http_5xx] = %d, want 1", got.Attribution["http_5xx"])
	}
	if got.AttributionPct["timeout"] != 50.0 {
		t.Fatalf("AttributionPct[timeout] = %v, want 50.0", got.AttributionPct["timeout"])
	}
	if got.AttributionPct["http_5xx"] != 50.0 {
		t.Fatalf("AttributionPct[http_5xx] = %v, want 50.0", got.AttributionPct["http_5xx"])
	}
}
