#!/usr/bin/env bash
cd "$(dirname "$0")"
uv run --with flask python app.py
