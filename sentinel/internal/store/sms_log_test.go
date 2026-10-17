package store

import (
	"testing"
	"time"

)

func TestRecordAndListSMSLog(t *testing.T) {
	st := newTestStore(t)

	if err := st.RecordSMSLog("13800138000", "code 1111", "aliyun", "success", ""); err != nil {
		t.Fatalf("record 1: %v", err)
	}
	if err := st.RecordSMSLog("13800138000", "code 2222", "aliyun", "failed", "gateway timeout"); err != nil {
		t.Fatalf("record 2: %v", err)
	}
	if err := st.RecordSMSLog("13900139000", "code 3333", "twilio", "success", ""); err != nil {
		t.Fatalf("record 3: %v", err)
	}

	all, _, err := st.ListSMSLog("", "", 10, 0)
	if err != nil {
		t.Fatalf("list all: %v", err)
	}
	if len(all) != 3 {
		t.Fatalf("list all len = %d, want 3", len(all))
	}
	if !(all[0].ID > all[1].ID && all[1].ID > all[2].ID) {
		t.Fatalf("list all not ordered by id desc: %d, %d, %d", all[0].ID, all[1].ID, all[2].ID)
	}
	if all[0].Phone != "13900139000" || all[0].Message != "code 3333" {
		t.Fatalf("newest entry = %+v, want phone 13900139000 message code 3333", all[0])
	}

	byPhone, _, err := st.ListSMSLog("13800138000", "", 10, 0)
	if err != nil {
		t.Fatalf("list by phone: %v", err)
	}
	if len(byPhone) != 2 {
		t.Fatalf("list by phone len = %d, want 2", len(byPhone))
	}
	for _, e := range byPhone {
		if e.Phone != "13800138000" {
			t.Fatalf("list by phone returned entry with phone %q", e.Phone)
		}
	}

	byStatus, _, err := st.ListSMSLog("", "failed", 10, 0)
	if err != nil {
		t.Fatalf("list by status: %v", err)
	}
	if len(byStatus) != 1 {
		t.Fatalf("list by status len = %d, want 1", len(byStatus))
	}
	if byStatus[0].Status != "failed" {
		t.Fatalf("list by status returned status %q, want failed", byStatus[0].Status)
	}
	if byStatus[0].Message != "code 2222" {
		t.Fatalf("list by status returned message %q, want code 2222", byStatus[0].Message)
	}

	limited, _, err := st.ListSMSLog("", "", 2, 0)
	if err != nil {
		t.Fatalf("list limit 2: %v", err)
	}
	if len(limited) != 2 {
		t.Fatalf("list limit 2 len = %d, want 2", len(limited))
	}
	if limited[0].Phone != "13900139000" || limited[1].Phone != "13800138000" {
		t.Fatalf("list limit 2 = %q, %q, want 13900139000, 13800138000", limited[0].Phone, limited[1].Phone)
	}

	offset, _, err := st.ListSMSLog("", "", 10, 2)
	if err != nil {
		t.Fatalf("list offset 2: %v", err)
	}
	if len(offset) != 1 {
		t.Fatalf("list offset 2 len = %d, want 1", len(offset))
	}
	if offset[0].Phone != "13800138000" || offset[0].Message != "code 1111" {
		t.Fatalf("list offset 2 = %+v, want phone 13800138000 message code 1111", offset[0])
	}
}

func TestSMSLogEntryFields(t *testing.T) {
	st := newTestStore(t)

	before := time.Now().Add(-time.Minute)
	if err := st.RecordSMSLog("13800138000", "hello world", "aliyun", "failed", "invalid number"); err != nil {
		t.Fatalf("record: %v", err)
	}
	after := time.Now().Add(time.Minute)

	list, _, err := st.ListSMSLog("13800138000", "failed", 10, 0)
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("list len = %d, want 1", len(list))
	}
	e := list[0]

	if e.Phone != "13800138000" {
		t.Fatalf("Phone = %q, want 13800138000", e.Phone)
	}
	if e.Message != "hello world" {
		t.Fatalf("Message = %q, want hello world", e.Message)
	}
	if e.Provider != "aliyun" {
		t.Fatalf("Provider = %q, want aliyun", e.Provider)
	}
	if e.Status != "failed" {
		t.Fatalf("Status = %q, want failed", e.Status)
	}
	if e.Error != "invalid number" {
		t.Fatalf("Error = %q, want invalid number", e.Error)
	}
	if e.ID <= 0 {
		t.Fatalf("ID = %d, want > 0", e.ID)
	}

	parsed, err := time.Parse(time.RFC3339, e.CreatedAt)
	if err != nil {
		t.Fatalf("CreatedAt %q not RFC3339: %v", e.CreatedAt, err)
	}
	if parsed.Before(before) || parsed.After(after) {
		t.Fatalf("CreatedAt %v not in [%v, %v]", parsed, before, after)
	}
}