# sqlite-curses

A terminal-based interactive SQLite editor built with Python curses. Designed to be fully usable from a phone keyboard — no Tab, Escape, Ctrl, or arrow keys required.

## Features

- **Three-panel layout** — schema tree on the left, SQL editor top-right, results bottom-right
- **Multi-line SQL editor** — wraps long lines, scrolls vertically, cursor tracked through wrapped text
- **Schema tree** — shows tables, views, and triggers; expand/collapse to see columns with type, PK, and index indicators
- **Results panel** — vertical and horizontal scrolling, visual scrollbar
- **CSV export** — export current results to a timestamped `.csv` file
- **File browser** — navigate directories to open a different database or create a new one
- **Phone-friendly** — all navigation available via number keys (`5`/`6`/`4`/`7` = up/down/left/right); `@` as command modifier; `$` as Tab substitute

## Requirements

- Python 3
- `curses` (standard library — included on Linux/macOS)
- SQLite3 (standard library)

## Usage

```bash
python sqlite_curses.py <database.db>
```

A database path is required. If the file does not exist, SQLite will create it.

## Key Bindings

### Panel Switching
| Key | Action |
|-----|--------|
| `Tab` or `$` | Cycle to next panel (Left → Editor → Results → Left) |

### SQL Editor (right panel, top)
| Key | Action |
|-----|--------|
| `Enter` | New line |
| `←` `→` `↑` `↓` | Move cursor (also `4` `7` `5` `6`) |
| `Backspace` | Delete character left / merge lines |
| `Del` | Forward delete character / merge lines |
| `@` | Enter command mode |

**Editor command mode** (`@` then):
| Key | Action |
|-----|--------|
| `Enter` | Execute SQL |
| `c` | Clear editor |
| `e` | Export results to CSV |
| `f` | Open file browser |
| `5` `6` `4` `7` | Move cursor (up/down/left/right) |
| `q` | Quit |
| `@` | Exit command mode |

### Schema Tree (left panel)
| Key | Action |
|-----|--------|
| `5` or `↑` | Move cursor up |
| `6` or `↓` | Move cursor down |
| `4` or `←` | Scroll content left |
| `7` or `→` | Scroll content right |
| `Space` | Expand / collapse item |
| `$` or `Tab` | Switch to SQL editor |
| `@` | Enter command mode |

**Left panel command mode** (`@` then):
| Key | Action |
|-----|--------|
| `e` | Export results to CSV |
| `f` | Open file browser |
| `q` | Quit |
| `@` | Exit command mode |

### Results Panel (right panel, bottom)
| Key | Action |
|-----|--------|
| `5` or `↑` | Scroll up |
| `6` or `↓` | Scroll down |
| `4` or `←` | Scroll left |
| `7` or `→` | Scroll right |
| `$` or `Tab` | Switch to left panel |
| `@` | Enter command mode |

**Results command mode** (`@` then):
| Key | Action |
|-----|--------|
| `e` | Export results to CSV |
| `f` | Open file browser |
| `q` | Quit |
| `@` | Exit command mode |

### File Browser
| Key | Action |
|-----|--------|
| `5` or `↑` | Move up |
| `6` or `↓` | Move down |
| `$` or `Tab` | Switch pane (directories ↔ files) |
| `Enter` | Select file / open directory |
| `n` | Create new database (prompts for name, auto-appends `.db`) |
| `q` | Cancel and return |

## Schema Tree Indicators

- `+` — collapsed (press Space to expand)
- `-` — expanded (press Space to collapse)
- `[PK]` — primary key column
- `[I]` — indexed column

## Quote-Aware Command Detection

When the cursor is inside a single-quoted (`'`) or double-quoted (`"`) string in the editor, `@` and `$` are passed through as literal characters rather than triggering command mode or panel switching. The status bar shows `[IN ']` or `[IN "]` when this is active.

## CSV Export

`@e` (available from any panel's command mode) writes the current results to a file named `results_YYYYMMDD_HHMMSS.csv` in the same directory as the open database. The filename is confirmed in the Results panel header.

## File Structure

```
sqlite_curses.py   — main application
file_browser.py    — modal file/directory picker
```
