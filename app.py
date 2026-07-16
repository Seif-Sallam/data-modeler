import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, abort

ROOT = Path(__file__).parent
STATIC = ROOT / "static"

CONFIG_PATH = Path.home() / ".data-modeler" / "config.json"
DEFAULT_STORAGE = Path.home() / "Downloads" / "DataModeler"


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def storage_dir() -> Path:
    raw = load_config().get("storage_dir")
    return Path(raw).expanduser() if raw else DEFAULT_STORAGE


def drafts_dir() -> Path:
    d = storage_dir() / "drafts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def backups_dir() -> Path:
    d = storage_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


app = Flask(__name__, static_folder=str(STATIC), static_url_path="")


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_\- ]", "", name).strip().replace(" ", "_")
    return s or "draft"


def draft_path(name: str) -> Path:
    return drafts_dir() / f"{slugify(name)}.json"


@app.route("/")
def index():
    return send_from_directory(str(STATIC), "index.html")


@app.route("/api/drafts", methods=["GET"])
def list_drafts():
    out = []
    for p in sorted(drafts_dir().glob("*.json")):
        try:
            st = p.stat()
            out.append({
                "name": p.stem,
                "mtime": st.st_mtime,
                "size": st.st_size,
            })
        except Exception:
            pass
    return jsonify(out)


@app.route("/api/drafts/<name>", methods=["GET"])
def get_draft(name):
    p = draft_path(name)
    if not p.exists():
        abort(404)
    resp = jsonify(json.loads(p.read_text()))
    resp.headers["X-Draft-Mtime"] = str(p.stat().st_mtime)
    return resp


@app.route("/api/drafts/<name>", methods=["PUT"])
def save_draft(name):
    data = request.get_json()
    p = draft_path(name)
    if p.exists():
        # backup previous
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(p, backups_dir() / f"{p.stem}__{ts}.json")
    p.write_text(json.dumps(data, indent=2))
    st = p.stat()
    return jsonify({"ok": True, "name": p.stem, "mtime": st.st_mtime})


@app.route("/api/drafts/<name>/meta", methods=["GET"])
def draft_meta(name):
    p = draft_path(name)
    if not p.exists():
        return jsonify({"exists": False})
    st = p.stat()
    return jsonify({"exists": True, "mtime": st.st_mtime, "size": st.st_size})


@app.route("/api/drafts/<name>", methods=["DELETE"])
def delete_draft(name):
    p = draft_path(name)
    if p.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.move(str(p), str(backups_dir() / f"{p.stem}__deleted_{ts}.json"))
    return jsonify({"ok": True})


@app.route("/api/duplicate", methods=["POST"])
def duplicate_draft():
    body = request.get_json()
    src = draft_path(body["source"])
    dst_name = slugify(body["target"])
    dst = drafts_dir() / f"{dst_name}.json"
    if not src.exists():
        abort(404)
    if dst.exists():
        return jsonify({"ok": False, "error": "target exists"}), 400
    data = json.loads(src.read_text())
    data["name"] = dst_name
    dst.write_text(json.dumps(data, indent=2))
    return jsonify({"ok": True, "name": dst_name})


@app.route("/api/rename", methods=["POST"])
def rename_draft():
    body = request.get_json()
    src = draft_path(body["source"])
    dst_name = slugify(body["target"])
    dst = drafts_dir() / f"{dst_name}.json"
    if not src.exists():
        abort(404)
    if dst.exists():
        return jsonify({"ok": False, "error": "target exists"}), 400
    data = json.loads(src.read_text())
    data["name"] = dst_name
    dst.write_text(json.dumps(data, indent=2))
    src.unlink()
    return jsonify({"ok": True, "name": dst_name})


@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify({
        "storage_dir": str(storage_dir()),
        "drafts_dir": str(storage_dir() / "drafts"),
        "backups_dir": str(storage_dir() / "backups"),
        "default_dir": str(DEFAULT_STORAGE),
        "is_default": not load_config().get("storage_dir"),
    })


@app.route("/api/settings", methods=["PUT"])
def update_settings():
    body = request.get_json() or {}
    raw = (body.get("storage_dir") or "").strip()
    cfg = load_config()
    if not raw:
        cfg.pop("storage_dir", None)
        save_config(cfg)
        return jsonify({"ok": True, "storage_dir": str(DEFAULT_STORAGE), "is_default": True})
    target = Path(raw).expanduser()
    try:
        (target / "drafts").mkdir(parents=True, exist_ok=True)
        (target / "backups").mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Cannot use '{target}': {e}"}), 400
    cfg["storage_dir"] = str(target)
    save_config(cfg)
    return jsonify({"ok": True, "storage_dir": str(target), "is_default": False})


# ---- Python export ----

PY_TYPE_MAP = {
    "TINYINT": "TINYINT",
    "SMALLINT": "SMALLINT",
    "MEDIUMINT": "MEDIUMINT",
    "INT": "INT",
    "BIGINT": "BIGINT",
    "SINT": "SINT",
    "SBIGINT": "SBIGINT",
    "CCY": "CCY",
    "BOOLEAN": "sa.Boolean",
    "BOOL": "sa.Boolean",
    "DATE": "sa.Date()",
    "DATETIME": "sa.DateTime",
    "TIME": "sa.Time",
    "TIMESTAMP": "types.TIMESTAMP",
    "JSON": "types.JSON",
    "TEXT": "sa.Text",
    "UNICODETEXT": "sa.UnicodeText",
    "REAL": "sa.REAL",
}


def render_col_type(t: str) -> str:
    t = (t or "").strip()
    if not t:
        return "sa.String(255)"
    u = t.upper()
    m = re.match(r"^(VARCHAR|STRING|CHAR)\s*\(\s*(\d+)\s*\)$", u)
    if m:
        return f"sa.String({m.group(2)})"
    m = re.match(r"^NUMERIC\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)$", u)
    if m:
        return f"sa.Numeric({m.group(1)}, {m.group(2)})"
    if u in PY_TYPE_MAP:
        return PY_TYPE_MAP[u]
    # raw passthrough
    return t


def render_table(tbl) -> str:
    table_name = tbl.get("table_name") or tbl.get("name") or "unnamed"
    parts_name = [p for p in re.split(r"[_\s]+", table_name) if p]
    name = "".join(p[:1].upper() + p[1:] for p in parts_name) or "Unnamed"
    cols = tbl.get("columns", [])
    lines = [f"class {name}(Model):", f"    __tablename__ = '{table_name}'"]
    for c in cols:
        cname = c.get("name", "")
        if not cname:
            continue
        ctype = render_col_type(c.get("type", ""))
        parts = [ctype]
        if c.get("primary_key"):
            parts.append("primary_key=True")
            if c.get("no_autoincrement"):
                parts.append("autoincrement=False")
        if not c.get("primary_key"):
            parts.append(f"nullable={'True' if c.get('nullable') else 'False'}")
        if c.get("unique"):
            parts.append("unique=True")
        if c.get("index"):
            parts.append("index=True")
        sd = c.get("server_default")
        if sd not in (None, ""):
            if isinstance(sd, str) and (sd.startswith("CURRENT_") or "CURRENT_TIMESTAMP" in sd or "ON UPDATE" in sd):
                parts.append(f"server_default=text('{sd}')")
            else:
                parts.append(f"server_default='{sd}'")
        lines.append(f"    {cname} = sa.Column({', '.join(parts)})")

    # table_args: unique constraints, indexes
    constraints = tbl.get("constraints", [])
    if constraints:
        lines.append("")
        lines.append("    __table_args__ = (")
        for ct in constraints:
            kind = ct.get("kind")
            cnname = ct.get("name", "")
            ccols = ", ".join(f"'{x}'" for x in ct.get("columns", []))
            if kind == "unique":
                lines.append(f"        UniqueConstraint({ccols}, name='{cnname}'),")
            elif kind == "index":
                lines.append(f"        Index('{cnname}', {ccols}),")
        lines.append("    )")
    return "\n".join(lines)


@app.route("/api/export/<name>", methods=["GET"])
def export_python(name):
    p = draft_path(name)
    if not p.exists():
        abort(404)
    data = json.loads(p.read_text())
    tab = request.args.get("tab")
    tables_filter = request.args.get("tables")
    allowed = set(tables_filter.split(",")) if tables_filter else None
    tabs = data.get("tabs", [])
    selected = []
    for t in tabs:
        if tab is None or t.get("id") == tab or t.get("name") == tab:
            if allowed is None:
                selected.append(t)
            else:
                filtered = {**t, "tables": [tb for tb in t.get("tables", []) if tb.get("id") in allowed]}
                if filtered["tables"]:
                    selected.append(filtered)
    body_parts = []
    for t in selected:
        for tbl in t.get("tables", []):
            body_parts.append(render_table(tbl))
            body_parts.append("")
    return jsonify({"python": "\n\n".join(body_parts)})


def _strip_quotes(s):
    s = s.strip()
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        return s[1:-1]
    return s


def _split_args(s):
    out, depth, cur = [], 0, []
    in_str = None
    for ch in s:
        if in_str:
            cur.append(ch)
            if ch == in_str and (len(cur) < 2 or cur[-2] != "\\"):
                in_str = None
            continue
        if ch in ("'", '"'):
            in_str = ch; cur.append(ch); continue
        if ch in "([{":
            depth += 1; cur.append(ch); continue
        if ch in ")]}":
            depth -= 1; cur.append(ch); continue
        if ch == "," and depth == 0:
            out.append("".join(cur).strip()); cur = []; continue
        cur.append(ch)
    if cur:
        out.append("".join(cur).strip())
    return [x for x in out if x]


def _denorm_type(raw):
    raw = raw.strip()
    m = re.match(r"^sa\.String\(\s*(\d+)\s*\)$", raw)
    if m:
        return f"String({m.group(1)})"
    m = re.match(r"^sa\.Numeric\(\s*(\d+)\s*,\s*(\d+)\s*\)$", raw)
    if m:
        return f"Numeric({m.group(1)},{m.group(2)})"
    rev = {
        "TINYINT": "TINYINT", "SMALLINT": "SMALLINT", "MEDIUMINT": "MEDIUMINT",
        "INT": "INT", "BIGINT": "BIGINT", "SINT": "SINT", "SBIGINT": "SBIGINT", "CCY": "CCY",
        "sa.Boolean": "BOOLEAN", "sa.Date()": "DATE", "sa.Date": "DATE",
        "sa.DateTime": "DATETIME", "sa.Time": "TIME",
        "types.TIMESTAMP": "TIMESTAMP", "sa.TIMESTAMP": "TIMESTAMP",
        "types.JSON": "JSON", "sa.JSON": "JSON",
        "sa.Text": "TEXT", "sa.TEXT": "TEXT", "sa.UnicodeText": "UNICODETEXT",
        "sa.REAL": "REAL", "sa.Integer": "INT",
    }
    return rev.get(raw, raw)


def parse_python_tables(src):
    tables = []
    # split into class blocks
    class_re = re.compile(r"^class\s+(\w+)\s*\(\s*Model\s*\)\s*:\s*$", re.M)
    matches = list(class_re.finditer(src))
    for i, m in enumerate(matches):
        cls_name = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(src)
        body = src[start:end]
        tn = re.search(r"__tablename__\s*=\s*['\"]([^'\"]+)['\"]", body)
        table_name = tn.group(1) if tn else re.sub(r"(?<!^)(?=[A-Z])", "_", cls_name).lower()
        columns = []
        # find columns: name = sa.Column(...)
        for col_m in re.finditer(r"^(\s+)(\w+)\s*=\s*sa\.Column\(", body, re.M):
            cname = col_m.group(2)
            # extract balanced parens
            i2 = col_m.end() - 1
            depth = 0; j = i2
            in_str = None
            while j < len(body):
                ch = body[j]
                if in_str:
                    if ch == in_str and body[j-1] != "\\":
                        in_str = None
                elif ch in ("'", '"'):
                    in_str = ch
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            inside = body[i2 + 1:j]
            args = _split_args(inside)
            if not args:
                continue
            ctype = _denorm_type(args[0])
            col = {
                "id": None, "name": cname, "type": ctype,
                "nullable": False, "primary_key": False, "unique": False,
                "index": False, "server_default": "", "no_autoincrement": False,
            }
            for a in args[1:]:
                if "=" not in a:
                    continue
                k, v = a.split("=", 1)
                k = k.strip(); v = v.strip()
                if k == "primary_key" and v == "True":
                    col["primary_key"] = True
                elif k == "nullable":
                    col["nullable"] = (v == "True")
                elif k == "unique" and v == "True":
                    col["unique"] = True
                elif k == "index" and v == "True":
                    col["index"] = True
                elif k == "autoincrement" and v == "False":
                    col["no_autoincrement"] = True
                elif k == "server_default":
                    mm = re.match(r"text\(\s*['\"]([^'\"]+)['\"]\s*\)$", v)
                    if mm:
                        col["server_default"] = mm.group(1)
                    else:
                        col["server_default"] = _strip_quotes(v)
            columns.append(col)
        # constraints (simple: UniqueConstraint / Index inside __table_args__)
        constraints = []
        for cm in re.finditer(r"UniqueConstraint\(([^)]*)\)", body):
            parts = _split_args(cm.group(1))
            cols = [_strip_quotes(p) for p in parts if "=" not in p]
            name = ""
            for p in parts:
                if p.strip().startswith("name="):
                    name = _strip_quotes(p.split("=", 1)[1])
            constraints.append({"kind": "unique", "name": name, "columns": cols})
        for cm in re.finditer(r"(?:sa\.)?Index\(([^)]*)\)", body):
            parts = _split_args(cm.group(1))
            if not parts:
                continue
            name = _strip_quotes(parts[0])
            cols = [_strip_quotes(p) for p in parts[1:] if "=" not in p]
            constraints.append({"kind": "index", "name": name, "columns": cols})
        tables.append({
            "table_name": table_name, "name": cls_name,
            "columns": columns, "constraints": constraints,
        })
    return tables


def render_markdown(data, tab_id=None):
    out = []
    name = data.get("name") or "draft"
    out.append(f"# {name}")
    out.append("")
    if data.get("description"):
        out.append(data["description"])
        out.append("")
    tabs = data.get("tabs", [])
    if tab_id:
        tabs = [t for t in tabs if t.get("id") == tab_id or t.get("name") == tab_id]
    for tab in tabs:
        out.append(f"## Tab: {tab.get('name','')}")
        if tab.get("description"):
            out.append("")
            out.append(tab["description"])
        out.append("")
        for tbl in tab.get("tables", []):
            tn = tbl.get("table_name") or "unnamed"
            cls = "".join(p[:1].upper()+p[1:] for p in re.split(r"[_\s]+", tn) if p)
            out.append(f"### {cls} — `{tn}`")
            if tbl.get("comment"):
                out.append("")
                for ln in str(tbl["comment"]).split("\n"):
                    out.append(f"> {ln}")
            out.append("")
            out.append("| Column | Type | PK | Null | Unique | Idx | Default | Comment |")
            out.append("|--------|------|----|------|--------|-----|---------|---------|")
            for c in tbl.get("columns", []):
                out.append("| `{n}` | `{t}` | {pk} | {nu} | {un} | {ix} | {sd} | {co} |".format(
                    n=c.get("name",""),
                    t=c.get("type",""),
                    pk="✔" if c.get("primary_key") else "",
                    nu="✔" if c.get("nullable") else "",
                    un="✔" if c.get("unique") else "",
                    ix="✔" if c.get("index") else "",
                    sd=f"`{c['server_default']}`" if c.get("server_default") else "",
                    co=(c.get("comment","") or "").replace("|","\\|").replace("\n"," "),
                ))
            cs = tbl.get("constraints", [])
            if cs:
                out.append("")
                out.append("**Constraints / Indexes**")
                for ct in cs:
                    cols = ", ".join(ct.get("columns", []))
                    out.append(f"- {ct.get('kind','')} `{ct.get('name','')}` ({cols})")
            out.append("")
        links = tab.get("links", [])
        if links:
            out.append("**Links**")
            tmap = {t["id"]: t for t in tab.get("tables", [])}
            for l in links:
                a = tmap.get(l.get("fromTable")); b = tmap.get(l.get("toTable"))
                if not a or not b: continue
                ac = next((c for c in a.get("columns",[]) if c.get("id")==l.get("fromCol")), None)
                bc = next((c for c in b.get("columns",[]) if c.get("id")==l.get("toCol")), None)
                out.append(f"- `{a.get('table_name','?')}.{ac.get('name','?') if ac else '?'}` → `{b.get('table_name','?')}.{bc.get('name','?') if bc else '?'}`")
            out.append("")
        notes = tab.get("notes", [])
        if notes:
            out.append("**Notes**")
            out.append("")
            for n in notes:
                title = (n.get("title") or "").strip() or "📝 Note"
                out.append(f"#### {title}")
                txt = (n.get("text") or "").strip()
                if txt:
                    for ln in txt.split("\n"):
                        out.append(f"> {ln}")
                else:
                    out.append("> _(empty)_")
                out.append("")
    return "\n".join(out)


@app.route("/api/markdown/<name>", methods=["GET"])
def api_markdown(name):
    p = draft_path(name)
    if not p.exists():
        abort(404)
    data = json.loads(p.read_text())
    tab = request.args.get("tab")
    return jsonify({"markdown": render_markdown(data, tab)})


@app.route("/api/parse", methods=["POST"])
def api_parse():
    body = request.get_json()
    src = body.get("source", "")
    return jsonify({"tables": parse_python_tables(src)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=False)
