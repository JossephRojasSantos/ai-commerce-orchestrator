package checker

import "testing"

func TestHasFailures(t *testing.T) {
	if HasFailures([]CheckResult{{Status: StatusOK}, {Status: StatusWarn}}) {
		t.Fatal("expected no failures")
	}
	if !HasFailures([]CheckResult{{Status: StatusOK}, {Status: StatusFail}}) {
		t.Fatal("expected failure")
	}
}

func TestCheckWhatsAppVerifyToken(t *testing.T) {
	if got := CheckWhatsAppVerifyToken("").Status; got != StatusFail {
		t.Fatalf("expected fail, got %s", got)
	}
	if got := CheckWhatsAppVerifyToken("abc").Status; got != StatusOK {
		t.Fatalf("expected pass, got %s", got)
	}
}
