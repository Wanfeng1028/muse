package config

import (
	"os"
	"testing"
)

func TestGetenvBoolStrict(t *testing.T) {
	tests := []struct {
		name string
		key  string
		val  string
		set  bool
		def  bool
		want bool
		ok   bool
	}{
		{"未设置", "LINKSHORT_TEST_STRICT_UNSET", "", false, true, true, true},
		{"空串", "LINKSHORT_TEST_STRICT_EMPTY", "", true, false, false, true},
		{"true", "LINKSHORT_TEST_STRICT_TRUE", "true", true, false, true, true},
		{"false", "LINKSHORT_TEST_STRICT_FALSE", "false", true, true, false, true},
		{"maybe", "LINKSHORT_TEST_STRICT_MAYBE", "maybe", true, true, false, false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.set {
				t.Setenv(tt.key, tt.val)
			} else {
				os.Unsetenv(tt.key)
			}
			got, ok := getenvBool(tt.key, tt.def)
			if got != tt.want || ok != tt.ok {
				t.Errorf("getenvBool(%q, %v) = (%v, %v), want (%v, %v)", tt.key, tt.def, got, ok, tt.want, tt.ok)
			}
		})
	}
}
