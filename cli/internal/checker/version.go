package checker

import (
	"fmt"
	"regexp"
	"strconv"
)

var versionRegexp = regexp.MustCompile(`(\d+)\.(\d+)`)

func parseVersion(output string) (int, int, error) {
	match := versionRegexp.FindStringSubmatch(output)
	if len(match) < 3 {
		return 0, 0, fmt.Errorf("version no encontrada")
	}
	major, err := strconv.Atoi(match[1])
	if err != nil {
		return 0, 0, err
	}
	minor, err := strconv.Atoi(match[2])
	if err != nil {
		return 0, 0, err
	}
	return major, minor, nil
}

func versionAtLeast(major, minor, minMajor, minMinor int) bool {
	if major > minMajor {
		return true
	}
	if major < minMajor {
		return false
	}
	return minor >= minMinor
}
