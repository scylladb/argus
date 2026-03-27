package keychain

import (
	"errors"

	"github.com/zalando/go-keyring"
)

const (
	// serviceName is the identifier used in the OS keychain for all Argus CLI
	// credentials.  It appears as the "application" or "service" label in the
	// system keychain UI.
	serviceName = "argus-cli"

	// sessionKey is the keychain account name under which the Argus session
	// token is stored.
	sessionKey = "session"

	// patKey is the keychain account name which hosts the Argus API token
	patKey = "pat"

	// cfTokenKey is the keychain account name under which the Cloudflare
	// Access JWT is stored so it can be reused across invocations without
	// having to re-run cloudflared.
	cfTokenKey = "cf_token"
)

// Sentinel errors returned by the keychain package.
var (
	// ErrNotFound is returned by Load when no session token is present in the
	// keychain.  Callers should treat this as a signal to re-authenticate
	// rather than a hard failure.
	ErrNotFound = errors.New("keychain: session token not found")

	// ErrCFTokenNotFound is returned by LoadCFToken when no CF Access JWT is
	// present in the keychain.
	ErrCFTokenNotFound = errors.New("keychain: CF token not found")

	// ErrStoring is returned when the OS keychain rejects a Store call.
	ErrStoring = errors.New("keychain: storing session token")

	// ErrStoringCFToken is returned when the OS keychain rejects a StoreCFToken call.
	ErrStoringCFToken = errors.New("keychain: storing CF token")

	// ErrDeleting is returned when the OS keychain rejects a Delete call.
	ErrDeleting = errors.New("keychain: deleting session token")

	// ErrDeletingCFToken is returned when the OS keychain rejects a DeleteCFToken call.
	ErrDeletingCFToken = errors.New("keychain: deleting CF token")
)

// Store persists token in the system keychain under the argus-cli service.
// It overwrites any previously stored value.
func Store(token string) error {
	if err := keyring.Set(serviceName, sessionKey, token); err != nil {
		return errors.Join(ErrStoring, err)
	}
	return nil
}

// Load retrieves the session token from the system keychain.
// If no token has been stored yet it returns ("", ErrNotFound).
func Load() (string, error) {
	token, err := keyring.Get(serviceName, sessionKey)
	if err != nil {
		if errors.Is(err, keyring.ErrNotFound) {
			return "", ErrNotFound
		}
		return "", errors.Join(ErrNotFound, err)
	}
	return token, nil
}

func LoadPAT() (string, error) {
	token, err := keyring.Get(serviceName, patKey)
	if err != nil {
		if errors.Is(err, keyring.ErrNotFound) {
			return "", ErrNotFound
		}
		return "", errors.Join(ErrNotFound, err)
	}
	return token, nil
}

func StorePAT(token string) error {
	if err := keyring.Set(serviceName, patKey, token); err != nil {
		return errors.Join(ErrStoring, err)
	}
	return nil
}

// Delete removes the session token from the system keychain.
// It is a no-op (returns nil) if no token is currently stored.
func Delete() error {
	err := keyring.Delete(serviceName, sessionKey)
	if err != nil && !errors.Is(err, keyring.ErrNotFound) {
		return errors.Join(ErrDeleting, err)
	}
	return nil
}

// StoreCFToken persists the Cloudflare Access JWT in the system keychain so
// it can be reused on subsequent invocations without re-running cloudflared.
// It overwrites any previously stored value.
func StoreCFToken(token string) error {
	if err := keyring.Set(serviceName, cfTokenKey, token); err != nil {
		return errors.Join(ErrStoringCFToken, err)
	}
	return nil
}

// LoadCFToken retrieves the Cloudflare Access JWT from the system keychain.
// If no token has been stored yet it returns ("", ErrCFTokenNotFound).
func LoadCFToken() (string, error) {
	token, err := keyring.Get(serviceName, cfTokenKey)
	if err != nil {
		if errors.Is(err, keyring.ErrNotFound) {
			return "", ErrCFTokenNotFound
		}
		return "", errors.Join(ErrCFTokenNotFound, err)
	}
	return token, nil
}

// DeleteCFToken removes the Cloudflare Access JWT from the system keychain.
// It is a no-op (returns nil) if no token is currently stored.
func DeleteCFToken() error {
	err := keyring.Delete(serviceName, cfTokenKey)
	if err != nil && !errors.Is(err, keyring.ErrNotFound) {
		return errors.Join(ErrDeletingCFToken, err)
	}
	return nil
}
