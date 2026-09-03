# sqlite-curses

A terminal-based interactive SQLite editor built with Python curses. Designed to be fully usable from a phone keyboard — no Tab, Escape, Ctrl, or arrow keys required.



*In a large phone:*

<img width="430" height="431" alt="Screenshot_20260408-202811" src="https://github.com/user-attachments/assets/86241916-e399-4477-b667-d7bb323c3243" />


*In a small phone:*

<img width="428" height="196" alt="Screenshot_20260408-202543" src="https://github.com/user-attachments/assets/cabfafe6-c816-4b90-a595-997af064a744" />


*The built-in file browser:*

<img width="432" height="431" alt="Screenshot_20260408-202908" src="https://github.com/user-attachments/assets/bea36b28-cba0-43fa-8024-a723b8bda8f3" />



## Features

- **Three-panel layout** — schema tree on the left, SQL editor top-right, results bottom-right
- **Multi-line SQL editor** — wraps long lines, scrolls vertically, cursor tracked through wrapped text; supports multiple statements separated by `;`
- **Schema tree** — shows tables, views, and triggers; expand/collapse to see columns with type, PK, and index indicators; horizontal scrolling for long names
- **Results panel** — vertical and horizontal scrolling, visual scrollbar; cell values with newlines or tabs are shown on a single line so they never corrupt the layout
- **SQL buffers** — up to 4 independent editor buffers; switch between them while keeping results visible
- **Copy SQL** — copy editor contents to clipboard via OSC 52 (works in most web/SSH terminals), with fallback to `xclip`/`xsel`, or saves to a `.sql` file
- **Export menu** — `@e` opens a submenu to export results to CSV or save the current SQL to a `.sql` file
- **File browser** — navigate directories to open a different database or create a new one
- **Resizable panels** — Shift+arrow keys move the vertical and horizontal dividers to reclaim screen space
- **Phone-friendly** — all navigation available via number keys (`5`/`6`/`4`/`7` = up/down/left/right); `@` as command modifier; `$` as Tab substitute

## Requirements

- Python 3
- `curses` (standard library — included on Linux/macOS)
- SQLite3 (standard library)

## Usage

```bash
# Open an existing database
python sqlite_curses.py <database.db>

# Create a new database
python sqlite_curses.py --create <database.db>
python sqlite_curses.py -c <database.db>
```

If the database file does not exist and `--create` is not specified, the program will exit with a friendly error rather than silently creating an empty file.

## Key Bindings

### Panel Switching
| Key | Action |
|-----|--------|
| `Tab` or `$` | Cycle to next panel (Left → Editor → Results → Left) |

### Resizing Panels (PC only)
| Key | Action |
|-----|--------|
| `Shift+←` `Shift+→` | Move the vertical divider left / right |
| `Shift+↑` `Shift+↓` | Move the horizontal divider up / down |

Dividers adjust relative to the default proportions, so the layout continues to scale correctly if you resize the window.

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
| `e` | Export menu (see below) |
| `y` | Copy SQL to clipboard |
| `t` | Enter buffer/tab mode |
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
| `e` | Export menu (see below) |
| `y` | Copy SQL to clipboard |
| `t` | Enter buffer/tab mode |
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
| `e` | Export menu (see below) |
| `y` | Copy SQL to clipboard |
| `t` | Enter buffer/tab mode |
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

## Multiple Statements

The editor supports multiple SQL statements in a single buffer, separated by `;`:

```sql
INSERT INTO users (name) VALUES ('alice');
INSERT INTO users (name) VALUES ('bob');
SELECT * FROM users;
```

All statements execute as a single atomic batch — if any one fails, the entire batch rolls back. Results displayed are from the last statement that returned rows. If all statements were write operations, a summary is shown: `OK (3 statements, 2 row(s) affected)`.

Semicolons inside quoted strings are handled correctly and not treated as statement separators.

## Multi-line Cell Values

When a column contains newlines, tabs, or other control characters, the results panel replaces them with spaces so each row stays on one line. The full, unmodified value is still written when you export results to CSV.

## Export Menu

`@e` (available from any panel's command mode) opens a one-key submenu:

| Key | Action |
|-----|--------|
| `r` | Export results to `results_YYYYMMDD_HHMMSS.csv` |
| `s` | Save current SQL to `query_YYYYMMDD_HHMMSS.sql` |
| any other key | Cancel |

Both files are saved in the same directory as the open database. The filename is confirmed in the Results panel header.

## Copy SQL

`@y` attempts to copy the current editor contents to the system clipboard using the following fallback chain:

1. **OSC 52** — a terminal escape sequence supported by most modern terminal emulators and web terminals, including over SSH. No extra tools needed.
2. **`xclip` / `xsel`** — standard Linux clipboard tools, used if OSC 52 is not supported.
3. **`.sql` file** — if neither clipboard method works, the SQL is saved as `query_YYYYMMDD_HHMMSS.sql` next to the database.

The result is confirmed in the editor header and clears on the next keystroke. If clipboard access is unavailable in your environment, use `@e s` instead to save the SQL directly to a file.

## SQL Buffers

`@t` (available from any panel's command mode) enters buffer mode. The help bar shows available commands:

| Key | Action |
|-----|--------|
| `n` | New buffer (up to 4) |
| `d` | Delete current buffer (clears if only one remains) |
| `1`–`4` | Switch to that buffer |
| any other key | Cancel |

Each buffer has its own SQL text, cursor position, and scroll state. Results are shared — switching buffers does not change what's displayed in the results panel. The editor header shows `[2/3]` (current/total) when more than one buffer is open.

## File Structure

```
sqlite_curses.py   — main application
file_browser.py    — modal file/directory picker
```
