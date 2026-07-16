#!/usr/bin/env bash
cd "$(dirname "$0")"
uv run --with mcp --with httpx python mcp_server.py
