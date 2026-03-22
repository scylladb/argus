BINARY     := argus
BUILD_DIR  := bin
MAIN       := .

.PHONY: all build fmt lint clean

all: build

## build: compile the binary into bin/
build:
	go build -o $(BUILD_DIR)/$(BINARY) $(MAIN)

## fmt: format all Go source files
fmt:
	golangci-lint fmt ./...

## lint: run golangci-lint on all packages
lint:
	golangci-lint run ./...

## clean: remove build artifacts
clean:
	rm -rf $(BUILD_DIR)
