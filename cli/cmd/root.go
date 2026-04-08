package cmd

import (
	"errors"
	"fmt"
	"os"
	"strings"

	"github.com/spf13/cobra"
)

var (
	version   = "dev"
	commit    = "none"
	buildDate = "unknown"
	verbose   bool
)

type usageError struct {
	err error
}

func (e usageError) Error() string {
	return e.err.Error()
}

func (e usageError) Unwrap() error {
	return e.err
}

var rootCmd = &cobra.Command{
	Use:           "ai-commerce-cli",
	Short:         "CLI de reproducibilidad para AI-Commerce Orchestrator",
	SilenceUsage:  true,
	SilenceErrors: true,
}

func Execute() int {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		if isUsageError(err) {
			return 2
		}
		return 1
	}
	return 0
}

func init() {
	rootCmd.Version = fmt.Sprintf("%s (commit %s, built %s)", version, commit, buildDate)
	rootCmd.PersistentFlags().BoolVar(&verbose, "verbose", false, "Habilita salida detallada")
	rootCmd.SetFlagErrorFunc(func(cmd *cobra.Command, err error) error {
		return usageError{err: err}
	})
}

func isUsageError(err error) bool {
	var flagErr usageError
	if errors.As(err, &flagErr) {
		return true
	}

	msg := strings.ToLower(err.Error())
	usageMarkers := []string{
		"unknown command",
		"unknown shorthand flag",
		"unknown flag",
		"required flag",
		"accepts ",
	}
	for _, marker := range usageMarkers {
		if strings.Contains(msg, marker) {
			return true
		}
	}
	return false
}
