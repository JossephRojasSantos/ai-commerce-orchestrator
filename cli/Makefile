APP_NAME := ai-commerce-cli
BIN_DIR := ../bin
DIST_DIR := ../dist
GO := $(shell command -v go 2>/dev/null || echo /opt/homebrew/bin/go)
GOLANGCI_LINT := $(shell command -v golangci-lint 2>/dev/null)
GOLANGCI_LINT_VERSION := v1.64.8

VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
COMMIT ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo none)
BUILD_DATE ?= $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")
LDFLAGS := -X 'github.com/josrojas/ai-commerce-cli/cmd.version=$(VERSION)' -X 'github.com/josrojas/ai-commerce-cli/cmd.commit=$(COMMIT)' -X 'github.com/josrojas/ai-commerce-cli/cmd.buildDate=$(BUILD_DATE)'

.PHONY: build build-all test test-cover lint clean run-setup run-health run-ingest

build:
	@mkdir -p $(BIN_DIR)
	$(GO) build -ldflags "$(LDFLAGS)" -o $(BIN_DIR)/$(APP_NAME) .

build-all: build
	@mkdir -p $(DIST_DIR)
	GOOS=darwin GOARCH=arm64 $(GO) build -ldflags "$(LDFLAGS)" -o $(DIST_DIR)/$(APP_NAME)-darwin-arm64 .
	GOOS=darwin GOARCH=amd64 $(GO) build -ldflags "$(LDFLAGS)" -o $(DIST_DIR)/$(APP_NAME)-darwin-amd64 .
	GOOS=linux GOARCH=amd64 $(GO) build -ldflags "$(LDFLAGS)" -o $(DIST_DIR)/$(APP_NAME)-linux-amd64 .

test:
	$(GO) test ./...

test-cover:
	$(GO) test -coverprofile=coverage.out ./internal/checker/...

lint:
	@if [ -n "$(GOLANGCI_LINT)" ]; then \
		$(GOLANGCI_LINT) run ./...; \
	else \
		$(GO) run github.com/golangci/golangci-lint/cmd/golangci-lint@$(GOLANGCI_LINT_VERSION) run ./...; \
	fi

clean:
	rm -f $(BIN_DIR)/$(APP_NAME)
	rm -f $(DIST_DIR)/$(APP_NAME)-darwin-arm64
	rm -f $(DIST_DIR)/$(APP_NAME)-darwin-amd64
	rm -f $(DIST_DIR)/$(APP_NAME)-linux-amd64
	rm -f coverage.out

run-setup: build
	$(BIN_DIR)/$(APP_NAME) setup

run-health: build
	$(BIN_DIR)/$(APP_NAME) health

run-ingest: build
	$(BIN_DIR)/$(APP_NAME) ingest
