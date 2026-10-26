#!/usr/bin/env python3
"""paper-colors CLI (stdlib only; `swatch sample` additionally needs Pillow).

Data (outside the skill: $PAPER_COLORS_HOME, default ~/.paper-colors/)
  paper_colors.py init [--from OLD_SKILL_DIR]   create the data folder; copy an old install's data
  paper_colors.py where                         print the data paths in use

Themes
  paper_colors.py list                          themes and their Pantone anchors
  paper_colors.py show [THEME]                  anchors, ramps, contrast, CVD previews
  paper_colors.py audit [THEME ...]             quality gate; exit 1 on any ERROR
  paper_colors.py export THEME --out DIR        paper_colors.py, paper-colors.sty,
                    [--formats py,sty,json,svg]  paper-colors.json, paper-colors-swatches.svg
  paper_colors.py lint PATH [--theme THEME]     off-palette colors in a paper; exit 1 if any

Pantone swatches (screenshot portal: inbox/ in the data folder)
  paper_colors.py swatch inbox                 screenshots waiting to be registered
  paper_colors.py swatch sample IMAGE [--box x0,y0,x1,y1] [--top N]
                                                dominant colors, ICC profile -> sRGB
  paper_colors.py swatch add CODE --name NAME [--hex H] [--sampled H] [--screenshot IMAGE]
  paper_colors.py swatch import FILE.ase [--dry-run]
                                                register a whole Pantone Connect collection export
  paper_colors.py swatch library add FILE [--name N]   index a color book (.acb/.aco/.ase)
  paper_colors.py swatch library add --from-pantone-cli [--index FILE] [--books ID,ID]
                                                index the books of a pantone-cli match index
  paper_colors.py swatch library books [--index FILE] [--json]
                                                books in a pantone-cli index: id, use, medium
  paper_colors.py swatch library list [--json] indexed books: use, medium, colors outside sRGB
  paper_colors.py swatch match INPUT ... [--library N] [--prefer lighter|nearest|darker]
                    [--top 3] [--colors 6] [--register] [--json]
                                                INPUT = CODE=HEX (palette entry), code, #hex or
                                                screenshot: code first, else a close color,
                                                lighter by default
  paper_colors.py swatch add CODE --from-library [--library N]
                                                register a code with its color-book value
  paper_colors.py swatch verify [CODE ...] [--library N --sample K]
                                                checklist to fill in from Pantone Connect
                                                (default: registered swatches not yet verified)
  paper_colors.py swatch verify --values FILE [--adopt]
                                                compare Connect HEX values; record in registry
  paper_colors.py swatch list [--json]         registered swatches
  paper_colors.py swatch ramp CODE|HEX [--steps N]   preview a derived ramp
  paper_colors.py swatch harmony CODE|HEX [--kind K ...] [--library N] [--json]
                                                analogous, complementary, ... in the book:
                                                Connect's own when indexed, else computed

Output: color swatches in a terminal (off with --no-color or $NO_COLOR).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import books  # noqa: E402
import colorlib as cl  # noqa: E402
import harmony  # noqa: E402
import library  # noqa: E402
import lint  # noqa: E402
import registry  # noqa: E402
import paths  # noqa: E402
import ramps  # noqa: E402
import term  # noqa: E402
import themes  # noqa: E402
import verify  # noqa: E402
from exporters import EXPORTERS  # noqa: E402


def _no_themes() -> int:
    print("no theme yet. Drop screenshots or color book files into "
          f"{paths.data_dir('inbox')} and ask Claude to register them (references/color-books.md).")
    return 0


def cmd_init(args) -> int:
    copied = paths.init(Path(args.source) if args.source else None)
    print(f"data folder: {paths.home()}")
    for item in copied:
        print(f"  copied {item}")
    if args.source and not copied:
        print(f"  nothing new to copy from {args.source}")
    return 0


def cmd_where(_args) -> int:
    print(f"home        {paths.home()}")
    print(f"swatches    {paths.swatches()}")
    print(f"palettes    {paths.palettes()}" + ("  (bundled template; run `init`)"
                                             if paths.palettes() == paths.TEMPLATE_PALETTES else ""))
    for name in paths.DATA_DIRS:
        print(f"{name:11} {paths.data_dir(name)}")
    return 0


def cmd_list(_args) -> int:
    all_themes, default = themes.load_all()
    if not all_themes:
        return _no_themes()
    for name, theme in all_themes.items():
        mark = " (default)" if name == default else ""
        anchors = ", ".join(f"{r}={theme.codes[r]}" for r in theme.hues)
        print(f"{name}{mark}\n    {theme.description}\n    {anchors}")
    return 0


def cmd_show(args) -> int:
    theme = themes.load(args.theme)
    print(f"{theme.name}: {theme.description}")
    print(f"{'hue':8} {'code':14} {'anchor':8} {'contrast':>8}  ramp light -> dark (* = anchor)")
    for role in theme.hues:
        steps = " ".join(h + ("*" if k == theme.anchor_step[role] else " ")
                         for k, h in enumerate(theme.ramps[role], 1))
        kind = "book" if all(theme.ramp_codes[role]) else "derived"
        print(f"{role:8} {theme.codes[role]:14} {theme.anchors[role]} "
              f"{cl.contrast_ratio(theme.anchors[role]):8.2f}  {steps} [{kind}]")
        print(f"{'':8} {'L*':>14} {'':8} {'':8}  "
              + " ".join(f"{cl.lightness(h):7.0f} " for h in theme.ramps[role]))
    for role, hex_c in theme.text.items():
        print(f"{role:9} = {theme.text_refs[role]:9} {hex_c}  contrast {cl.contrast_ratio(hex_c):.2f}")
    stats = themes.series_stats(theme)
    print(f"series safe by color alone: {stats['cvd_safe']} (CVD), {stats['gray_safe']} (grayscale)")
    return 0


def cmd_audit(args) -> int:
    all_themes, _ = themes.load_all()
    if not all_themes:
        return _no_themes()
    names = args.themes or list(all_themes)
    failed = False
    for name in names:
        if name not in all_themes:
            print(f"unknown theme {name!r}; choose from {sorted(all_themes)}", file=sys.stderr)
            return 2
        issues = themes.audit(all_themes[name])
        errors = [m for lvl, m in issues if lvl == "ERROR"]
        failed |= bool(errors)
        print(f"{name}: {'FAIL' if errors else 'PASS'}")
        for lvl, msg in issues:
            print(f"  {lvl:5} {msg}")
    return 1 if failed else 0


def cmd_export(args) -> int:
    theme = themes.load(args.theme)
    errors = [m for lvl, m in themes.audit(theme) if lvl == "ERROR"]
    if errors:
        print(f"refusing to export {theme.name}: audit errors {errors}", file=sys.stderr)
        return 1
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    unknown = [f for f in formats if f not in EXPORTERS]
    if unknown:
        print(f"unknown formats {unknown}; choose from {sorted(EXPORTERS)}", file=sys.stderr)
        return 2
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    stats = themes.series_stats(theme)
    for fmt in formats:
        filename, render = EXPORTERS[fmt]
        (out / filename).write_text(render(theme, stats))
        print(f"wrote {out / filename}")
    return 0


def cmd_lint(args) -> int:
    root = Path(args.path).expanduser().resolve()
    if not root.exists():
        print(f"no such path: {root}", file=sys.stderr)
        return 2
    name = args.theme or lint.detect_theme(root)
    theme = themes.load(name)
    source = "--theme" if args.theme else ("exported file" if name else "default")
    print(f"linting {root} against theme {theme.name!r} (from {source})")
    findings = lint.lint_tree(root, theme)
    base = root if root.is_dir() else root.parent
    groups: dict[tuple, list[lint.Finding]] = {}
    for f in findings:
        groups.setdefault((f.path, f.kind, f.value), []).append(f)
    for same in groups.values():
        more = f" (+{len(same) - 1} more in this file)" if len(same) > 1 else ""
        print(same[0].format(base) + more)
    print(f"{len(findings)} finding(s), {len(groups)} distinct")
    return 1 if findings else 0


# ------------------------------------------------------------------ pantone

def cmd_pantone_inbox(_args) -> int:
    inbox = paths.data_dir("inbox")
    files = registry.inbox_files(inbox)
    print(f"{len(files)} screenshot(s) in {inbox}")
    for f in files:
        print(f"  {f.name}")
    return 0


def cmd_pantone_sample(args) -> int:
    box = tuple(int(v) for v in args.box.split(",")) if args.box else None
    if box is not None and len(box) != 4:
        print("--box needs x0,y0,x1,y1", file=sys.stderr)
        return 2
    try:
        colors, profile, size = registry.dominant_colors(Path(args.image).expanduser(), box, args.top)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{args.image}: {size[0]}x{size[1]}, ICC profile: {profile} (converted to sRGB)")
    print(f"{'hex':8} {'share':>6}  bbox (x0,y0,x1,y1)")
    for c in colors:
        note = "  near-white (page background?)" if c["near_white"] else ""
        print(f"{c['hex']} {c['share']:6.1%}  {c['bbox']}{note}")
    return 0


def _lib_dir() -> Path:
    return paths.data_dir("libraries")


def cmd_pantone_add(args) -> int:
    if args.from_library:
        return _add_from_library(args)
    shot = Path(args.screenshot).expanduser() if args.screenshot else None
    if shot and not shot.is_file():
        print(f"no such screenshot: {shot}", file=sys.stderr)
        return 2
    entry = registry.add_swatch(args.code, args.name, args.hex, args.sampled, shot,
                               path=themes.swatches_path(),
                               archive=paths.data_dir("screenshots"))
    print(f"registered {' '.join(args.code.split())}: {entry}")
    return 0


def _add_from_library(args) -> int:
    hits = library.lookup_code(args.code, library.load_libraries(_lib_dir()), args.library)
    if not hits:
        print(f"{args.code!r} is in no indexed color book; `swatch library list`", file=sys.stderr)
        return 2
    if len({name for name, _ in hits}) > 1:
        names = ", ".join(sorted({name for name, _ in hits}))
        print(f"{args.code!r} is in several books ({names}); pick one with --library", file=sys.stderr)
        return 2
    name, color = hits[0]
    outcome = registry.register_from_library(color, name, themes.swatches_path())
    gamut = "" if color.in_gamut else "  (outside sRGB: screen approximation)"
    print(f"{outcome}: {color.code} {color.hex} from {name}{gamut}")
    return 1 if outcome.startswith("conflict") else 0


def _emit_json(data) -> int:
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def _book_line(book: dict | None) -> str:
    if not book:
        return "use/medium unknown"
    note = f"; {book['note']}" if book.get("note") else ""
    return f"{book.get('target') or '?'} - {book.get('medium') or '?'}{note}"


def cmd_library_add(args) -> int:
    import pantone_cli
    if args.from_pantone_cli or (args.file and pantone_cli.is_index(Path(args.file).expanduser())):
        index = pantone_cli.find_index(args.index or args.file)
        wanted = [b.strip() for b in args.books.split(",") if b.strip()] if args.books else None
        added = library.add_pantone_cli(index, _lib_dir(), wanted)
        print(f"pantone-cli index {index}: {len(added)} book(s). Use only color data you are licensed to use.")
        for name, stats in added:
            print(f"  indexed {name!r}: {stats['colors']} colors ({stats['out_of_gamut']} outside sRGB), "
                  f"{stats['relationships']} with Connect shades/harmonies; {_book_line(stats['book'])}")
        return 0
    if not args.file:
        print("give a color book FILE, or --from-pantone-cli", file=sys.stderr)
        return 2
    src = Path(args.file).expanduser()
    if not src.is_file():
        print(f"no such file: {src}", file=sys.stderr)
        return 2
    name, stats = library.add_library(src, _lib_dir(), args.name)
    print(f"indexed {name!r}: {stats['colors']} colors ({stats['out_of_gamut']} outside sRGB), "
          f"skipped {stats['skipped']}; models {stats['models']}")
    print(f"  {_book_line(library.load_meta(_lib_dir())[name]['book'])}")
    return 0


def cmd_library_books(args) -> int:
    import pantone_cli
    index_path = pantone_cli.find_index(args.index)
    index = pantone_cli.load_index(index_path)
    rows = [{**books.from_pantone_cli(s), "title": s.get("title", s["id"]),
             "colors": len(index["colorsByBook"][s["id"]])} for s in pantone_cli.book_summaries(index)]
    if args.json:
        return _emit_json({"index": str(index_path), "books": rows})
    print(f"{index_path}")
    for r in rows:
        print(f"  {r['id']:28} {r['colors']:5} colors  {r['title']}: {_book_line(r)}")
    return 0


def cmd_library_list(args) -> int:
    meta = library.load_meta(_lib_dir())
    if args.json:
        return _emit_json([{"name": n, **{k: v for k, v in m.items() if k != "relationships"},
                            "relationships": len(m["relationships"])} for n, m in meta.items()])
    if not meta:
        print(f"no color books indexed in {_lib_dir()}")
    for name, m in meta.items():
        share = m["out_of_gamut"] / m["colors"] if m["colors"] else 0
        rel = f", {len(m['relationships'])} with Connect harmonies" if m["relationships"] else ""
        print(f"{name}: {m['colors']} colors, {m['out_of_gamut']} ({share:.0%}) outside sRGB{rel}\n"
              f"    {_book_line(m['book'])}  [{m['source']}]")
    return 0


def _match_inputs(raw: str, top_colors: int, quiet: bool = False) -> list[tuple[str, str]]:
    """INPUT -> [(label, hex)]; a screenshot gives its dominant non-background colors."""
    path = Path(raw).expanduser()
    if path.is_file():
        colors, profile, _ = registry.dominant_colors(path, top=top_colors + 4)
        picked = [c for c in colors if not c["near_white"] and c["share"] >= 0.005][:top_colors]
        if not quiet:
            print(f"{path.name}: ICC {profile}; {len(picked)} swatch color(s)")
        return [(f"{c['hex']} @ {c['bbox']}", c["hex"]) for c in picked]
    return [(raw, cl.to_hex(cl.parse_hex(raw)))]


def _color_json(name: str, c, d: float) -> dict:
    return {"code": c.code, "name": c.name, "hex": c.hex, "lab_d65": [round(v, 2) for v in c.lab],
            "in_srgb": c.in_gamut, "book": name, "delta_e": round(d, 2),
            "grade": library.grade(d), "perceived": library.perceive(d)}


def _resolution_json(label: str, target: str | None, res: dict, top: int) -> dict:
    chosen = res["chosen"]
    return {"input": label, "target": target, "status": res["status"], "reason": res["reason"],
            "chosen": _color_json(*chosen) if chosen else None,
            "candidates": [_color_json(*c) for c in res["candidates"][:top]]}


def _print_resolution(label: str, res: dict, top: int) -> None:
    chosen = res["chosen"]
    if not chosen:
        print(f"{label}: {res['status']} - {res['reason']}")
        return
    name, c, d = chosen
    gamut = "  outside sRGB" if not c.in_gamut else ""
    print(f"{label}: {res['status']} -> {term.swatch(c.hex)}{c.code} {c.hex} [{name}]  dE {d:.1f} "
          f"{library.perceive(d)}  ({res['reason']}){gamut}")
    for cname, cc, cd in res["candidates"][:top]:
        mark = "*" if cc is c else " "
        print(f"    {mark} {term.swatch(cc.hex)}{library.grade(cd):5} dE {cd:4.1f}  L* {cc.lab[0]:5.1f}  "
              f"{cc.code:16} {cc.hex}  [{cname}]")


def _resolve_inputs(args, libs) -> list[tuple[str, str | None, dict]]:
    """Each INPUT -> [(label, target hex, resolution)]; ValueError on unreadable input."""
    out = []
    for raw in args.inputs:
        code, _, hex_part = raw.partition("=")
        if hex_part:                                   # palette entry: CODE=HEX
            hex_c = cl.to_hex(cl.parse_hex(hex_part))
            res = library.resolve(code, hex_c, libs, args.library, args.prefer, max(args.top, 8))
            out.append((f"{code} (target {hex_c}, L* {cl.lightness(hex_c):.1f})", hex_c, res))
            continue
        if library.lookup_any(raw, libs, args.library):  # bare code
            out.append((raw, None, library.resolve(raw, None, libs, args.library, args.prefer)))
            continue
        try:
            targets = _match_inputs(raw, args.colors, quiet=args.json)  # screenshot or #hex
        except (ValueError, RuntimeError) as exc:
            raise ValueError(f"{raw}: not a screenshot, #hex or known code ({exc})") from exc
        for label, hex_c in targets:
            res = library.resolve(None, hex_c, libs, args.library, args.prefer, max(args.top, 8))
            out.append((f"{label} (L* {cl.lightness(hex_c):.1f})", hex_c, res))
    return out


def cmd_match(args) -> int:
    libs = library.load_libraries(_lib_dir())
    if not libs:
        print("no color books indexed; `swatch library add <file>` or "
              "`swatch library add --from-pantone-cli` first", file=sys.stderr)
        return 2
    try:
        resolved = _resolve_inputs(args, libs)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    registered = []
    if args.register:
        for _, _, res in resolved:
            if res["status"] in ("exact", "approx"):
                name, color, _ = res["chosen"]
                registered.append((color.code, registry.register_from_library(color, name, themes.swatches_path())))
            elif res["chosen"]:
                registered.append((res["chosen"][1].code, f"skipped: dE {res['chosen'][2]:.1f} is too far"))
    if args.json:
        return _emit_json({"method": "CIEDE2000", "disclaimer": library.DISCLAIMER,
                           "results": [_resolution_json(lb, t, r, args.top) for lb, t, r in resolved],
                           "registered": [{"code": c, "outcome": o} for c, o in registered]})
    for label, _, res in resolved:
        _print_resolution(label, res, args.top)
    for code, outcome in registered:
        print(f"register {code}: {outcome}" if not outcome.startswith("skipped")
              else f"skip {code}: {outcome[9:]}; confirm it by hand")
    print(f"note: {library.DISCLAIMER}")
    return 0


def _expected_from_registry(only_unverified: bool) -> dict[str, dict]:
    out = {}
    for code, s in registry.load_swatches(themes.swatches_path()).items():
        if only_unverified and s.get("verified", {}).get("status") == "ok":
            continue
        out[verify.norm(code)] = {"code": code, "source": s.get("source", s["method"]),
                                  "our_hex": s["hex"], "outside_srgb": "yes" if "outside" in s.get("note", "") else ""}
    return out


def _expected_from_books(codes, libs, book) -> dict[str, dict]:
    out = {}
    for code in codes:
        hits = library.lookup_code(code, libs, book)
        if len({n for n, _ in hits}) != 1:
            raise ValueError(f"{code!r}: found in {len({n for n, _ in hits})} indexed books; use --library")
        name, c = hits[0]
        out[verify.norm(c.code)] = {"code": c.code, "source": name, "our_hex": c.hex,
                                    "outside_srgb": "" if c.in_gamut else "yes"}
    return out


def cmd_verify(args) -> int:
    libs = library.load_libraries(_lib_dir())
    base = paths.data_dir("verify")
    if args.values:
        connect, rows = verify.parse_values(Path(args.values).expanduser().read_text())
        # What we hold per code: the registry wins, then the checklist row, then a color book.
        expected = {k: {f: r[f] for f in verify.FIELDS[:4]} for k, r in rows.items()}
        registered = _expected_from_registry(only_unverified=False)
        for key in connect:
            if key in registered:
                expected[key] = registered[key]
            elif key not in expected and libs:
                try:
                    expected.update(_expected_from_books([key], libs, args.library))
                except ValueError:
                    pass  # reported as "unknown"
        report = verify.compare(connect, expected)
        for r in sorted(report, key=lambda r: -r.get("delta_e", -1)):
            de = f"dE {r['delta_e']:5.2f}" if "delta_e" in r else " " * 8
            gamut = "  outside sRGB" if r.get("outside_srgb") == "yes" else ""
            print(f"{r['status']:8} {de}  {r['code']:16} ours {r.get('our_hex', '-'):8} "
                  f"Connect {r.get('connect_hex', '-'):8} [{r.get('source', '')}]{gamut}")
        swatches = registry.load_swatches(themes.swatches_path())
        updated = verify.record(swatches, report, args.adopt)
        if updated:
            registry._save(swatches, themes.swatches_path())
        counts = {s: sum(r["status"] == s for r in report) for s in ("ok", "check", "mismatch", "missing", "unknown")}
        print(f"{counts}; registry updated for {len(updated)} swatch(es)" + (" (adopted Connect hex)" if args.adopt else ""))
        return 1 if counts["mismatch"] or counts["check"] else 0
    if args.sample:
        if not args.library:
            print("--sample needs --library", file=sys.stderr)
            return 2
        picked = verify.sample_codes(next(iter(library._select(libs, args.library).values())), args.sample, args.seed)
        expected = _expected_from_books([c.code for c in picked], libs, args.library)
        label = f"sample-{library._slug(args.library)}"
    elif args.codes:
        registered = _expected_from_registry(only_unverified=False)
        expected = {verify.norm(c): registered[verify.norm(c)] for c in args.codes if verify.norm(c) in registered}
        rest = [c for c in args.codes if verify.norm(c) not in registered]
        expected.update(_expected_from_books(rest, libs, args.library) if rest else {})
        label = "codes"
    else:
        expected = _expected_from_registry(only_unverified=True)
        label = "registered"
        if not expected:
            print("nothing to verify: no registered swatches without an ok verification")
            return 0
    path = verify.write_checklist(list(expected.values()),
                                  base / f"{dt.date.today().isoformat()}-{label}.tsv")
    print(f"wrote {path} ({len(expected)} codes). Fill connect_hex from Pantone Connect, then:\n"
          f"  paper_colors.py swatch verify --values {path}")
    for row in expected.values():
        print(f"  {row['code']:16} ours {row['our_hex']}  [{row['source']}]" + ("  outside sRGB" if row["outside_srgb"] else ""))
    return 0


def cmd_pantone_import(args) -> int:
    path = Path(args.file).expanduser()
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 2
    report = registry.import_ase(path, path=themes.swatches_path(), dry_run=args.dry_run)
    for row in report:
        print(f"{row['status']:9} {row['code']:16} {row['hex'] or '-':8}  {row['detail']}")
    counts = {s: sum(r["status"] == s for r in report) for s in ("added", "unchanged", "conflict", "skipped")}
    verb = "would add" if args.dry_run else "added"
    print(f"{verb} {counts['added']}, unchanged {counts['unchanged']}, "
          f"conflicts {counts['conflict']}, skipped {counts['skipped']} ({len(report)} swatches in file)")
    return 1 if counts["conflict"] else 0


def cmd_pantone_list(args) -> int:
    swatches = registry.load_swatches(themes.swatches_path())
    if args.json:
        return _emit_json({"path": str(themes.swatches_path()),
                           "swatches": [{"code": code, **s} for code, s in swatches.items()]})
    print(f"{len(swatches)} swatch(es) in {themes.swatches_path()}")
    for code, s in swatches.items():
        check = f" (sampled {s['sampled']}, dE {s['sample_delta_e']})" if "sampled" in s else ""
        print(f"  {term.swatch(s['hex'])}{code:16} {s['hex']}  L*={cl.lightness(s['hex']):5.1f}  {s.get('name', '')}"
              f"  [{s['method']}]{check}")
    return 0


def cmd_pantone_ramp(args) -> int:
    swatches = registry.load_swatches(themes.swatches_path())
    key = " ".join(args.color.split())
    hex_c = swatches[key]["hex"] if key in swatches else cl.to_hex(cl.parse_hex(key))
    ramp, k = ramps.derive(hex_c, args.steps)
    for i, h in enumerate(ramp, 1):
        mark = "  <- anchor" if i == k + 1 else ""
        print(f"step {i}: {term.swatch(h)}{h}  L*={cl.lightness(h):5.1f}  contrast {cl.contrast_ratio(h):5.2f}{mark}")
    return 0


def _anchor(raw: str, libs, book: str | None) -> tuple[str, str | None]:
    """Registered code, book code or #hex -> (hex, code or None)."""
    key = " ".join(raw.split())
    swatches = registry.load_swatches(themes.swatches_path())
    if key in swatches:
        return swatches[key]["hex"], key
    hits = library.lookup_any(key, libs, book) if libs else []
    if hits:
        return hits[0][1].hex, hits[0][1].code
    return cl.to_hex(cl.parse_hex(key)), None


def cmd_pantone_harmony(args) -> int:
    lib_dir = _lib_dir()
    libs, meta = library.load_libraries(lib_dir), library.load_meta(lib_dir)
    hex_c, code = _anchor(args.color, libs, args.library)
    kinds = tuple(args.kind) if args.kind else harmony.KINDS
    found = harmony.harmonies(hex_c, code, libs, meta, args.library, kinds)
    if args.json:
        return _emit_json({"anchor": {"code": code, "hex": hex_c}, "library": args.library,
                           "harmonies": found, "disclaimer": library.DISCLAIMER})
    print(f"anchor {term.swatch(hex_c)}{code or ''} {hex_c}" + (f"  [{args.library}]" if args.library else ""))
    if not libs:
        print("  (no color book indexed: showing computed sRGB targets only)")
    for kind, rows in found.items():
        print(f"{kind.lower().replace('_', '-')}  [{rows[0]['source'] if rows else '-'}]")
        for r in rows:
            if r["code"]:
                far = f"  {library.NO_GOOD_MATCH}" if r["delta_e"] and r["delta_e"] >= 10 else ""
                de = f"dE {r['delta_e']:4.1f} from {r['target']}" if r["source"] == "computed" else "Pantone Connect"
                print(f"    {term.swatch(r['hex'])}{r['code']:16} {r['hex']}  {de}  [{r['book']}]{far}")
            else:
                print(f"    {term.swatch(r['target'])}{r['target']}")
    print("next: put candidates in a theme and run `audit`; it checks contrast, CVD and grayscale.")
    return 0


def _harmony_kind(text: str) -> str:
    kind = text.upper().replace("-", "_")
    if kind not in harmony.KINDS:
        raise argparse.ArgumentTypeError(f"unknown harmony {text!r}; one of "
                                         + ", ".join(k.lower().replace("_", "-") for k in harmony.KINDS))
    return kind


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-color", action="store_true", help="no terminal color swatches")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--from", dest="source")
    p.set_defaults(func=cmd_init)
    sub.add_parser("where").set_defaults(func=cmd_where)
    sub.add_parser("list").set_defaults(func=cmd_list)
    p = sub.add_parser("show")
    p.add_argument("theme", nargs="?")
    p.set_defaults(func=cmd_show)
    p = sub.add_parser("audit")
    p.add_argument("themes", nargs="*")
    p.set_defaults(func=cmd_audit)
    p = sub.add_parser("export")
    p.add_argument("theme")
    p.add_argument("--out", required=True)
    p.add_argument("--formats", default="py,sty,json,svg")
    p.set_defaults(func=cmd_export)
    p = sub.add_parser("lint")
    p.add_argument("path")
    p.add_argument("--theme")
    p.set_defaults(func=cmd_lint)

    pan = sub.add_parser("swatch").add_subparsers(dest="pcmd", required=True)
    pan.add_parser("inbox").set_defaults(func=cmd_pantone_inbox)
    p = pan.add_parser("list")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_pantone_list)
    p = pan.add_parser("sample")
    p.add_argument("image")
    p.add_argument("--box")
    p.add_argument("--top", type=int, default=8)
    p.set_defaults(func=cmd_pantone_sample)
    p = pan.add_parser("add")
    p.add_argument("code")
    p.add_argument("--name", default="")
    p.add_argument("--hex")
    p.add_argument("--sampled")
    p.add_argument("--screenshot")
    p.add_argument("--from-library", action="store_true")
    p.add_argument("--library")
    p.set_defaults(func=cmd_pantone_add)
    lib = pan.add_parser("library").add_subparsers(dest="lcmd", required=True)
    p = lib.add_parser("add")
    p.add_argument("file", nargs="?")
    p.add_argument("--name")
    p.add_argument("--from-pantone-cli", action="store_true")
    p.add_argument("--index")
    p.add_argument("--books")
    p.set_defaults(func=cmd_library_add)
    p = lib.add_parser("books")
    p.add_argument("--index")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_library_books)
    p = lib.add_parser("list")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_library_list)
    p = pan.add_parser("match")
    p.add_argument("inputs", nargs="+")
    p.add_argument("--library")
    p.add_argument("--top", type=int, default=3)
    p.add_argument("--colors", type=int, default=6)
    p.add_argument("--prefer", choices=library.PREFERENCES, default="lighter")
    p.add_argument("--register", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_match)
    p = pan.add_parser("import")
    p.add_argument("file")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_pantone_import)
    p = pan.add_parser("verify")
    p.add_argument("codes", nargs="*")
    p.add_argument("--library")
    p.add_argument("--sample", type=int)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--values")
    p.add_argument("--adopt", action="store_true")
    p.set_defaults(func=cmd_verify)
    p = pan.add_parser("ramp")
    p.add_argument("color")
    p.add_argument("--steps", type=int, default=5)
    p.set_defaults(func=cmd_pantone_ramp)
    p = pan.add_parser("harmony")
    p.add_argument("color")
    p.add_argument("--kind", action="append", type=_harmony_kind,
                   help="analogous, complementary, split-complementary, triadic, tetradic, monochromatic")
    p.add_argument("--library")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_pantone_harmony)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    no_color = "--no-color" in argv                    # accepted anywhere on the line
    args = _parser().parse_args([a for a in argv if a != "--no-color"])
    term.disable(no_color)                             # per call, so a library caller can re-enable
    try:
        return args.func(args)
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
