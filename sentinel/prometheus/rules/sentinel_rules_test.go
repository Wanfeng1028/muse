package rules_test

import (
	"os"
	"strings"
	"testing"
	"time"

	"gopkg.in/yaml.v3"
)

type ruleFile struct {
	Groups []ruleGroup `yaml:"groups"`
}

type ruleGroup struct {
	Name  string     `yaml:"name"`
	Rules []ruleItem `yaml:"rules"`
}

type ruleItem struct {
	Alert       string            `yaml:"alert"`
	Expr        string            `yaml:"expr"`
	For         string            `yaml:"for"`
	Labels      map[string]string `yaml:"labels"`
	Annotations map[string]string `yaml:"annotations"`
}

func TestSentinelRulesFile(t *testing.T) {
	raw, err := os.ReadFile("sentinel.yml")
	if err != nil {
		t.Fatal(err)
	}

	var parsed ruleFile
	if err := yaml.Unmarshal(raw, &parsed); err != nil {
		t.Fatalf("unmarshal sentinel.yml: %v", err)
	}

	if len(parsed.Groups) != 1 {
		t.Fatalf("expected exactly 1 group, got %d", len(parsed.Groups))
	}
	g := parsed.Groups[0]
	if g.Name != "sentinel" {
		t.Fatalf("expected group name %q, got %q", "sentinel", g.Name)
	}
	if len(g.Rules) != 6 {
		t.Fatalf("expected exactly 6 rules, got %d", len(g.Rules))
	}

	metricSubstr := map[string]string{
		"SentinelInstanceDown":            `up{job="sentinel"}`,
		"SentinelChecksStalled":           `sentinel_checks_total`,
		"SentinelWebhookQueueBacklogHigh": `sentinel_webhook_queue_backlog`,
		"SentinelWebhookFailureRateHigh":  `sentinel_webhook_failures_total`,
		"SentinelCheckFailuresSpike":      `sentinel_check_failures_total`,
		"SentinelAPI5xxRateHigh":          `sentinel_http_requests_total`,
	}

	expected := map[string]bool{
		"SentinelInstanceDown":            false,
		"SentinelChecksStalled":           false,
		"SentinelWebhookQueueBacklogHigh": false,
		"SentinelWebhookFailureRateHigh":  false,
		"SentinelCheckFailuresSpike":      false,
		"SentinelAPI5xxRateHigh":          false,
	}

	for _, r := range g.Rules {
		if _, ok := expected[r.Alert]; !ok {
			t.Fatalf("unexpected alert %q", r.Alert)
		}
		if expected[r.Alert] {
			t.Fatalf("duplicate alert %q", r.Alert)
		}
		expected[r.Alert] = true

		if strings.TrimSpace(r.Expr) == "" {
			t.Fatalf("alert %q: empty expr", r.Alert)
		}
		if strings.TrimSpace(r.For) == "" {
			t.Fatalf("alert %q: empty for", r.Alert)
		}
		if _, err := time.ParseDuration(r.For); err != nil {
			t.Fatalf("alert %q: for %q is not a valid duration: %v", r.Alert, r.For, err)
		}

		sev := r.Labels["severity"]
		if sev != "critical" && sev != "warning" {
			t.Fatalf("alert %q: severity %q must be critical or warning", r.Alert, sev)
		}
		if strings.TrimSpace(r.Annotations["summary"]) == "" {
			t.Fatalf("alert %q: empty annotations.summary", r.Alert)
		}
		if strings.TrimSpace(r.Annotations["description"]) == "" {
			t.Fatalf("alert %q: empty annotations.description", r.Alert)
		}

		substr, ok := metricSubstr[r.Alert]
		if !ok {
			t.Fatalf("alert %q: missing metric substring mapping", r.Alert)
		}
		if !strings.Contains(r.Expr, substr) {
			t.Fatalf("alert %q: expr %q must contain %q", r.Alert, r.Expr, substr)
		}

		if r.Alert == "SentinelWebhookQueueBacklogHigh" {
			if !strings.Contains(r.Expr, "> 50") {
				t.Fatalf("alert %q: expr %q must contain threshold %q", r.Alert, r.Expr, "> 50")
			}
		}
	}

	for name, seen := range expected {
		if !seen {
			t.Fatalf("missing expected alert %q", name)
		}
	}
}
