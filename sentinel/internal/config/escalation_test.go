package config

import "testing"

func TestParseEscalationValid(t *testing.T) {
levels, err := parseEscalation("15:wecom;30:wecom,smtp")
if err != nil {
t.Fatalf("unexpected error: %v", err)
}
if len(levels) != 2 {
t.Fatalf("expected 2 levels, got %d", len(levels))
}
if levels[0].AfterMinutes != 15 || len(levels[0].Channels) != 1 || levels[0].Channels[0] != "wecom" {
t.Fatalf("level0 wrong: %+v", levels[0])
}
if levels[1].AfterMinutes != 30 || len(levels[1].Channels) != 2 {
t.Fatalf("level1 wrong: %+v", levels[1])
}
}

func TestParseEscalationInvalid(t *testing.T) {
cases := []string{
"30:wecom;15:wecom", // 分钟不递增
"0:wecom", // 分钟为 0
"15:foo,bar", // 渠道全非法
"15", // 格式错
"15:", // 渠道为空
}
for _, c := range cases {
if _, err := parseEscalation(c); err == nil {
t.Fatalf("expected error for %q", c)
}
}
}
