package checker

import (
	"fmt"
	"os/exec"
	"strings"
	"time"
)

type DockerVersionChecker struct {
	MinMajor int
	MinMinor int
}

func (c DockerVersionChecker) Run() CheckResult {
	return CheckDockerVersion(c.MinMajor, c.MinMinor)
}

func CheckDockerVersion(minMajor, minMinor int) CheckResult {
	start := time.Now()
	path, err := exec.LookPath("docker")
	if err != nil {
		return CheckResult{Name: "Docker Engine", Status: StatusFail, Message: "docker no instalado", LatencyMS: time.Since(start).Milliseconds()}
	}

	out, err := exec.Command(path, "--version").CombinedOutput()
	latency := time.Since(start)
	if err != nil {
		return CheckResult{Name: "Docker Engine", Status: StatusFail, Message: strings.TrimSpace(string(out)), LatencyMS: latency.Milliseconds()}
	}

	major, minor, err := parseVersion(string(out))
	if err != nil {
		return CheckResult{Name: "Docker Engine", Status: StatusFail, Message: "no se pudo parsear version", LatencyMS: latency.Milliseconds()}
	}
	if !versionAtLeast(major, minor, minMajor, minMinor) {
		return CheckResult{Name: "Docker Engine", Status: StatusFail, Message: fmt.Sprintf("version %d.%d (< %d.%d)", major, minor, minMajor, minMinor), LatencyMS: latency.Milliseconds()}
	}
	return CheckResult{Name: "Docker Engine", Status: StatusOK, Message: fmt.Sprintf("version %d.%d", major, minor), LatencyMS: latency.Milliseconds()}
}
