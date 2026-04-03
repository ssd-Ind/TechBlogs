# 🐍 FileRenamer Pro

> **Smart File & Directory Renamer in Python** — with Unicode normalization, transliteration, dry-run mode, undo support, and more.

[![Python 3.x](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub Pages](https://img.shields.io/badge/demo-live-brightgreen)](https://ssd-Ind.github.io/TechBlogs/)

---

## ✨ Features

- 🌍 **Non-English Support** — Transliterates Cyrillic, Greek, Arabic, German umlauts, and more
- 🔤 **Unicode Normalization** — NFKD decomposition with accent stripping
- 🔁 **Undo / Rollback** — JSON logging with `--undo` support
- 🛡 **Conflict Resolution** — Auto-appends `_1`, `_2` to prevent overwrites
- 👁 **Dry Run Mode** — Preview changes with `--dry-run`
- 🔡 **Case Conversion** — 6 modes: original, lower, upper, title, snake, camel
- 🚫 **Extension Preservation** — Never alters file extensions
- ⚙ **Full CLI** — Powered by argparse with comprehensive options
- 🖥 **Cross-Platform** — Works on Linux, macOS, and Windows

---

## 🚀 Quick Start

```bash
# Download
curl -O https://raw.githubusercontent.com/ssd-Ind/TechBlogs/main/rename_files.py

# Preview changes (dry run)
python3 rename_files.py /path/to/folder --dry-run

# Execute
python3 rename_files.py /path/to/folder

# Undo if needed
python3 rename_files.py --undo rename_log.json
