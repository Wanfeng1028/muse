package config

import "testing"

func TestGetBoolEnv(t *testing.T) {
	tests := []struct {
		name   string
		key    string
		value  string
		set    bool
		def    bool
		wantB  bool
		wantOk bool
	}{
		{"unset default true", "SB_TEST_GETBOOLENV_1", "", false, true, true, true},
		{"unset default false", "SB_TEST_GETBOOLENV_2", "", false, false, false, true},
		{"true", "SB_TEST_GETBOOLENV_3", "true", true, false, true, true},
		{"TRUE", "SB_TEST_GETBOOLENV_4", "TRUE", true, false, true, true},
		{"whitespace yes", "SB_TEST_GETBOOLENV_5", "  yes ", true, false, true, true},
		{"1", "SB_TEST_GETBOOLENV_6", "1", true, false, true, true},
		{"on", "SB_TEST_GETBOOLENV_7", "on", true, false, true, true},
		{"false", "SB_TEST_GETBOOLENV_8", "false", true, true, false, true},
		{"0", "SB_TEST_GETBOOLENV_9", "0", true, true, false, true},
		{"no", "SB_TEST_GETBOOLENV_10", "no", true, true, false, true},
		{"off", "SB_TEST_GETBOOLENV_11", "off", true, true, false, true},
		{"whitespace FALSE", "SB_TEST_GETBOOLENV_12", "  FALSE  ", true, true, false, true},
		{"abc", "SB_TEST_GETBOOLENV_13", "abc", true, true, false, false},
		{"2", "SB_TEST_GETBOOLENV_14", "2", true, true, false, false},
		{"maybe", "SB_TEST_GETBOOLENV_15", "maybe", true, false, false, false},
		{"t", "SB_TEST_GETBOOLENV_16", "t", true, true, false, false},
		{"whitespace only", "SB_TEST_GETBOOLENV_17", "   ", true, true, false, false},
		{"empty string", "SB_TEST_GETBOOLENV_18", "", true, true, true, true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.set {
				t.Setenv(tt.key, tt.value)
			}
			gotB, gotOk := getBoolEnv(tt.key, tt.def)
			if gotB != tt.wantB || gotOk != tt.wantOk {
				t.Errorf("getBoolEnv(%q, %v) = (%v, %v), want (%v, %v)", tt.key, tt.def, gotB, gotOk, tt.wantB, tt.wantOk)
			}
		})
	}
}
