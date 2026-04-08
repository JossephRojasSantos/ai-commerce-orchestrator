package checker

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestCheckOpenAIKey(t *testing.T) {
	okSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") == "Bearer valid" {
			w.WriteHeader(http.StatusOK)
			return
		}
		w.WriteHeader(http.StatusUnauthorized)
	}))
	defer okSrv.Close()

	missing := CheckOpenAIKey("", okSrv.URL, 2*time.Second)
	if missing.Status != StatusFail {
		t.Fatalf("expected fail for missing key, got %s", missing.Status)
	}

	invalid := CheckOpenAIKey("bad", okSrv.URL, 2*time.Second)
	if invalid.Status != StatusFail {
		t.Fatalf("expected fail for invalid key, got %s", invalid.Status)
	}

	valid := CheckOpenAIKey("valid", okSrv.URL, 2*time.Second)
	if valid.Status != StatusOK {
		t.Fatalf("expected pass for valid key, got %s", valid.Status)
	}
}
