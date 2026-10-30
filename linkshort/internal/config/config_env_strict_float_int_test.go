package config

import (
	"os"
	"testing"
)

func TestGetenvFloatStrict(t *testing.T) {
	const key = "LINKSHORT_TEST_STRICT_FLOAT"
	tests := []struct {
		name    string
		set     bool
		raw     string
		def     float64
		wantVal float64
		wantOK  bool
	}{
		{name: "unset", set: false, def: 3.25, wantVal: 3.25, wantOK: true},
		{name: "empty", set: true, raw: "", def: 3.25, wantVal: 3.25, wantOK: true},
		{name: "valid", set: true, raw: "12.5", def: 3.25, wantVal: 12.5, wantOK: true},
		{name: "invalid", set: true, raw: "abc", def: 3.25, wantVal: 0, wantOK: false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.set {
				t.Setenv(key, tt.raw)
			} else {
				os.Unsetenv(key)
			}
			got, ok := getenvFloat(key, tt.def)
			if got != tt.wantVal {
				t.Errorf("getenvFloat(%q) value = %v, want %v", key, got, tt.wantVal)
			}
			if ok != tt.wantOK {
				t.Errorf("getenvFloat(%q) ok = %v, want %v", key, ok, tt.wantOK)
			}
		})
	}
}

func TestGetenvIntStrict(t *testing.T) {
	const key = "LINKSHORT_TEST_STRICT_INT"
	tests := []struct {
		name    string
		set     bool
		raw     string
		def     int
		wantVal int
		wantOK  bool
	}{
		{name: "unset", set: false, def: 7, wantVal: 7, wantOK: true},
		{name: "empty", set: true, raw: "", def: 7, wantVal: 7, wantOK: true},
		{name: "valid", set: true, raw: "40", def: 7, wantVal: 40, wantOK: true},
		{name: "alpha", set: true, raw: "abc", def: 7, wantVal: 0, wantOK: false},
		{name: "float_string", set: true, raw: "1.5", def: 7, wantVal: 0, wantOK: false},
		{name: "trailing_letter", set: true, raw: "1x", def: 7, wantVal: 0, wantOK: false},
		{name: "surrounding_spaces", set: true, raw: " 40 ", def: 7, wantVal: 0, wantOK: false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.set {
				t.Setenv(key, tt.raw)
			} else {
				os.Unsetenv(key)
			}
			got, ok := getenvInt(key, tt.def)
			if got != tt.wantVal {
				t.Errorf("getenvInt(%q) value = %v, want %v", key, got, tt.wantVal)
			}
			if ok != tt.wantOK {
				t.Errorf("getenvInt(%q) ok = %v, want %v", key, ok, tt.wantOK)
			}
		})
	}
}
