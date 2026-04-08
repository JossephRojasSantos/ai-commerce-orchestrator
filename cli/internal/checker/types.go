package checker

type Status string

const (
	StatusOK   Status = "OK"
	StatusFail Status = "FAIL"
	StatusWarn Status = "WARN"
)

type CheckResult struct {
	Name      string
	Status    Status
	Message   string
	LatencyMS int64
}

type Checker interface {
	Run() CheckResult
}

func HasFailures(results []CheckResult) bool {
	for _, r := range results {
		if r.Status == StatusFail {
			return true
		}
	}
	return false
}
