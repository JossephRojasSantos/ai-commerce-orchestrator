package checker

import (
	"net"
	"testing"
)

func TestCheckPortsAvailable(t *testing.T) {
	ln, err := net.Listen("tcp", ":0")
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()
	port := ln.Addr().(*net.TCPAddr).Port

	result := CheckPortsAvailable([]int{port})
	if result.Status != StatusFail {
		t.Fatalf("expected fail for occupied port, got %s", result.Status)
	}
}
