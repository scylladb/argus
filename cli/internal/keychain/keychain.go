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

	// cfAccessClientIDKey is the keychain account name for the Cloudflare
	// Access service-token client ID, stored by "auth headless".
	cfAccessClientIDKey = "cf-access-client-id"

	// cfAccessClientSecretKey is the keychain account name for the Cloudflare
	// Access service-token client secret, stored by "auth headless".
	cfAccessClientSecretKey = "cf-access-client-secret"

	// cfAccessArgusTokenKey is the keychain account name for the Argus API
	// token that accompanies the CF Access service-token headers, stored by
	// "auth headless".
	cfAccessArgusTokenKey = "cf-access-argus-token"
)

// Sentinel errors returned by the keychain package.
var (
	// ErrNotFound is returned by Load when no session token is present in the
	// keychain.  Callers should treat this as a signal to re-authenticate
	// rather than a hard failure.
	ErrNotFound = errors.New("keychain: session token not found")

	// ErrPATNotFound is returned by LoadPAT when no PAT is stored.
	ErrPATNotFound = errors.New("keychain: PAT not found")

	// ErrStoring is returned when the OS keychain rejects a Store call.
	ErrStoring = errors.New("keychain: storing session token")

	// ErrDeleting is returned when the OS keychain rejects a Delete call.
	ErrDeleting = errors.New("keychain: deleting session token")

	// ErrDeletingPAT is returned when the OS keychain rejects a DeletePAT call.
	ErrDeletingPAT = errors.New("keychain: deleting PAT")

	// ErrCFAccessNotFound is returned by LoadCFAccess when one or more of the
	// headless CF Access credentials are missing from the keychain.
	ErrCFAccessNotFound = errors.New("keychain: CF Access headless credentials not found")

	// ErrStoringCFAccess is returned when persisting headless CF Access
	// credentials fails.
	ErrStoringCFAccess = errors.New("keychain: storing CF Access headless credentials")
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
			return "", ErrPATNotFound
		}
		return "", errors.Join(ErrPATNotFound, err)
	}
	if token == "" {
		// An empty string was stored — treat it as absent and clean it up.
		_ = keyring.Delete(serviceName, patKey)
		return "", ErrPATNotFound
	}
	return token, nil
}

func StorePAT(token string) error {
	if err := keyring.Set(serviceName, patKey, token); err != nil {
		return errors.Join(ErrStoring, err)
	}
	return nil
}

// DeletePAT removes the PAT from the system keychain.
// It is a no-op (returns nil) if no PAT is currently stored.
func DeletePAT() error {
	err := keyring.Delete(serviceName, patKey)
	if err != nil && !errors.Is(err, keyring.ErrNotFound) {
		return errors.Join(ErrDeletingPAT, err)
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

// StoreCFAccess persists the three headless CF Access credentials
// (client ID, client secret, and Argus API token) in the system keychain.
// All three are required; an error storing any one of them is returned
// immediately.
func StoreCFAccess(clientID, clientSecret, argusToken string) error {
	for _, kv := range []struct {
		key, val string
	}{
		{cfAccessClientIDKey, clientID},
		{cfAccessClientSecretKey, clientSecret},
		{cfAccessArgusTokenKey, argusToken},
	} {
		if err := keyring.Set(serviceName, kv.key, kv.val); err != nil {
			return errors.Join(ErrStoringCFAccess, err)
		}
	}
	return nil
}

// LoadCFAccess retrieves all three headless CF Access credentials from the
// system keychain.  If any of the three is missing or empty the function
// returns ErrCFAccessNotFound.
func LoadCFAccess() (clientID, clientSecret, argusToken string, err error) {
	clientID, err = keyring.Get(serviceName, cfAccessClientIDKey)
	if err != nil || clientID == "" {
		return "", "", "", ErrCFAccessNotFound
	}

	clientSecret, err = keyring.Get(serviceName, cfAccessClientSecretKey)
	if err != nil || clientSecret == "" {
		return "", "", "", ErrCFAccessNotFound
	}

	argusToken, err = keyring.Get(serviceName, cfAccessArgusTokenKey)
	if err != nil || argusToken == "" {
		return "", "", "", ErrCFAccessNotFound
	}

	return clientID, clientSecret, argusToken, nil
}

// HasCFAccess reports whether all three headless CF Access credentials are
// present in the system keychain.
func HasCFAccess() bool {
	_, _, _, err := LoadCFAccess()
	return err == nil
}

// DeleteCFAccess removes all three headless CF Access credentials from the
// system keychain.  Missing entries are silently ignored.
func DeleteCFAccess() error {
	for _, key := range []string{
		cfAccessClientIDKey,
		cfAccessClientSecretKey,
		cfAccessArgusTokenKey,
	} {
		if err := keyring.Delete(serviceName, key); err != nil && !errors.Is(err, keyring.ErrNotFound) {
			return errors.Join(ErrDeleting, err)
		}
	}
	return nil
}
