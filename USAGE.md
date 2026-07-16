# Data Modeler — User Guide

A local, single-user web app for **designing database schemas visually** and turning them
into **SQLAlchemy Python models** and **Markdown documentation**. Draw your tables on an
infinite canvas, wire up relationships, annotate everything, and export production-ready code
in one click.

Everything runs on your own machine. Your work is saved as plain JSON files you fully own.

---

## Getting started

```bash
./run.sh
```

Then open **http://127.0.0.1:8001** in your browser.

That's it — no build step, no database, no accounts. The only requirements are Python 3.10+
and [`uv`](https://docs.astral.sh/uv/). The app pulls in Flask automatically.

Your designs are stored as JSON files in a `drafts/` folder, and every time you save, the
previous version is copied into a `backups/` folder with a timestamp — so you can never lose
work by overwriting. By default these live in **`~/Downloads/DataModeler/`**, and you can
change the location at any time (see [Choosing where files are saved](#choosing-where-files-are-saved)).

---

## Core concepts

| Term | What it is |
|---|---|
| **Draft** | One complete design document. You can have as many as you like — switch between them from the toolbar. |
| **Tab** | A canvas within a draft. Use tabs to split a large schema into logical areas (e.g. "Billing", "Users"). |
| **Table** | A database table card on the canvas, with columns and constraints. |
| **Column** | A field in a table, with type, primary key, nullable, unique, index, server default, and comments. |
| **Link** | A visual relationship line between two columns. Purely for readability — links are **not** exported as foreign keys. |
| **Note** | A free-floating sticky note for documentation. Supports full Markdown. |

---

## Designing a schema

### Working with tables

- **Add a table** — click **＋ Table** in the toolbar. A new card appears on the canvas.
- **Rename** — click the table name and type. The Python class name is derived automatically
  (`user_account` → `UserAccount`).
- **Move** — drag the table header anywhere on the canvas.
- **Resize** — drag the corner handle to widen the card; drag the Name/Type column dividers
  to adjust column widths.
- **Collapse** — click **▬** to shrink a table to a compact summary; **▣** to expand it again.
- **Duplicate** — click **❏** to clone a table.
- **Delete** — click **🗑**; it turns red, click again within 3 seconds to confirm.

### Working with columns

Each column row exposes toggles and fields:

- **PK** — mark the column as the table's primary key.
- **Nullable** — allow `NULL` values.
- **Unique** — add a `UNIQUE` constraint.
- **Index** — add a single-column index.
- **Server default** — e.g. `CURRENT_TIMESTAMP`, `0`, `'1'`.
- **Reorder** — drag the handle on the left of a row.
- **Add a column** — press **Shift+Enter** while editing a column, or use the row actions.

**Supported column types:** `BIGINT`, `INT`, `SMALLINT`, `TINYINT`, `String(N)`, `TEXT`,
`DATETIME`, `DATE`, `BOOLEAN`, `JSON`, `DECIMAL(p,s)`, and `CCY` (currency).

### Multi-column constraints

Beyond per-column flags, each table can define named **multi-column unique constraints** and
**composite indexes**, which are emitted into the generated `__table_args__`.

### Links (relationships)

Draw a link between two columns to visually document a relationship. Use the **link manager**
in the toolbar to list, hide/show, or delete links, or toggle **hide/show all links** for the
whole tab at once. Links follow tables as you move, resize, or reorder columns — they always
stay attached to the right anchor.

### Notes & comments

- **Sticky notes** — click **＋ Note** to drop a Markdown note anywhere on the canvas. Notes
  render live, can be resized, and minimized independently.
- **Table & column comments** — click the **💬** button to attach Markdown documentation to a
  table or an individual column. Comments can be *pinned* so they stay visible on the canvas.

Markdown support across notes and comments includes headings, **bold**, *italic*, `code`,
fenced code blocks, bullet/numbered lists, blockquotes, links, horizontal rules, and GFM
pipe tables with column alignment.

---

## Canvas navigation

| Action | How |
|---|---|
| **Pan** | Drag empty canvas space. |
| **Zoom** | Scroll wheel (zooms toward the cursor), or **⌘/Ctrl +** / **⌘/Ctrl −**. |
| **Reset view** | Click the reset button in the view controls. |
| **Auto-arrange** | Tidy all tables into a grid with one click. |
| **Select** | **⌘/Ctrl+Click** to toggle selection; **⌘/Ctrl+A** to select everything. |
| **Group move** | Drag any selected item to move the whole selection together. |

Each tab remembers its own zoom and pan position.

---

## Editing shortcuts

| Shortcut | Action |
|---|---|
| **⌘/Ctrl+S** | Save the current draft |
| **⌘/Ctrl+Z** | Undo |
| **⌘/Ctrl+Shift+Z** | Redo |
| **⌘/Ctrl+A** | Select all on the canvas |
| **Shift+Enter** | Add a new column while editing |
| **Shift+Tab** | Cycle between tabs |

Undo/redo covers your editing history; the app also autosaves as you work.

---

## Importing & exporting

### Export → Python

Generates clean **SQLAlchemy model classes** — `__tablename__`, all columns with their types
and flags, and `__table_args__` for multi-column constraints. Export the **whole draft**, a
**single tab**, or a **selected set of tables**. Copy to clipboard or view in the dialog.

### Export → Markdown

Produces a **documentation report**: one section per tab, each with its tables, columns,
constraints, links, and notes. Ideal for pasting into a wiki or PR description.

### Export → JSON

Downloads the raw draft file so you can back it up or move it between machines.

### Import → Paste Python code

Paste existing SQLAlchemy class definitions and the app **parses them back into tables** —
recognizing columns, types, `primary_key`, `nullable`, `unique`, `index`, `server_default`,
and `UniqueConstraint` / `Index` definitions. Great for reverse-engineering an existing model.

### Import → Upload draft file

Load a `.json` draft exported from another machine.

### 📸 Snapshot

Download a **high-resolution PNG** of the current tab's canvas — perfect for design docs and
presentations.

---

## Managing drafts

From the toolbar you can **switch** between drafts, create a **new** one, **rename**,
**duplicate**, or **delete** (a timestamped backup is always kept in `backups/`).

## Choosing where files are saved

Click **⚙ Settings** in the toolbar to choose the folder where your drafts and backups live.

- The default is **`~/Downloads/DataModeler/`**, created automatically on first run.
- Enter any absolute folder path — the app creates `drafts/` and `backups/` subfolders inside
  it. Point it at a synced folder (Dropbox, iCloud Drive, a Git repo…) to back up or share your
  designs however you like.
- Leave the field empty and save to reset back to the default.

Your choice is remembered between sessions (stored in `~/.data-modeler/config.json`). Changing
the location doesn't move existing files — switch back to the old folder anytime, or copy your
`.json` files across.

---

## Good to know

- **Everything is local.** No server, no cloud, no login. Your data stays on your machine.
- **Your files are yours.** Drafts are readable JSON — inspect, diff, or version-control them.
- **Safe by default.** Every save writes a backup first; deletes keep a backup too.
- **Works offline.** The only external dependency is the screenshot library, loaded from a CDN
  and used solely by the Snapshot button.
