"""MCP server for the Data Modeler app.

Exposes the visual schema designer as tools so an agent can build up a draft
during a planning phase — create drafts/tabs, add tables/columns, annotate with
comments and sticky notes, wire relationships — and then read the design back
out as SQLAlchemy code or Markdown to drop into the target codebase.

It is a thin HTTP client of the running Data Modeler service (default
http://127.0.0.1:8001). Start the app first with ./run.sh. Mutations are done as
read-modify-write against PUT /api/drafts/<name>, which auto-backs-up on save.
"""

import copy
import logging
import os
import random
import string
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("data-modeler-mcp")

BASE_URL = os.environ.get("DATA_MODELER_URL", "http://127.0.0.1:8001").rstrip("/")

LAYOUT_GUIDE = (
    "Canvas layout: tables are absolutely positioned by their top-left (x, y) in "
    "canvas pixels. A table is ~290px wide (or its `w` value if set). Height is "
    "roughly 40px (header) + 28px per column row; a collapsed/minimized table is "
    "just the ~40px header. To avoid overlap, space tables ~340px apart "
    "horizontally and leave a >=40px vertical gap below the tallest neighbour. "
    "Use get_draft to read current x/y/w/collapsed, compute positions from the "
    "sizes above, then set_table_layout to place or minimize tables. "
    "All comment/note text (table comments, column comments, sticky notes) is "
    "rendered as Markdown, so you can use headings, bold/italic, code, lists, "
    "tables and links to write rich documentation."
)

mcp = FastMCP("data-modeler", instructions=LAYOUT_GUIDE)

_BASE36 = string.digits + string.ascii_lowercase


def uid() -> str:
    return "".join(random.choices(_BASE36, k=7))


def _client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=15.0)


def _request(method: str, path: str, **kwargs) -> httpx.Response:
    try:
        with _client() as client:
            resp = client.request(method, path, **kwargs)
    except httpx.ConnectError:
        raise Exception(
            f"Cannot reach the Data Modeler service at {BASE_URL}. "
            f"Start it with ./run.sh (or set DATA_MODELER_URL)."
        )
    if resp.status_code == 404:
        raise Exception(f"Not found: {path} (does the draft exist?)")
    resp.raise_for_status()
    return resp


def _get_draft(name: str) -> dict:
    return _request("GET", f"/api/drafts/{name}").json()


def _put_draft(name: str, data: dict) -> None:
    _request("PUT", f"/api/drafts/{name}", json=data)


def _find_tab(draft: dict, tab: Optional[str]) -> dict:
    tabs = draft.get("tabs", [])
    if not tabs:
        raise Exception(f"Draft '{draft.get('name')}' has no tabs.")
    if tab is None:
        return tabs[0]
    for t in tabs:
        if t.get("id") == tab or t.get("name") == tab:
            return t
    raise Exception(f"No tab '{tab}' in draft '{draft.get('name')}'.")


def _find_table(tab: dict, table: str) -> dict:
    for tb in tab.get("tables", []):
        if tb.get("id") == table or tb.get("table_name") == table or tb.get("name") == table:
            return tb
    raise Exception(f"No table '{table}' in tab '{tab.get('name')}'.")


def _find_column(tbl: dict, column: str) -> dict:
    for c in tbl.get("columns", []):
        if c.get("id") == column or c.get("name") == column:
            return c
    raise Exception(f"No column '{column}' in table '{tbl.get('table_name')}'.")


def _new_column(spec: dict) -> dict:
    col = {
        "id": uid(),
        "name": spec.get("name", ""),
        "type": spec.get("type", ""),
        "nullable": bool(spec.get("nullable", False)),
        "primary_key": bool(spec.get("primary_key", False)),
        "unique": bool(spec.get("unique", False)),
        "index": bool(spec.get("index", False)),
        "server_default": spec.get("server_default", "") or "",
        "no_autoincrement": bool(spec.get("no_autoincrement", False)),
    }
    if spec.get("comment"):
        col["comment"] = spec["comment"]
        col["comment_pinned"] = bool(spec.get("comment_pinned", False))
    return col


def _grid_position(tab: dict) -> tuple[int, int]:
    n = len(tab.get("tables", []))
    return 60 + (n % 4) * 340, 60 + (n // 4) * 280


@mcp.tool()
def list_drafts() -> list[dict]:
    """List all existing drafts (name, last-modified time, size)."""
    return _request("GET", "/api/drafts").json()


@mcp.tool()
def get_draft(name: str) -> dict:
    """Read the full JSON of a draft: all tabs, tables, columns, links, notes and comments."""
    return _get_draft(name)


@mcp.tool()
def create_draft(name: str, first_tab_name: str = "Main") -> dict:
    """Create a new empty draft with a single tab.

    Returns the draft name and the id of the created tab.
    """
    existing = {d["name"] for d in _request("GET", "/api/drafts").json()}
    if name in existing:
        raise Exception(f"Draft '{name}' already exists. Use a different name or add to it.")
    tab_id = uid()
    draft = {"name": name, "tabs": [{"id": tab_id, "name": first_tab_name, "tables": [], "links": []}]}
    _put_draft(name, draft)
    return {"ok": True, "name": name, "tab_id": tab_id}


@mcp.tool()
def add_tab(draft: str, name: str) -> dict:
    """Add a new tab (a separate canvas within the draft) and return its id."""
    data = _get_draft(draft)
    tab_id = uid()
    data.setdefault("tabs", []).append({"id": tab_id, "name": name, "tables": [], "links": []})
    _put_draft(draft, data)
    return {"ok": True, "tab_id": tab_id}


@mcp.tool()
def duplicate_tab(draft: str, tab: str, new_name: Optional[str] = None) -> dict:
    """Duplicate a tab within a draft, including all its tables, columns, notes and links.

    All ids are regenerated and link references are remapped to the copies, so the
    new tab is fully independent — edit it freely without touching the original.
    `tab` is a tab id or name; `new_name` defaults to "<name> (copy)".
    """
    data = _get_draft(draft)
    src = _find_tab(data, tab)
    dup = copy.deepcopy(src)
    dup["id"] = uid()
    dup["name"] = new_name or f"{src.get('name', 'Tab')} (copy)"

    id_map: dict[str, str] = {}
    for tbl in dup.get("tables", []):
        new_id = uid()
        id_map[tbl["id"]] = new_id
        tbl["id"] = new_id
        for col in tbl.get("columns", []):
            new_col = uid()
            id_map[col["id"]] = new_col
            col["id"] = new_col
    for note in dup.get("notes", []):
        note["id"] = uid()
    for link in dup.get("links", []):
        link["fromTable"] = id_map.get(link.get("fromTable"), link.get("fromTable"))
        link["fromCol"] = id_map.get(link.get("fromCol"), link.get("fromCol"))
        link["toTable"] = id_map.get(link.get("toTable"), link.get("toTable"))
        link["toCol"] = id_map.get(link.get("toCol"), link.get("toCol"))

    data.setdefault("tabs", []).append(dup)
    _put_draft(draft, data)
    return {"ok": True, "tab_id": dup["id"], "name": dup["name"]}


@mcp.tool()
def add_table(
    draft: str,
    table_name: str,
    columns: Optional[list[dict]] = None,
    tab: Optional[str] = None,
    comment: Optional[str] = None,
    comment_pinned: bool = False,
    constraints: Optional[list[dict]] = None,
    x: Optional[int] = None,
    y: Optional[int] = None,
) -> dict:
    """Create a table in a tab.

    Args:
        table_name: snake_case table name (e.g. "vendor_contract").
        columns: list of column specs. Each is a dict with keys: name, type,
            and optional primary_key, nullable, unique, index, server_default,
            no_autoincrement, comment, comment_pinned. `type` accepts the app's
            column types: BIGINT, INT, SMALLINT, TINYINT, String(N), TEXT,
            DATETIME, DATE, TIMESTAMP, BOOLEAN, JSON, DECIMAL(p,s), CCY.
        tab: target tab id or name (defaults to the first tab).
        comment: optional table comment (rendered as Markdown).
        constraints: list of {kind: "unique"|"index", name, columns: [col_name,...]}.
        x, y: optional canvas position (auto-arranged in a grid if omitted).

    Returns the new table id and a name->id map of its columns.
    """
    data = _get_draft(draft)
    t = _find_tab(data, tab)
    if any(tb.get("table_name") == table_name for tb in t.get("tables", [])):
        raise Exception(f"Table '{table_name}' already exists in tab '{t.get('name')}'.")

    px, py = (x, y) if x is not None and y is not None else _grid_position(t)
    cols = [_new_column(c) for c in (columns or [])]
    tbl: dict[str, Any] = {
        "id": uid(),
        "table_name": table_name,
        "x": px,
        "y": py,
        "columns": cols,
        "constraints": constraints or [],
    }
    if comment:
        tbl["comment"] = comment
        tbl["comment_pinned"] = comment_pinned

    t.setdefault("tables", []).append(tbl)
    _put_draft(draft, data)
    return {
        "ok": True,
        "table_id": tbl["id"],
        "columns": {c["name"]: c["id"] for c in cols if c["name"]},
    }


@mcp.tool()
def add_column(draft: str, table: str, column: dict, tab: Optional[str] = None) -> dict:
    """Append a column to an existing table.

    `column` is a spec dict (same shape as add_table's column entries: name,
    type, and optional primary_key/nullable/unique/index/server_default/
    no_autoincrement/comment). The comment is rendered as Markdown. `table` is a
    table id or table_name.
    """
    data = _get_draft(draft)
    tbl = _find_table(_find_tab(data, tab), table)
    col = _new_column(column)
    tbl.setdefault("columns", []).append(col)
    _put_draft(draft, data)
    return {"ok": True, "column_id": col["id"]}


@mcp.tool()
def update_table(
    draft: str,
    table: str,
    new_table_name: Optional[str] = None,
    constraints: Optional[list[dict]] = None,
    tab: Optional[str] = None,
) -> dict:
    """Update an existing table: rename it and/or replace its constraints.

    `new_table_name` renames the table (snake_case). `constraints` replaces the
    whole constraint list with {kind: "unique"|"index", name, columns:[...]} items.
    Omitted args are left unchanged. `table` is a table id or table_name.
    """
    data = _get_draft(draft)
    tbl = _find_table(_find_tab(data, tab), table)
    if new_table_name is not None:
        tbl["table_name"] = new_table_name
        tbl.pop("name", None)  # let codegen re-derive the class name
    if constraints is not None:
        tbl["constraints"] = constraints
    _put_draft(draft, data)
    return {"ok": True, "table_id": tbl["id"], "table_name": tbl["table_name"]}


@mcp.tool()
def update_column(
    draft: str,
    table: str,
    column: str,
    name: Optional[str] = None,
    type: Optional[str] = None,
    primary_key: Optional[bool] = None,
    nullable: Optional[bool] = None,
    unique: Optional[bool] = None,
    index: Optional[bool] = None,
    server_default: Optional[str] = None,
    no_autoincrement: Optional[bool] = None,
    tab: Optional[str] = None,
) -> dict:
    """Modify an existing column in place. Only the fields you pass are changed.

    `column` is a column id or its current name. Any of name/type and the flags
    (primary_key, nullable, unique, index, server_default, no_autoincrement) may
    be updated; the column's comment is preserved (use set_comment to change it).
    """
    data = _get_draft(draft)
    col = _find_column(_find_table(_find_tab(data, tab), table), column)
    updates = {
        "name": name, "type": type, "primary_key": primary_key, "nullable": nullable,
        "unique": unique, "index": index, "server_default": server_default,
        "no_autoincrement": no_autoincrement,
    }
    for key, val in updates.items():
        if val is not None:
            col[key] = val
    _put_draft(draft, data)
    return {"ok": True, "column_id": col["id"]}


@mcp.tool()
def remove_column(draft: str, table: str, column: str, tab: Optional[str] = None) -> dict:
    """Delete a column from a table, and drop any links that referenced it."""
    data = _get_draft(draft)
    t = _find_tab(data, tab)
    tbl = _find_table(t, table)
    col = _find_column(tbl, column)
    col_id = col["id"]
    tbl["columns"] = [c for c in tbl["columns"] if c["id"] != col_id]
    t["links"] = [l for l in t.get("links", [])
                  if l.get("fromCol") != col_id and l.get("toCol") != col_id]
    _put_draft(draft, data)
    return {"ok": True, "removed": col_id}


@mcp.tool()
def set_table_layout(
    draft: str,
    table: str,
    x: Optional[int] = None,
    y: Optional[int] = None,
    w: Optional[int] = None,
    collapsed: Optional[bool] = None,
    tab: Optional[str] = None,
) -> dict:
    """Organize a table on the canvas: set its position (x, y), width (w), and/or
    minimize it (collapsed=True) or expand it (collapsed=False).

    Only the fields you pass change. A table is ~290px wide and ~40px + 28px/row
    tall (collapsed = ~40px); read current geometry with get_draft and space
    tables ~340px apart horizontally to avoid overlap.
    """
    data = _get_draft(draft)
    tbl = _find_table(_find_tab(data, tab), table)
    if x is not None:
        tbl["x"] = x
    if y is not None:
        tbl["y"] = y
    if w is not None:
        tbl["w"] = w
    if collapsed is not None:
        tbl["collapsed"] = collapsed
    _put_draft(draft, data)
    return {"ok": True, "table_id": tbl["id"],
            "x": tbl.get("x"), "y": tbl.get("y"), "w": tbl.get("w"),
            "collapsed": tbl.get("collapsed", False)}


@mcp.tool()
def auto_arrange(draft: str, tab: Optional[str] = None, columns: int = 4) -> dict:
    """Tidy all tables in a tab into a simple grid (like the app's auto-arrange).

    Lays tables left-to-right, `columns` per row, ~340px apart horizontally and
    spaced vertically to clear the tallest table in each row.
    """
    data = _get_draft(draft)
    t = _find_tab(data, tab)
    tables = t.get("tables", [])
    x0, y = 60, 60
    row_h = 0
    for i, tbl in enumerate(tables):
        col = i % columns
        if col == 0 and i > 0:
            y += row_h + 40
            row_h = 0
        tbl["x"] = x0 + col * 340
        tbl["y"] = y
        est_h = 40 if tbl.get("collapsed") else 40 + 28 * len(tbl.get("columns", []))
        row_h = max(row_h, est_h)
    _put_draft(draft, data)
    return {"ok": True, "arranged": len(tables)}


@mcp.tool()
def set_comment(
    draft: str,
    table: str,
    text: str,
    column: Optional[str] = None,
    pinned: bool = False,
    tab: Optional[str] = None,
) -> dict:
    """Set a comment on a table, or on one of its columns.

    Provide `column` (id or name) to comment on a column; omit it to comment on
    the table itself. `pinned` keeps the comment visible on the canvas. Comment
    text is rendered as Markdown (headings, bold/italic, `code`, fenced blocks,
    lists, tables, links), so you can write rich documentation.
    """
    data = _get_draft(draft)
    tbl = _find_table(_find_tab(data, tab), table)
    target = _find_column(tbl, column) if column else tbl
    target["comment"] = text
    target["comment_pinned"] = pinned
    _put_draft(draft, data)
    return {"ok": True}


@mcp.tool()
def add_note(
    draft: str,
    text: str,
    tab: Optional[str] = None,
    x: Optional[int] = None,
    y: Optional[int] = None,
) -> dict:
    """Drop a free-floating sticky note on a tab's canvas.

    `text` is rendered as Markdown (headings, bold/italic, code, lists, tables,
    links), so notes can hold rich planning documentation.
    """
    data = _get_draft(draft)
    t = _find_tab(data, tab)
    note = {"id": uid(), "x": x if x is not None else 80, "y": y if y is not None else 80,
            "text": text, "collapsed": False}
    t.setdefault("notes", []).append(note)
    _put_draft(draft, data)
    return {"ok": True, "note_id": note["id"]}


@mcp.tool()
def add_link(
    draft: str,
    from_table: str,
    from_col: str,
    to_table: str,
    to_col: str,
    tab: Optional[str] = None,
) -> dict:
    """Draw a relationship link between two columns (visual documentation only).

    Tables and columns are resolved by id or name within the given tab.
    """
    data = _get_draft(draft)
    t = _find_tab(data, tab)
    ft, tt = _find_table(t, from_table), _find_table(t, to_table)
    fc, tc = _find_column(ft, from_col), _find_column(tt, to_col)
    t.setdefault("links", []).append({
        "fromTable": ft["id"], "fromCol": fc["id"],
        "toTable": tt["id"], "toCol": tc["id"], "hidden": False,
    })
    _put_draft(draft, data)
    return {"ok": True}


@mcp.tool()
def export_python(draft: str, tab: Optional[str] = None, tables: Optional[list[str]] = None) -> str:
    """Generate SQLAlchemy model code from a draft, to write into the target codebase.

    Optionally scope to a single `tab` (id or name) or a subset of table ids via
    `tables`. Returns the generated Python source.
    """
    params: dict[str, str] = {}
    if tab is not None:
        params["tab"] = tab
    if tables:
        params["tables"] = ",".join(tables)
    return _request("GET", f"/api/export/{draft}", params=params).json()["python"]


@mcp.tool()
def export_markdown(draft: str, tab: Optional[str] = None) -> str:
    """Generate the Markdown documentation report for a draft (optionally one tab)."""
    params = {"tab": tab} if tab is not None else {}
    return _request("GET", f"/api/markdown/{draft}", params=params).json()["markdown"]


if __name__ == "__main__":
    logger.info("Data Modeler MCP server -> %s", BASE_URL)
    mcp.run()
