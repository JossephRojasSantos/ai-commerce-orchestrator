package printer

import (
	"fmt"
	"os"
	"text/tabwriter"

	"github.com/fatih/color"
	"github.com/josrojas/ai-commerce-cli/internal/checker"
)

func PrintResults(title string, results []checker.CheckResult) {
	PrintHeader(title)
	PrintTable(results)
	PrintSummary(results)
}

func PrintHeader(title string) {
	separator := "=================================================="
	fmt.Printf("\n%s\n%s\n%s\n\n", separator, title, separator)
}

func PrintResult(result checker.CheckResult) {
	fmt.Printf("%s %s (%dms): %s\n", colorizeStatus(result.Status), result.Name, result.LatencyMS, result.Message)
}

func PrintSuccess(message string) {
	fmt.Println(colorizeByStatus(checker.StatusOK, message))
}

func PrintError(message string) {
	fmt.Println(colorizeByStatus(checker.StatusFail, message))
}

func PrintWarn(message string) {
	fmt.Println(colorizeByStatus(checker.StatusWarn, message))
}

func PrintTable(results []checker.CheckResult) {
	tw := tabwriter.NewWriter(os.Stdout, 2, 2, 2, ' ', 0)
	fmt.Fprintln(tw, "Check\tEstado\tLatencia(ms)\tMensaje")
	fmt.Fprintln(tw, "-----\t------\t-----------\t-------")
	for _, r := range results {
		fmt.Fprintf(tw, "%s\t%s\t%d\t%s\n", r.Name, colorizeStatus(r.Status), r.LatencyMS, r.Message)
	}
	_ = tw.Flush()
}

func PrintSummary(results []checker.CheckResult) {
	ok := 0
	fail := 0
	warn := 0
	for _, r := range results {
		switch r.Status {
		case checker.StatusOK:
			ok++
		case checker.StatusFail:
			fail++
		case checker.StatusWarn:
			warn++
		}
	}

	fmt.Printf("\nResumen: OK=%d FAIL=%d WARN=%d\n", ok, fail, warn)
	if fail > 0 {
		PrintError("Se detectaron checks fallidos")
	} else if warn > 0 {
		PrintWarn("Hay checks en estado WARN")
	} else {
		PrintSuccess("Todos los checks en estado OK")
	}
	fmt.Println()
}

func colorizeStatus(status checker.Status) string {
	return colorizeByStatus(status, statusWithSymbol(status))
}

func colorizeByStatus(status checker.Status, text string) string {
	configureColors()
	switch status {
	case checker.StatusOK:
		return color.New(color.FgGreen).Sprint(text)
	case checker.StatusFail:
		return color.New(color.FgRed).Sprint(text)
	case checker.StatusWarn:
		return color.New(color.FgYellow).Sprint(text)
	default:
		return text
	}
}

func statusWithSymbol(status checker.Status) string {
	switch status {
	case checker.StatusOK:
		return "+ OK"
	case checker.StatusWarn:
		return "! WARN"
	case checker.StatusFail:
		return "x FAIL"
	default:
		return string(status)
	}
}

func configureColors() {
	stdoutInfo, err := os.Stdout.Stat()
	isTTY := err == nil && (stdoutInfo.Mode()&os.ModeCharDevice) != 0
	color.NoColor = os.Getenv("NO_COLOR") != "" || !isTTY
}
