# Bournemouth CLI

This project includes a small command line client for interacting with the chat
API. It requires Python 3.13 and the dependencies defined in `pyproject.toml`.

## Installation

Install the project in editable mode and ensure the CLI dependencies are
available:

```bash
uv pip install -e .
```

A console script named `bournemouth-chat` will be available after installation.

## Usage

```bash
bournemouth-chat login
bournemouth-chat token
bournemouth-chat chat
```

The `login` command prompts for your username and password and stores the
session cookie in `~/.bournemouth_cookie`. The `token` command saves your
OpenRouter API key. After logging in and setting a token, use `chat` to start an
interactive conversation.
