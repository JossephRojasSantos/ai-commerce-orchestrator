package checker

import (
	"fmt"
	"net"
	"sort"
	"strings"
	"time"
)

type PortsAvailabilityChecker struct {
	Ports []int
}

func (c PortsAvailabilityChecker) Run() CheckResult {
	return CheckPortsAvailable(c.Ports)
}

func CheckPortsAvailable(ports []int) CheckResult {
	start := time.Now()
	occupied := make([]string, 0)
	for _, port := range ports {
		ln, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
		if err != nil {
			occupied = append(occupied, fmt.Sprintf("%d", port))
			continue
		}
		_ = ln.Close()
	}
	latency := time.Since(start)
	if len(occupied) > 0 {
		sort.Strings(occupied)
		return CheckResult{Name: "Puertos", Status: StatusFail, Message: "ocupados: " + strings.Join(occupied, ","), LatencyMS: latency.Milliseconds()}
	}
	return CheckResult{Name: "Puertos", Status: StatusOK, Message: "todos disponibles", LatencyMS: latency.Milliseconds()}
}
