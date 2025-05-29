# PyPI Publishing

## Prerequisites

- Make sure you have 2FA enabled for your PyPI account
- Ask @k0machi or @fruch for access to the project
- Create a token on the [PyPI account page](https://pypi.org/manage/account/#api-tokens)

## Usage

Edit your publishing version inside `pyproject.toml`:

```toml
version = "0.12.3"
```

Then simply run

```bash
UV_PUBLISH_TOKEN=${your-token}
uv build
uv publish
```
