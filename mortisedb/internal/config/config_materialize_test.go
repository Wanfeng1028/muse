package config

import "testing"

// TestViewMaterializeValidate 校验物化声明的校验逻辑与 refresh 默认值。
func TestViewMaterializeValidate(t *testing.T) {
	tests := []struct {
		name      string
		view      ViewConfig
		wantErr   bool
		wantRefr  string
		checkRefr bool
	}{
		{
			name:      "enabled 空 refresh 默认 on_sync",
			view:      ViewConfig{Name: "sales", SQL: "SELECT 1", Materialize: &MaterializeConfig{Enabled: true}},
			wantErr:   false,
			wantRefr:  "on_sync",
			checkRefr: true,
		},
		{
			name:    "manual 合法",
			view:    ViewConfig{Name: "sales", SQL: "SELECT 1", Materialize: &MaterializeConfig{Enabled: true, Refresh: "manual"}},
			wantErr: false,
		},
		{
			name:    "interval 合法",
			view:    ViewConfig{Name: "sales", SQL: "SELECT 1", Materialize: &MaterializeConfig{Enabled: true, Refresh: "interval:30m"}},
			wantErr: false,
		},
		{
			name:    "interval 非数字非法",
			view:    ViewConfig{Name: "sales", SQL: "SELECT 1", Materialize: &MaterializeConfig{Enabled: true, Refresh: "interval:abc"}},
			wantErr: true,
		},
		{
			name:    "every 前缀非法",
			view:    ViewConfig{Name: "sales", SQL: "SELECT 1", Materialize: &MaterializeConfig{Enabled: true, Refresh: "every:1h"}},
			wantErr: true,
		},
		{
			name:    "interval 0 非法",
			view:    ViewConfig{Name: "sales", SQL: "SELECT 1", Materialize: &MaterializeConfig{Enabled: true, Refresh: "interval:0s"}},
			wantErr: true,
		},
		{
			name:    "interval 负数非法",
			view:    ViewConfig{Name: "sales", SQL: "SELECT 1", Materialize: &MaterializeConfig{Enabled: true, Refresh: "interval:-5m"}},
			wantErr: true,
		},
		{
			name:    "启用物化名称非法",
			view:    ViewConfig{Name: "bad-name", SQL: "SELECT 1", Materialize: &MaterializeConfig{Enabled: true}},
			wantErr: true,
		},
		{
			name:    "未启用物化名称非法放行",
			view:    ViewConfig{Name: "bad-name", SQL: "SELECT 1", Materialize: &MaterializeConfig{Enabled: false}},
			wantErr: false,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c := &Config{Views: []ViewConfig{tt.view}}
			err := c.validate()
			if tt.wantErr {
				if err == nil {
					t.Fatalf("期望报错，实际通过")
				}
				return
			}
			if err != nil {
				t.Fatalf("期望通过，实际报错: %v", err)
			}
			if tt.checkRefr {
				if c.Views[0].Materialize == nil {
					t.Fatalf("Materialize 不应为 nil")
				}
				if c.Views[0].Materialize.Refresh != tt.wantRefr {
					t.Fatalf("refresh 期望 %q，实际 %q", tt.wantRefr, c.Views[0].Materialize.Refresh)
				}
			}
		})
	}
}
