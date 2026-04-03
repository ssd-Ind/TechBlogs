#!/usr/bin/env python3
"""
rename_files.py — Smart File & Directory Renamer
=================================================
Features:
  • Replaces spaces and special characters with underscores (or custom sep)
  • Unicode normalization (NFKD) + transliteration for non-English names
  • Handles accented, CJK, Cyrillic, Arabic, and other scripts
  • Dry-run mode (preview without making changes)
  • Undo / rollback from JSON log
  • Conflict resolution with auto-numbering
  • Preserves file extensions during rename
  • Case conversion: lower, upper, title, snake, camel, original
  • Verbose and quiet logging
  • Recursive or single-level processing
  • Regex-based include/exclude filters
  • CLI argument parsing (argparse)
  • Cross-platform (Windows, macOS, Linux)
"""

import os
import re
import sys
import json
import unicodedata
import argparse
import logging
from pathlib import Path
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
#  Transliteration map for common non-Latin scripts
# ─────────────────────────────────────────────────────────────────────────────
TRANSLITERATION_MAP = {
    # German umlauts
    'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
    'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue',
    # Nordic / Scandinavian
    'å': 'aa', 'Å': 'Aa', 'ø': 'oe', 'Ø': 'Oe',
    'æ': 'ae', 'Æ': 'Ae', 'þ': 'th', 'Þ': 'Th',
    # Spanish / Portuguese
    'ñ': 'n',  'Ñ': 'N',  'ç': 'c',  'Ç': 'C',
    # Cyrillic (Russian) – key characters
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh',
    'з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o',
    'п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts',
    'ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu',
    'я':'ya',
    'А':'A','Б':'B','В':'V','Г':'G','Д':'D','Е':'E','Ё':'Yo','Ж':'Zh',
    'З':'Z','И':'I','Й':'Y','К':'K','Л':'L','М':'M','Н':'N','О':'O',
    'П':'P','Р':'R','С':'S','Т':'T','У':'U','Ф':'F','Х':'Kh','Ц':'Ts',
    'Ч':'Ch','Ш':'Sh','Щ':'Sch','Ъ':'','Ы':'Y','Ь':'','Э':'E','Ю':'Yu',
    'Я':'Ya',
    # Greek
    'α':'a','β':'b','γ':'g','δ':'d','ε':'e','ζ':'z','η':'i','θ':'th',
    'ι':'i','κ':'k','λ':'l','μ':'m','ν':'n','ξ':'x','ο':'o','π':'p',
    'ρ':'r','σ':'s','τ':'t','υ':'y','φ':'ph','χ':'ch','ψ':'ps','ω':'o',
    # Arabic transliteration (basic)
    'ا':'a','ب':'b','ت':'t','ث':'th','ج':'j','ح':'h','خ':'kh','د':'d',
    'ذ':'dh','ر':'r','ز':'z','س':'s','ش':'sh','ص':'s','ض':'d','ط':'t',
    'ظ':'z','ع':'a','غ':'gh','ف':'f','ق':'q','ك':'k','ل':'l','م':'m',
    'ن':'n','ه':'h','و':'w','ي':'y',
}


# ─────────────────────────────────────────────────────────────────────────────
#  Core sanitization logic
# ─────────────────────────────────────────────────────────────────────────────
def transliterate(text: str) -> str:
    """Apply character-by-character transliteration using the map."""
    return ''.join(TRANSLITERATION_MAP.get(ch, ch) for ch in text)


def unicode_normalize(text: str) -> str:
    """
    NFKD decomposition → strip combining marks (accents) → re-encode as ASCII.
    Handles: café→cafe, naïve→naive, résumé→resume, etc.
    """
    normalized = unicodedata.normalize('NFKD', text)
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


def sanitize_name(
    name: str,
    separator: str = '_',
    case_mode: str = 'original',
    transliterate_flag: bool = True,
    normalize_unicode: bool = True,
) -> str:
    """
    Fully sanitize a filename stem (without extension).

    Steps:
      1. Apply transliteration map (Cyrillic, Arabic, Greek, umlauts…)
      2. Unicode NFKD normalization (strip accent marks)
      3. Remove or replace all characters not safe for filenames
      4. Collapse repeated separators
      5. Strip leading/trailing separators
      6. Apply case conversion
    """
    if transliterate_flag:
        name = transliterate(name)

    if normalize_unicode:
        name = unicode_normalize(name)

    # Force ASCII (drop anything that survived normalization, e.g. CJK)
    name = name.encode('ascii', errors='ignore').decode('ascii')

    # Replace any unsafe / whitespace / special chars with separator
    name = re.sub(r"[^\w\-.]", separator, name)

    # Replace underscores and hyphens with the chosen separator
    name = re.sub(r"[\s_\-]+", separator, name)

    # Collapse multiple consecutive separators
    sep_escaped = re.escape(separator)
    name = re.sub(rf"{sep_escaped}+", separator, name)

    # Strip leading/trailing separator
    name = name.strip(separator)

    # Case conversion
    if   case_mode == 'lower':  name = name.lower()
    elif case_mode == 'upper':  name = name.upper()
    elif case_mode == 'title':  name = name.replace(separator, ' ').title().replace(' ', separator)
    elif case_mode == 'snake':  name = name.lower()
    elif case_mode == 'camel':
        parts = name.split(separator)
        name  = parts[0].lower() + ''.join(p.title() for p in parts[1:])

    return name or 'unnamed'


# ─────────────────────────────────────────────────────────────────────────────
#  Conflict resolution
# ─────────────────────────────────────────────────────────────────────────────
def resolve_conflict(target: Path) -> Path:
    """Append _1, _2, … to the stem until the path is free."""
    if not target.exists():
        return target
    stem, suffix, parent = target.stem, target.suffix, target.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


# ─────────────────────────────────────────────────────────────────────────────
#  Undo helpers
# ─────────────────────────────────────────────────────────────────────────────
def save_log(log_entries: list, log_path: Path) -> None:
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(log_entries, f, indent=2, ensure_ascii=False)


def undo_from_log(log_path: Path, dry_run: bool = False) -> None:
    """Reverse all renames recorded in a JSON log file."""
    if not log_path.exists():
        logging.error(f"Log file not found: {log_path}")
        sys.exit(1)

    with open(log_path, encoding='utf-8') as f:
        entries = json.load(f)

    for entry in reversed(entries):
        src, dst = Path(entry['new']), Path(entry['old'])
        if not src.exists():
            logging.warning(f"SKIP (missing): {src}")
            continue
        if dry_run:
            logging.info(f"[DRY UNDO] {src} → {dst}")
        else:
            src.rename(dst)
            logging.info(f"UNDO: {src} → {dst}")


# ─────────────────────────────────────────────────────────────────────────────
#  Main rename engine
# ─────────────────────────────────────────────────────────────────────────────
def rename_entries(
    root: Path,
    *,
    separator: str       = '_',
    case_mode: str       = 'original',
    dry_run: bool        = False,
    recursive: bool      = True,
    rename_dirs: bool    = True,
    rename_files: bool   = True,
    transliterate_flag: bool = True,
    normalize_unicode: bool  = True,
    include_pattern: str = None,
    exclude_pattern: str = None,
    verbose: bool        = True,
) -> list:
    """
    Walk *root* and rename every entry whose name differs after sanitization.
    Returns a list of rename log dicts: {old, new, type, timestamp}.
    """
    log_entries = []
    include_re  = re.compile(include_pattern) if include_pattern else None
    exclude_re  = re.compile(exclude_pattern) if exclude_pattern else None

    def should_process(name: str) -> bool:
        if include_re and not include_re.search(name):
            return False
        if exclude_re and exclude_re.search(name):
            return False
        return True

    def process_path(path: Path, kind: str) -> None:
        name = path.name

        if not should_process(name):
            if verbose:
                logging.debug(f"SKIP (filter): {path}")
            return

        if kind == 'file':
            stem      = path.stem
            extension = path.suffix
            new_stem  = sanitize_name(
                stem,
                separator          = separator,
                case_mode          = case_mode,
                transliterate_flag = transliterate_flag,
                normalize_unicode  = normalize_unicode,
            )
            new_name = new_stem + extension
        else:
            new_name = sanitize_name(
                name,
                separator          = separator,
                case_mode          = case_mode,
                transliterate_flag = transliterate_flag,
                normalize_unicode  = normalize_unicode,
            )

        if new_name == name:
            return

        new_path = resolve_conflict(path.parent / new_name)

        if verbose:
            status = '[DRY]' if dry_run else '[RENAME]'
            logging.info(f"{status} ({kind}) {path}  →  {new_path}")

        if not dry_run:
            path.rename(new_path)

        log_entries.append({
            'type':      kind,
            'old':       str(path),
            'new':       str(new_path),
            'timestamp': datetime.now().isoformat(),
        })

    if recursive:
        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            current = Path(dirpath)
            if rename_files:
                for fname in filenames:
                    process_path(current / fname, 'file')
            if rename_dirs and current != root:
                process_path(current, 'dir')
    else:
        for entry in root.iterdir():
            if entry.is_file() and rename_files:
                process_path(entry, 'file')
            elif entry.is_dir() and rename_dirs:
                process_path(entry, 'dir')

    return log_entries


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog        = 'rename_files.py',
        description = 'Smart file/directory renamer with Unicode support.',
        formatter_class = argparse.RawDescriptionHelpFormatter,
        epilog = """
Examples:
  python rename_files.py /path/to/folder
  python rename_files.py /path/to/folder --dry-run
  python rename_files.py /path/to/folder --separator - --case lower
  python rename_files.py /path/to/folder --exclude "\\.git"
  python rename_files.py --undo rename_log.json
        """
    )

    p.add_argument('directory', nargs='?', help='Root directory to process.')
    p.add_argument('--dry-run', '-n', action='store_true',
                   help='Preview changes without renaming anything.')
    p.add_argument('--separator', '-s', default='_', metavar='SEP',
                   help='Replacement character for spaces/specials (default: _).')
    p.add_argument('--case', '-c',
                   choices=['original','lower','upper','title','snake','camel'],
                   default='original', help='Case conversion mode.')
    p.add_argument('--no-recursive', action='store_true',
                   help='Only process top-level entries.')
    p.add_argument('--files-only', action='store_true',
                   help='Rename files only, skip directories.')
    p.add_argument('--dirs-only', action='store_true',
                   help='Rename directories only, skip files.')
    p.add_argument('--no-transliterate', action='store_true',
                   help='Disable transliteration.')
    p.add_argument('--no-normalize', action='store_true',
                   help='Disable Unicode normalization.')
    p.add_argument('--include', metavar='REGEX',
                   help='Only process names matching this regex.')
    p.add_argument('--exclude', metavar='REGEX',
                   help='Skip names matching this regex.')
    p.add_argument('--log', metavar='FILE', default='rename_log.json',
                   help='Path for the JSON rename log.')
    p.add_argument('--undo', metavar='LOG_FILE',
                   help='Undo renames from log file.')
    p.add_argument('--quiet', '-q', action='store_true',
                   help='Suppress per-file output.')
    p.add_argument('--verbose', '-v', action='store_true',
                   help='Show debug output.')

    return p


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else (
                logging.WARNING if args.quiet else logging.INFO)
    logging.basicConfig(level=log_level, format='%(levelname)-8s %(message)s')

    if args.undo:
        undo_from_log(Path(args.undo), dry_run=args.dry_run)
        return

    if not args.directory:
        args.directory = input("Enter directory path: ").strip()

    root = Path(args.directory).expanduser().resolve()
    if not root.is_dir():
        logging.error(f"Not a valid directory: {root}")
        sys.exit(1)

    if args.dry_run:
        logging.info("=== DRY RUN — no files will be changed ===")

    entries = rename_entries(
        root,
        separator          = args.separator,
        case_mode          = args.case,
        dry_run            = args.dry_run,
        recursive          = not args.no_recursive,
        rename_dirs        = not args.files_only,
        rename_files       = not args.dirs_only,
        transliterate_flag = not args.no_transliterate,
        normalize_unicode  = not args.no_normalize,
        include_pattern    = args.include,
        exclude_pattern    = args.exclude,
        verbose            = not args.quiet,
    )

    files_count = sum(1 for e in entries if e['type'] == 'file')
    dirs_count  = sum(1 for e in entries if e['type'] == 'dir')
    logging.info(
        f"\n{'[DRY RUN] ' if args.dry_run else ''}Done. "
        f"Files renamed: {files_count} | Dirs renamed: {dirs_count}"
    )

    if entries and not args.dry_run:
        log_path = Path(args.log)
        save_log(entries, log_path)
        logging.info(f"Rename log saved to: {log_path}")


if __name__ == '__main__':
    main()
