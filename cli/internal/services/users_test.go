package services_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func newUserSvc(t *testing.T, mux *http.ServeMux) *services.UserService {
	t.Helper()
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))
	return services.NewUserService(client, ca)
}

// userServiceMux serves three users for get/list tests.
func userServiceMux(t *testing.T) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/users", func(w http.ResponseWriter, _ *http.Request) {
		jsonOK(t, w, models.UsersMap{
			"u1": {ID: "u1", Username: "alice", Email: "alice@scylladb.com", FullName: "Alice A"},
			"u2": {ID: "u2", Username: "bob", Email: "bob@scylladb.com", FullName: "Bob B"},
			"u3": {ID: "u3", Username: "carol", Email: "carol@scylladb.com", FullName: "Carol C"},
		})
	})
	return mux
}

func TestUserService_ListUsers_SortedByUsername(t *testing.T) {
	t.Parallel()
	svc := newUserSvc(t, userServiceMux(t))

	users, err := svc.ListUsers(context.Background())
	require.NoError(t, err)
	require.Len(t, users, 3)
	assert.Equal(t, []string{"alice", "bob", "carol"},
		[]string{users[0].Username, users[1].Username, users[2].Username})
}

func TestUserService_GetUser(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name    string
		field   string
		value   string
		wantID  string
		wantErr bool
	}{
		{"by username", "username", "Alice", "u1", false},
		{"by uuid", "uuid", "U2", "u2", false},
		{"by email", "email", "carol@scylladb.com", "u3", false},
		{"no match", "username", "dave", "", true},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			svc := newUserSvc(t, userServiceMux(t))
			u, err := svc.GetUser(context.Background(), tc.field, tc.value)
			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			assert.Equal(t, tc.wantID, u.ID)
		})
	}
}

func TestUserService_GetUser_Ambiguous(t *testing.T) {
	t.Parallel()

	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/users", func(w http.ResponseWriter, _ *http.Request) {
		jsonOK(t, w, models.UsersMap{
			"u1": {ID: "u1", Username: "alice", Email: "shared@scylladb.com"},
			"u2": {ID: "u2", Username: "bob", Email: "shared@scylladb.com"},
		})
	})
	svc := newUserSvc(t, mux)

	_, err := svc.GetUser(context.Background(), "email", "shared@scylladb.com")
	require.Error(t, err)
}

func TestUserService_SearchUsers(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name          string
		term          string
		wantUsernames []string
	}{
		{"username substring", "ali", []string{"alice"}},
		{"case-insensitive", "ALI", []string{"alice"}},
		{"full name substring", "Bob B", []string{"bob"}},
		{"email domain matches all", "@scylladb.com", []string{"alice", "bob", "carol"}},
		{"empty term returns all", "", []string{"alice", "bob", "carol"}},
		{"no match", "dave", []string{}},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			svc := newUserSvc(t, userServiceMux(t))
			got, err := svc.SearchUsers(context.Background(), tc.term)
			require.NoError(t, err)

			names := make([]string, len(got))
			for i, u := range got {
				names[i] = u.Username
			}
			assert.Equal(t, tc.wantUsernames, names)
		})
	}
}

func TestUserService_SearchUsers_DiacriticInsensitive(t *testing.T) {
	t.Parallel()

	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/users", func(w http.ResponseWriter, _ *http.Request) {
		jsonOK(t, w, models.UsersMap{
			"u1": {ID: "u1", Username: "lkaczmarek", Email: "lk@scylladb.com", FullName: "Łukasz Częstochowski"},
			"u2": {ID: "u2", Username: "jnovak", Email: "jn@scylladb.com", FullName: "Jiří Dvořák"},
		})
	})

	cases := []struct {
		name     string
		term     string
		wantUser string
	}{
		{"ascii term matches diacritic name", "lukasz", "lkaczmarek"},
		{"partial folded surname", "czest", "lkaczmarek"},
		{"czech name folded", "jiri dvorak", "jnovak"},
		{"diacritic term matches too", "Łukasz", "lkaczmarek"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			svc := newUserSvc(t, mux)
			got, err := svc.SearchUsers(context.Background(), tc.term)
			require.NoError(t, err)
			require.Len(t, got, 1)
			assert.Equal(t, tc.wantUser, got[0].Username)
		})
	}
}
