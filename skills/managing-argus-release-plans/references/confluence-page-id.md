# Decoding a Confluence `/wiki/x/<code>` tinylink (fallback only)

Prefer asking the user for the resolved URL or numeric page ID — this decode
is fiddly and only worth it if that's not available.

The `x/<code>` short-link code is the page ID, base64-encoded with the byte
order reversed. Decode:

```python
import base64

def decode_tinylink(code):
    rev = code[::-1]
    s = rev.replace('-', '+').replace('_', '/')
    s += '=' * (-len(s) % 4)
    decoded = base64.b64decode(s)
    return int.from_bytes(decoded, byteorder='big')
```

Verify the result before trusting it — try `acli confluence page view --id
<decoded> --json` and confirm the returned `title` matches what you expect.
This has produced a wrong-but-plausible-looking integer before; a failed
lookup (`Cannot find a page with id [...]`) means try asking the user instead
of guessing further variants.
