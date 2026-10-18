package handlers

import (
	"net/http/httptest"
	"testing"

	"sentinel/internal/store"
)

func TestToMonitorAllNilDefaultsDeep2(t *testing.T) {
	in := &monitorInput{}
	m := in.toMonitor()

	if m.Kind != "http" {
		t.Fatalf("expected default Kind http, got %q", m.Kind)
	}
	if m.Method != "GET" {
		t.Fatalf("expected default Method GET, got %q", m.Method)
	}
	if m.ExpectedStatus != 200 {
		t.Fatalf("expected default ExpectedStatus 200, got %d", m.ExpectedStatus)
	}
	if m.TimeoutSec != 10 {
		t.Fatalf("expected default TimeoutSec 10, got %d", m.TimeoutSec)
	}
	if m.IntervalSec != 60 {
		t.Fatalf("expected default IntervalSec 60, got %d", m.IntervalSec)
	}
	if m.Enabled != 1 {
		t.Fatalf("expected default Enabled 1, got %d", m.Enabled)
	}
}

func TestToMonitorPartialOverrideDeep2(t *testing.T) {
	name := "svc"
	kind := "tcp"
	target := "db:5432"
	method := "POST"
	status := 201
	timeout := 5
	interval := 120
	enabled := 0

	in := &monitorInput{
		Name:           &name,
		Kind:           &kind,
		Target:         &target,
		Method:         &method,
		ExpectedStatus: &status,
		TimeoutSec:     &timeout,
		IntervalSec:    &interval,
		Enabled:        &enabled,
	}
	m := in.toMonitor()

	if m.Name != "svc" {
		t.Fatalf("expected Name svc, got %q", m.Name)
	}
	if m.Kind != "tcp" {
		t.Fatalf("expected Kind tcp, got %q", m.Kind)
	}
	if m.Target != "db:5432" {
		t.Fatalf("expected Target db:5432, got %q", m.Target)
	}
	if m.Method != "POST" {
		t.Fatalf("expected Method POST, got %q", m.Method)
	}
	if m.ExpectedStatus != 201 {
		t.Fatalf("expected ExpectedStatus 201, got %d", m.ExpectedStatus)
	}
	if m.TimeoutSec != 5 {
		t.Fatalf("expected TimeoutSec 5, got %d", m.TimeoutSec)
	}
	if m.IntervalSec != 120 {
		t.Fatalf("expected IntervalSec 120, got %d", m.IntervalSec)
	}
	if m.Enabled != 0 {
		t.Fatalf("expected Enabled 0, got %d", m.Enabled)
	}
}

func TestValidateMonitorNameEmptyDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "",
		Kind:           "http",
		Target:         "http://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
	}
	err := validateMonitor(m)
	if err == nil {
		t.Fatalf("expected error for empty name, got nil")
	}
	if err.Error() != "名称不能为空" {
		t.Fatalf("expected 名称不能为空, got %q", err.Error())
	}
}

func TestValidateMonitorKindInvalidDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "udp",
		Target:         "http://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
	}
	err := validateMonitor(m)
	if err == nil {
		t.Fatalf("expected error for invalid kind, got nil")
	}
	if err.Error() != "kind 只能为 http 或 tcp" {
		t.Fatalf("expected kind 只能为 http 或 tcp, got %q", err.Error())
	}
}

func TestValidateMonitorTargetEmptyDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "http",
		Target:         "",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
	}
	err := validateMonitor(m)
	if err == nil {
		t.Fatalf("expected error for empty target, got nil")
	}
	if err.Error() != "目标地址不能为空" {
		t.Fatalf("expected 目标地址不能为空, got %q", err.Error())
	}
}

func TestValidateMonitorHTTPSchemeMissingDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "http",
		Target:         "example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
	}
	err := validateMonitor(m)
	if err == nil {
		t.Fatalf("expected error for missing scheme, got nil")
	}
	if err.Error() != "http 目标必须以 http:// 或 https:// 开头" {
		t.Fatalf("expected http 目标必须以 http:// 或 https:// 开头, got %q", err.Error())
	}
}

func TestValidateMonitorTCPNoColonDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "tcp",
		Target:         "localhost",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
	}
	err := validateMonitor(m)
	if err == nil {
		t.Fatalf("expected error for tcp target without colon, got nil")
	}
	if err.Error() != "tcp 目标必须为 host:port 形式" {
		t.Fatalf("expected tcp 目标必须为 host:port 形式, got %q", err.Error())
	}
}

func TestValidateMonitorMethodInvalidDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "http",
		Target:         "http://example.com",
		Method:         "DELETE",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
	}
	err := validateMonitor(m)
	if err == nil {
		t.Fatalf("expected error for invalid method, got nil")
	}
	if err.Error() != "method 仅支持 GET/HEAD/POST" {
		t.Fatalf("expected method 仅支持 GET/HEAD/POST, got %q", err.Error())
	}
}

func TestValidateMonitorMethodEmptyAllowedDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "http",
		Target:         "http://example.com",
		Method:         "",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
	}
	err := validateMonitor(m)
	if err != nil {
		t.Fatalf("expected empty method to be valid, got error %v", err)
	}
}

func TestValidateMonitorExpectedStatusLowOutOfRangeDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "http",
		Target:         "http://example.com",
		Method:         "GET",
		ExpectedStatus: 99,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
	}
	if err := validateMonitor(m); err == nil {
		t.Fatalf("expected error for ExpectedStatus 99, got nil")
	}
}

func TestValidateMonitorExpectedStatusHighOutOfRangeDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "http",
		Target:         "http://example.com",
		Method:         "GET",
		ExpectedStatus: 600,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
	}
	if err := validateMonitor(m); err == nil {
		t.Fatalf("expected error for ExpectedStatus 600, got nil")
	}
}

func TestValidateMonitorTimeoutLowOutOfRangeDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "http",
		Target:         "http://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     0,
		IntervalSec:    60,
		Enabled:        1,
	}
	if err := validateMonitor(m); err == nil {
		t.Fatalf("expected error for TimeoutSec 0, got nil")
	}
}

func TestValidateMonitorTimeoutHighOutOfRangeDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "http",
		Target:         "http://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     61,
		IntervalSec:    60,
		Enabled:        1,
	}
	if err := validateMonitor(m); err == nil {
		t.Fatalf("expected error for TimeoutSec 61, got nil")
	}
}

func TestValidateMonitorIntervalLowOutOfRangeDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "http",
		Target:         "http://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    9,
		Enabled:        1,
	}
	if err := validateMonitor(m); err == nil {
		t.Fatalf("expected error for IntervalSec 9, got nil")
	}
}

func TestValidateMonitorIntervalHighOutOfRangeDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "http",
		Target:         "http://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    3601,
		Enabled:        1,
	}
	if err := validateMonitor(m); err == nil {
		t.Fatalf("expected error for IntervalSec 3601, got nil")
	}
}

func TestValidateMonitorEnabledInvalidDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "http",
		Target:         "http://example.com",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        2,
	}
	if err := validateMonitor(m); err == nil {
		t.Fatalf("expected error for Enabled 2, got nil")
	}
}

func TestValidateMonitorValidHTTPDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "http",
		Target:         "https://example.com",
		Method:         "HEAD",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
	}
	if err := validateMonitor(m); err != nil {
		t.Fatalf("expected valid http monitor, got error %v", err)
	}
}

func TestValidateMonitorValidTCPDeep2(t *testing.T) {
	m := &store.Monitor{
		Name:           "x",
		Kind:           "tcp",
		Target:         "127.0.0.1:8080",
		Method:         "",
		ExpectedStatus: 200,
		TimeoutSec:     1,
		IntervalSec:    3600,
		Enabled:        0,
	}
	if err := validateMonitor(m); err != nil {
		t.Fatalf("expected valid tcp monitor, got error %v", err)
	}
}

func TestParseIDValidDeep2(t *testing.T) {
	req := httptest.NewRequest("GET", "/monitors/123", nil)
	req.SetPathValue("id", "123")
	id, ok := parseID(req)
	if !ok {
		t.Fatalf("expected ok true for id 123")
	}
	if id != 123 {
		t.Fatalf("expected id 123, got %d", id)
	}
}

func TestParseIDEmptyDeep2(t *testing.T) {
	req := httptest.NewRequest("GET", "/monitors/", nil)
	req.SetPathValue("id", "")
	id, ok := parseID(req)
	if ok {
		t.Fatalf("expected ok false for empty id")
	}
	if id != 0 {
		t.Fatalf("expected id 0 for empty id, got %d", id)
	}
}

func TestParseIDNonNumericDeep2(t *testing.T) {
	req := httptest.NewRequest("GET", "/monitors/abc", nil)
	req.SetPathValue("id", "abc")
	id, ok := parseID(req)
	if ok {
		t.Fatalf("expected ok false for non-numeric id")
	}
	if id != 0 {
		t.Fatalf("expected id 0 for non-numeric id, got %d", id)
	}
}

func TestParseIDZeroDeep2(t *testing.T) {
	req := httptest.NewRequest("GET", "/monitors/0", nil)
	req.SetPathValue("id", "0")
	id, ok := parseID(req)
	if ok {
		t.Fatalf("expected ok false for id 0")
	}
	if id != 0 {
		t.Fatalf("expected id 0, got %d", id)
	}
}

func TestParseIDNegativeDeep2(t *testing.T) {
	req := httptest.NewRequest("GET", "/monitors/-5", nil)
	req.SetPathValue("id", "-5")
	id, ok := parseID(req)
	if ok {
		t.Fatalf("expected ok false for negative id")
	}
	if id != 0 {
		t.Fatalf("expected id 0 for negative id, got %d", id)
	}
}
