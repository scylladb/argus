package services

import (
	"strings"
	"unicode"

	"golang.org/x/text/runes"
	"golang.org/x/text/transform"
	"golang.org/x/text/unicode/norm"
)

// latinReplacer maps Latin letters that do NOT decompose under Unicode NFD
// (i.e. they are single code points with no combining-mark form) to their
// closest ASCII equivalent. Diacritics that DO decompose (á, ę, ř, ž, ...) are
// handled by the NFD + combining-mark removal below and need no entry here.
var latinReplacer = strings.NewReplacer(
	"Ł", "L", "ł", "l",
	"Ø", "O", "ø", "o",
	"Đ", "D", "đ", "d",
	"Ð", "D", "ð", "d",
	"Þ", "Th", "þ", "th",
	"ß", "ss",
	"Æ", "Ae", "æ", "ae",
	"Œ", "Oe", "œ", "oe",
	"Ĳ", "Ij", "ĳ", "ij",
	"İ", "I", "ı", "i",
	"Ŀ", "L", "ŀ", "l",
	"ĸ", "k",
)

// normalizeLatin folds a string to a diacritic-free, lower-cased ASCII-ish form
// for accent-insensitive matching. For example "Łukasz Częstochowski" becomes
// "lukasz czestochowski", so a search for "lukasz czestochowski" (or a partial
// "czest") matches regardless of the diacritics in the stored name.
func normalizeLatin(s string) string {
	s = latinReplacer.Replace(s)
	t := transform.Chain(norm.NFD, runes.Remove(runes.In(unicode.Mn)), norm.NFC)
	folded, _, err := transform.String(t, s)
	if err != nil {
		folded = s
	}
	return strings.ToLower(folded)
}
