package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestParseFloatEnvUnsetDefaultDeep2(t *testing.T) {
	const name = "SENTINEL_DEEP2_FLOAT_UNSET"
	os.Unsetenv(name)
	got, err := parseFloatEnv(name, 1.5, 0, 10)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != 1.5 {
		t.Fatalf("expected default 1.5, got %v", got)
	}
}

func TestParseFloatEnvBlankDefaultDeep2(t *testing.T) {
	const name = "SENTINEL_DEEP2_FLOAT_BLANK"
	t.Setenv(name, "   ")
	got, err := parseFloatEnv(name, 2.25, 0, 10)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != 2.25 {
		t.Fatalf("expected default 2.25 for blank value, got %v", got)
	}
}

func TestParseFloatEnvBoundariesDeep2(t *testing.T) {
	const nameMin = "SENTINEL_DEEP2_FLOAT_MIN"
	t.Setenv(nameMin, "0")
	gotMin, err := parseFloatEnv(nameMin, 5, 0, 10)
	if err != nil {
		t.Fatalf("unexpected error at min boundary: %v", err)
	}
	if gotMin != 0 {
		t.Fatalf("expected min boundary 0, got %v", gotMin)
	}

	const nameMax = "SENTINEL_DEEP2_FLOAT_MAX"
	t.Setenv(nameMax, "10")
	gotMax, err := parseFloatEnv(nameMax, 5, 0, 10)
	if err != nil {
		t.Fatalf("unexpected error at max boundary: %v", err)
	}
	if gotMax != 10 {
		t.Fatalf("expected max boundary 10, got %v", gotMax)
	}
}

func TestParseFloatEnvBelowMinDeep2(t *testing.T) {
	const name = "SENTINEL_DEEP2_FLOAT_BELOW_MIN"
	t.Setenv(name, "-0.01")
	_, err := parseFloatEnv(name, 5, 0, 10)
	if err == nil {
		t.Fatalf("expected error for value below min")
	}
	if !strings.Contains(err.Error(), name) {
		t.Fatalf("expected error to mention variable name %q, got %q", name, err.Error())
	}
	if !strings.Contains(err.Error(), "0") || !strings.Contains(err.Error(), "10") {
		t.Fatalf("expected error to mention range [0,10], got %q", err.Error())
	}
}

func TestParseFloatEnvAboveMaxDeep2(t *testing.T) {
	const name = "SENTINEL_DEEP2_FLOAT_ABOVE_MAX"
	t.Setenv(name, "10.5")
	_, err := parseFloatEnv(name, 5, 0, 10)
	if err == nil {
		t.Fatalf("expected error for value above max")
	}
	if !strings.Contains(err.Error(), name) {
		t.Fatalf("expected error to mention variable name %q, got %q", name, err.Error())
	}
}

func TestParseFloatEnvInvalidDeep2(t *testing.T) {
	const name = "SENTINEL_DEEP2_FLOAT_ABC"
	t.Setenv(name, "abc")
	_, err := parseFloatEnv(name, 5, 0, 10)
	if err == nil {
		t.Fatalf("expected error for non-numeric value")
	}
	if !strings.Contains(err.Error(), name) {
		t.Fatalf("expected error to mention variable name %q, got %q", name, err.Error())
	}
}

func TestParseIntEnvFractionalFailsDeep2(t *testing.T) {
	const name = "SENTINEL_DEEP2_INT_FRACTION"
	t.Setenv(name, "3.5")
	_, err := parseIntEnv(name, 1, 0, 10)
	if err == nil {
		t.Fatalf("expected error for fractional integer value 3.5")
	}
	if !strings.Contains(err.Error(), name) {
		t.Fatalf("expected error to mention variable name %q, got %q", name, err.Error())
	}
}

func TestParseIntEnvNegativeRangeDeep2(t *testing.T) {
	const name = "SENTINEL_DEEP2_INT_NEG"
	t.Setenv(name, "-5")
	got, err := parseIntEnv(name, 0, -10, -1)
	if err != nil {
		t.Fatalf("unexpected error for -5 inside [-10,-1]: %v", err)
	}
	if got != -5 {
		t.Fatalf("got %d, want -5", got)
	}
	// 范围外的值应报错
	t.Setenv(name, "-11")
	_, err = parseIntEnv(name, 0, -10, -1)
	if err == nil {
		t.Fatalf("expected error for -11 outside [-10,-1]")
	}
	if !strings.Contains(err.Error(), name) {
		t.Fatalf("expected error to mention variable name %q, got %q", name, err.Error())
	}

	const nameOK = "SENTINEL_DEEP2_INT_NEG_OK"
	t.Setenv(nameOK, "-5")
	got, err = parseIntEnv(nameOK, 0, -10, -1)
	if err != nil {
		t.Fatalf("unexpected error for -5 within [-10,-1]: %v", err)
	}
	if got != -5 {
		t.Fatalf("expected -5, got %d", got)
	}
}

func TestParseIntEnvBoundariesDeep2(t *testing.T) {
	const nameMin = "SENTINEL_DEEP2_INT_MIN"
	t.Setenv(nameMin, "1")
	gotMin, err := parseIntEnv(nameMin, 7, 1, 10)
	if err != nil {
		t.Fatalf("unexpected error at min boundary: %v", err)
	}
	if gotMin != 1 {
		t.Fatalf("expected min boundary 1, got %d", gotMin)
	}

	const nameMax = "SENTINEL_DEEP2_INT_MAX"
	t.Setenv(nameMax, "10")
	gotMax, err := parseIntEnv(nameMax, 7, 1, 10)
	if err != nil {
		t.Fatalf("unexpected error at max boundary: %v", err)
	}
	if gotMax != 10 {
		t.Fatalf("expected max boundary 10, got %d", gotMax)
	}
}

func TestParseBoolEnvCaseInsensitiveTrueDeep2(t *testing.T) {
	cases := []string{"YES", "On", "TrUe", "1"}
	for _, v := range cases {
		name := "SENTINEL_DEEP2_BOOL_TRUE"
		t.Setenv(name, v)
		got, err := parseBoolEnv(name, false)
		if err != nil {
			t.Fatalf("unexpected error for %q: %v", v, err)
		}
		if !got {
			t.Fatalf("expected true for %q, got false", v)
		}
	}
}

func TestParseBoolEnvWhitespaceDeep2(t *testing.T) {
	const name = "SENTINEL_DEEP2_BOOL_WS"
	t.Setenv(name, "  true  ")
	got, err := parseBoolEnv(name, false)
	if err != nil {
		t.Fatalf("unexpected error for padded true: %v", err)
	}
	if !got {
		t.Fatalf("expected true for padded \"  true  \", got false")
	}

	const nameOff = "SENTINEL_DEEP2_BOOL_WS_OFF"
	t.Setenv(nameOff, "\tOFF\t")
	gotOff, err := parseBoolEnv(nameOff, true)
	if err != nil {
		t.Fatalf("unexpected error for padded off: %v", err)
	}
	if gotOff {
		t.Fatalf("expected false for padded \"\\tOFF\\t\", got true")
	}
}

func TestParseBoolEnvFalseValuesDeep2(t *testing.T) {
	cases := []string{"0", "false", "no", "off", "FALSE", "No"}
	for _, v := range cases {
		name := "SENTINEL_DEEP2_BOOL_FALSE"
		t.Setenv(name, v)
		got, err := parseBoolEnv(name, true)
		if err != nil {
			t.Fatalf("unexpected error for %q: %v", v, err)
		}
		if got {
			t.Fatalf("expected false for %q, got true", v)
		}
	}
}

func TestParseBoolEnvInvalidDeep2(t *testing.T) {
	const name = "SENTINEL_DEEP2_BOOL_MAYBE"
	t.Setenv(name, "maybe")
	_, err := parseBoolEnv(name, true)
	if err == nil {
		t.Fatalf("expected error for invalid bool \"maybe\"")
	}
	if !strings.Contains(err.Error(), name) {
		t.Fatalf("expected error to mention variable name %q, got %q", name, err.Error())
	}
}

func TestParseBoolEnvUnsetDefaultDeep2(t *testing.T) {
	const nameTrue = "SENTINEL_DEEP2_BOOL_UNSET_TRUE"
	os.Unsetenv(nameTrue)
	gotTrue, err := parseBoolEnv(nameTrue, true)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !gotTrue {
		t.Fatalf("expected default true, got false")
	}

	const nameFalse = "SENTINEL_DEEP2_BOOL_UNSET_FALSE"
	os.Unsetenv(nameFalse)
	gotFalse, err := parseBoolEnv(nameFalse, false)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if gotFalse {
		t.Fatalf("expected default false, got true")
	}
}

func TestParseEscalationEmptyDeep2(t *testing.T) {
	got, err := parseEscalation("")
	if err != nil {
		t.Fatalf("unexpected error for empty string: %v", err)
	}
	if got != nil {
		t.Fatalf("expected nil for empty string, got %#v", got)
	}

	gotWS, err := parseEscalation("   ")
	if err != nil {
		t.Fatalf("unexpected error for whitespace string: %v", err)
	}
	if gotWS != nil {
		t.Fatalf("expected nil for whitespace string, got %#v", gotWS)
	}
}

func TestParseEscalationValidDeep2(t *testing.T) {
	got, err := parseEscalation("5:webhook;10:sms,wecom")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("expected 2 levels, got %d", len(got))
	}
	if got[0].AfterMinutes != 5 {
		t.Fatalf("expected first level minute 5, got %d", got[0].AfterMinutes)
	}
	if len(got[0].Channels) != 1 || got[0].Channels[0] != "webhook" {
		t.Fatalf("expected first level channels [webhook], got %#v", got[0].Channels)
	}
	if got[1].AfterMinutes != 10 {
		t.Fatalf("expected second level minute 10, got %d", got[1].AfterMinutes)
	}
	if len(got[1].Channels) != 2 || got[1].Channels[0] != "sms" || got[1].Channels[1] != "wecom" {
		t.Fatalf("expected second level channels [sms wecom] in order, got %#v", got[1].Channels)
	}
}

func TestParseEscalationLowercaseDedupeOrderDeep2(t *testing.T) {
	got, err := parseEscalation("5:WEBHOOK,webhook,Sms;10:SMS")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("expected 2 levels, got %d", len(got))
	}
	if len(got[0].Channels) != 2 || got[0].Channels[0] != "webhook" || got[0].Channels[1] != "sms" {
		t.Fatalf("expected deduped lowercase order [webhook sms], got %#v", got[0].Channels)
	}
	if len(got[1].Channels) != 1 || got[1].Channels[0] != "sms" {
		t.Fatalf("expected second level [sms], got %#v", got[1].Channels)
	}
}

func TestParseEscalationNonIncreasingDeep2(t *testing.T) {
	_, err := parseEscalation("10:webhook;5:sms")
	if err == nil {
		t.Fatalf("expected error for non-increasing minutes")
	}
	// 错误信息提及"严格递增"即可，不强求原文片段回显
	if !strings.Contains(err.Error(), "严格递增") {
		t.Fatalf("expected error to mention 严格递增, got %q", err.Error())
	}
}

func TestParseEscalationZeroMinuteDeep2(t *testing.T) {
	_, err := parseEscalation("0:webhook")
	if err == nil {
		t.Fatalf("expected error for minute 0 below minimum 1")
	}
	if !strings.Contains(err.Error(), "0:webhook") {
		t.Fatalf("expected error to mention original segment \"0:webhook\", got %q", err.Error())
	}
}

func TestParseEscalationUnknownChannelDeep2(t *testing.T) {
	_, err := parseEscalation("5:carrier-pigeon")
	if err == nil {
		t.Fatalf("expected error for unknown channel")
	}
	if !strings.Contains(err.Error(), "carrier-pigeon") {
		t.Fatalf("expected error to mention unknown channel, got %q", err.Error())
	}
}

func TestParseEscalationMissingColonDeep2(t *testing.T) {
	_, err := parseEscalation("5webhook")
	if err == nil {
		t.Fatalf("expected error for segment missing colon")
	}
	if !strings.Contains(err.Error(), "5webhook") {
		t.Fatalf("expected error to mention original segment \"5webhook\", got %q", err.Error())
	}
}

func TestParseEscalationEmptyChannelDeep2(t *testing.T) {
	_, err := parseEscalation("5:")
	if err == nil {
		t.Fatalf("expected error for empty channel list")
	}
	if !strings.Contains(err.Error(), "5:") {
		t.Fatalf("expected error to mention original segment \"5:\", got %q", err.Error())
	}
}

func TestParseEscalationEmptyFragmentDeep2(t *testing.T) {
	_, err := parseEscalation("5:webhook;;10:sms")
	if err == nil {
		t.Fatalf("expected error for empty fragment between semicolons")
	}
	// 空片段报错即可，不强求回显周边片段
	if !strings.Contains(err.Error(), "非法的升级配置片段") {
		t.Fatalf("expected error to mention 非法的升级配置片段, got %q", err.Error())
	}
}

func TestParseEscalationMinuteTooLargeDeep2(t *testing.T) {
	_, err := parseEscalation("525601:webhook")
	if err == nil {
		t.Fatalf("expected error for minute 525601 above max 525600")
	}
	if !strings.Contains(err.Error(), "525601:webhook") {
		t.Fatalf("expected error to mention original segment, got %q", err.Error())
	}
}

func TestParseEscalationMinuteAtMaxDeep2(t *testing.T) {
	got, err := parseEscalation("525600:webhook")
	if err != nil {
		t.Fatalf("unexpected error at max minute boundary: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("expected 1 level, got %d", len(got))
	}
	if got[0].AfterMinutes != 525600 {
		t.Fatalf("expected minute 525600, got %d", got[0].AfterMinutes)
	}
	if len(got[0].Channels) != 1 || got[0].Channels[0] != "webhook" {
		t.Fatalf("expected channels [webhook], got %#v", got[0].Channels)
	}
}

func TestParseEscalationNonNumericMinuteDeep2(t *testing.T) {
	_, err := parseEscalation("abc:webhook")
	if err == nil {
		t.Fatalf("expected error for non-numeric minute")
	}
	if !strings.Contains(err.Error(), "abc:webhook") {
		t.Fatalf("expected error to mention original segment, got %q", err.Error())
	}
}

func TestAddrJoinDeep2(t *testing.T) {
	c := Config{Host: "127.0.0.1", Port: 8080}
	if got := c.Addr(); got != "127.0.0.1:8080" {
		t.Fatalf("expected \"127.0.0.1:8080\", got %q", got)
	}

	c2 := Config{Host: "example.com", Port: 443}
	if got := c2.Addr(); got != "example.com:443" {
		t.Fatalf("expected \"example.com:443\", got %q", got)
	}
}

func TestResolveProjectRootInsideRepoDeep2(t *testing.T) {
	got, err := resolveProjectRoot()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got == "" {
		t.Fatalf("expected non-empty project root")
	}
	if _, statErr := os.Stat(filepath.Join(got, "go.mod")); statErr != nil {
		t.Fatalf("expected resolved root %q to contain go.mod: %v", got, statErr)
	}
	if !filepath.IsAbs(got) {
		t.Fatalf("expected absolute project root path, got %q", got)
	}
}
