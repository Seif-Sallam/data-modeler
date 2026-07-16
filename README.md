# 📐 Data Modeler

A local, single-user web app for **designing database schemas visually** and turning them into
**SQLAlchemy Python models** and **Markdown documentation**. Draw your tables on an infinite
canvas, wire up relationships, annotate everything, and export production-ready code in one click.

Everything runs on your own machine. Your work is saved as plain JSON files you fully own — no
server, no cloud, no accounts.

---

## Quick start

```bash
./run.sh
```

Then open **http://127.0.0.1:8001** in your browser.

Requires Python 3.10+ and [`uv`](https://docs.astral.sh/uv/). Flask is pulled in automatically —
no build step, no database. Drafts and backups default to `~/Downloads/DataModeler/` and the
location is configurable in-app.

---

## Features

- **Visual canvas** — infinite pan/zoom, per-tab saved views, and one-click auto-arrange.
- **Tables & columns** — move, resize, collapse, duplicate; full column control (type, PK,
  nullable, unique, index, server default, reorder).
- **Constraints** — named multi-column unique constraints and composite indexes.
- **Relationship links** that track tables as you move, resize, and reorder columns.
- **Tabs** to split large schemas into logical areas.
- **Documentation built in** — sticky notes and table/column comments, all with live Markdown.
- **Export** to SQLAlchemy Python models, a Markdown report, or JSON — whole draft, one tab, or
  selected tables.
- **Import** by uploading a JSON draft or **pasting existing Python** to reverse-engineer it.
- **📸 Snapshot** the canvas to a high-resolution PNG.
- **Undo/redo, autosave, multi-select group move**, light/dark theme, keyboard shortcuts.
- **⚙ Configurable storage location** — save drafts and backups anywhere (including a synced
  Dropbox / iCloud / Git folder).

---

## Documentation

See **[USAGE.md](USAGE.md)** for the full user guide, including keyboard shortcuts and every
import/export option.

---

## How it works

A tiny single-process **Flask** backend serves a vanilla-JS single-page app (no framework, no
bundler). Each design is one JSON file; every save writes a timestamped backup first, so you can
never lose work by overwriting.

```
app.py              Flask backend — routes, Python codegen, Python parser, Markdown renderer
static/index.html   Single-page app (HTML + CSS + JS inline)
run.sh              One-command launcher
mcp_server.py       MCP server — lets an AI agent build & read drafts (see below)
run_mcp.sh          Launcher for the MCP server (stdio)
```

---

## MCP server (drive it from an AI agent)

`mcp_server.py` exposes the Data Modeler as an [MCP](https://modelcontextprotocol.io) server, so
an agent (e.g. Claude Code) can design a schema **during the planning phase** — create a draft,
add tabs, tables, columns, comments, sticky notes and relationship links — and then read the
design back out as SQLAlchemy code to drop straight into the target codebase.

It's a thin HTTP client of the running app, so **start `./run.sh` first**. Every change goes
through the app's normal save path, meaning it's auto-backed-up and shows up in the browser when
you reopen the draft.

The project ships a `.mcp.json`, so Claude Code picks the server up automatically when you open
this repo (approve it once when prompted). Point it at a non-default app URL with the
`DATA_MODELER_URL` env var. To run it standalone: `./run_mcp.sh`.

**Tools:**
- *Read:* `list_drafts`, `get_draft`, `export_python`, `export_markdown`
- *Build:* `create_draft`, `add_tab`, `duplicate_tab`, `add_table`, `add_column`, `add_note`, `add_link`
- *Edit:* `update_table` (rename / constraints), `update_column` (type / flags), `remove_column`,
  `set_comment` (on a table **or** a column)
- *Organize:* `set_table_layout` (move, resize, minimize a table), `auto_arrange` (grid a whole tab)
