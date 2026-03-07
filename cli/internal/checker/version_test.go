package checker

import "testing"

func TestParseVersion(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		major   int
		minor   int
		wantErr bool
	}{
		{name: "docker", input: "Docker version 28.5.2", major: 28, minor: 5},
		{name: "compose", input: "Docker Compose version 2.35.1", major: 2, minor: 35},
		{name: "invalid", input: "no version", wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			major, minor, err := parseVersion(tt.input)
			if tt.wantErr {
				if err == nil {
					t.Fatal("expected error")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if major != tt.major || minor != tt.minor {
				t.Fatalf("got %d.%d, want %d.%d", major, minor, tt.major, tt.minor)
			}
		})
	}
}

func TestVersionAtLeast(t *testing.T) {
	if !versionAtLeast(2, 30, 2, 20) {
		t.Fatal("expected true")
	}
	if versionAtLeast(2, 10, 2, 20) {
		t.Fatal("expected false")
	}
	if versionAtLeast(1, 99, 2, 20) {
		t.Fatal("expected false")
	}
}
