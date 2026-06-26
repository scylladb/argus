package cmd

import (
	"github.com/scylladb/argus/cli/cmd/search"
)

func init() {
	search.Register(rootCmd)
}
