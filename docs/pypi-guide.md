# PyPI Publishing

## Prerequisites

- Make sure you have 2FA enabled for your PyPI account
- Ask @k0machi or @fruch for access to the project
- Create a token on the [PyPI account page](https://pypi.org/manage/account/#api-tokens)

## Poetry setup

Save your token to poetry:

```bash
poetry config pypi-token.pypi $your-token
```

## Usage

Edit your publishing version inside `pyproject.toml`:

```toml
version = "0.12.3"
```

Then simply run

```bash
poetry publish --build
```
