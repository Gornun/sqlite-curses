import base64
import csv
import curses
import sqlite3
import os
import re
import subprocess
import sys
from datetime import datetime
from file_browser import FileBrowser


class SQLiteCursesApp:
    def __init__(self, db_path):
        self.db_path = os.path.abspath(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._set_db_pragmas()
        self.tables = []
        self.views = []
        self.triggers = []   # list of {'name', 'table', 'event'}
        self.selected_table = None
        self.sql_lines = [""]
        self.current_line = 0
        self.cursor_position = 0
        self.query_results = []
        self.query_col_names = []   # column headers from last SELECT
        self.editor_scroll = 0      # vertical scroll offset for SQL editor
        self.result_scroll = 0      # vertical scroll offset for results
        self.result_col_scroll = 0  # horizontal scroll offset for results
        self.results_visible_rows = 0  # updated each draw, used by input handler
        self.export_status = ""        # shown in results header after export
        self.copy_status = ""          # shown in editor header after copy/save
        self.sql_buffers = [{"lines": [""], "line": 0, "pos": 0, "scroll": 0}]
        self.current_buffer = 0
        self.tab_mode = False          # waiting for tab subcommand after @t
        self.export_mode = False       # waiting for export subcommand after @e
        self.divider_x = 0             # left panel width offset from default (width//3)
        self.divider_y = 0             # editor height offset from default (height//2-2)
        self.current_panel = "right"   # "left", "right", "results"
        self.command_mode = False
        self.in_quote = None    # '"' or "'" when cursor is inside a quoted string
        self.left_scroll = 0      # vertical scroll offset for left panel
        self.left_col_scroll = 0  # horizontal scroll offset for left panel
        self.left_cursor = 0     # cursor index into flat left-panel item list
        self.expanded_tables = set()  # tables with columns currently visible

    def _set_db_pragmas(self):
        try:
            self.conn.execute("PRAGMA journal_mode=WAL;")
        except sqlite3.Error:
            pass
        try:
            self.conn.execute("PRAGMA synchronous=NORMAL;")
        except sqlite3.Error:
            pass

    def load_objects(self):
        self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        self.tables = [row[0] for row in self.cursor.fetchall()]

        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='view';")
        self.views = [row[0] for row in self.cursor.fetchall()]

        self.cursor.execute(
            "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger';")
        self.triggers = []
        for name, tbl_name, sql in self.cursor.fetchall():
            event = 'UNKNOWN'
            if sql:
                m = re.search(
                    r'(BEFORE|AFTER|INSTEAD\s+OF)\s+(INSERT|UPDATE|DELETE)',
                    sql, re.IGNORECASE)
                if m:
                    event = f"{m.group(1).upper()} {m.group(2).upper()}"
            self.triggers.append({'name': name, 'table': tbl_name, 'event': event})

    def get_table_columns(self, table_name):
        self.cursor.execute(f"PRAGMA table_info([{table_name}]);")
        cols = self.cursor.fetchall()  # (cid, name, type, notnull, dflt, pk)

        # Find explicitly indexed columns (skip 'pk' origin — covered by [PK] tag)
        self.cursor.execute(f"PRAGMA index_list([{table_name}]);")
        indexed = set()
        for idx in self.cursor.fetchall():  # (seq, name, unique, origin, partial)
            if idx[3] != 'pk':
                self.cursor.execute(f"PRAGMA index_info([{idx[1]}]);")
                for info in self.cursor.fetchall():
                    indexed.add(info[2])  # column name

        return [(row[1], row[2], bool(row[5]), row[1] in indexed)
                for row in cols]  # (name, type, is_pk, is_indexed)

    def execute_query(self):
        try:
            sql_query = '\n'.join(self.sql_lines).strip()
            if not sql_query:
                return
            self.cursor.execute(sql_query)
            first_word = sql_query.upper().split()[0]
            write_ops = ('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP',
                         'ALTER', 'ATTACH', 'DETACH', 'REPLACE')
            if first_word in write_ops:
                self.conn.commit()
                self.query_results = [f"OK ({self.cursor.rowcount} row(s) affected)"]
                self.query_col_names = []
                if first_word in ('CREATE', 'DROP', 'ALTER'):
                    self.load_objects()
                    if self.tables and self.selected_table not in self.tables:
                        self.selected_table = self.tables[0]
            else:
                self.query_col_names = ([desc[0] for desc in self.cursor.description]
                                        if self.cursor.description else [])
                rows = self.cursor.fetchall()
                self.query_results = rows if rows else ["(no results)"]
        except Exception as e:
            try:
                self.conn.rollback()
            except Exception:
                pass
            self.query_results = [f"Error: {str(e)}"]
            self.query_col_names = []
        # Reset scroll and export status whenever query runs
        self.result_scroll = 0
        self.result_col_scroll = 0
        self.export_status = ""

    def export_to_csv(self):
        if not self.query_results:
            self.export_status = "no results"
            return
        if not isinstance(self.query_results[0], (tuple, list)):
            self.export_status = "no tabular results to export"
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(os.path.dirname(self.db_path),
                                f"results_{timestamp}.csv")
        try:
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                if self.query_col_names:
                    writer.writerow(self.query_col_names)
                writer.writerows(self.query_results)
            self.export_status = f"saved: {os.path.basename(filename)}"
        except Exception as e:
            self.export_status = f"error: {e}"

    def save_sql_to_file(self):
        text = '\n'.join(self.sql_lines).strip()
        if not text:
            self.export_status = "editor is empty"
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(os.path.dirname(self.db_path),
                                f"query_{timestamp}.sql")
        try:
            with open(filename, 'w') as f:
                f.write(text)
            self.export_status = f"saved: {os.path.basename(filename)}"
        except Exception as e:
            self.export_status = f"error: {e}"

    def _handle_export_mode(self, key):
        self.export_mode = False
        if key == ord('r'):
            self.export_to_csv()
        elif key == ord('s'):
            self.save_sql_to_file()
        # any other key: cancel

    def copy_sql(self):
        text = '\n'.join(self.sql_lines).strip()
        if not text:
            self.copy_status = "editor is empty"
            return

        # Try OSC 52 — terminal-native clipboard, works in most web terminals
        try:
            encoded = base64.b64encode(text.encode()).decode()
            osc52 = f"\033]52;c;{encoded}\007"
            fd = os.open('/dev/tty', os.O_WRONLY)
            os.write(fd, osc52.encode())
            os.close(fd)
            self.copy_status = "copied to clipboard"
            return
        except Exception:
            pass

        # Try xclip / xsel (Linux X11)
        for cmd in (['xclip', '-selection', 'clipboard'],
                    ['xsel', '--clipboard', '--input']):
            try:
                proc = subprocess.run(cmd, input=text.encode(), timeout=2)
                if proc.returncode == 0:
                    self.copy_status = f"copied ({cmd[0]})"
                    return
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        # Fallback: save to a .sql file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(os.path.dirname(self.db_path),
                                f"query_{timestamp}.sql")
        try:
            with open(filename, 'w') as f:
                f.write(text)
            self.copy_status = f"saved: {os.path.basename(filename)}"
        except Exception as e:
            self.copy_status = f"error: {e}"

    def _save_buffer(self):
        self.sql_buffers[self.current_buffer] = {
            "lines": list(self.sql_lines),
            "line": self.current_line,
            "pos": self.cursor_position,
            "scroll": self.editor_scroll,
        }

    def _restore_buffer(self, n):
        """Load buffer n into live state (does NOT save current first)."""
        self.current_buffer = n
        b = self.sql_buffers[n]
        self.sql_lines = list(b["lines"])
        self.current_line = b["line"]
        self.cursor_position = b["pos"]
        self.editor_scroll = b["scroll"]
        self.copy_status = ""

    def _switch_buffer(self, n):
        self._save_buffer()
        self._restore_buffer(n)

    def _handle_tab_mode(self, key):
        self.tab_mode = False
        if key == ord('n'):
            if len(self.sql_buffers) < 4:
                self._save_buffer()
                self.sql_buffers.append({"lines": [""], "line": 0, "pos": 0, "scroll": 0})
                self._restore_buffer(len(self.sql_buffers) - 1)
            else:
                self.copy_status = "max 4 buffers"
        elif key == ord('d'):
            if len(self.sql_buffers) > 1:
                self.sql_buffers.pop(self.current_buffer)
                self._restore_buffer(min(self.current_buffer, len(self.sql_buffers) - 1))
            else:
                # Only one buffer — just clear it
                self.sql_lines = [""]
                self.current_line = 0
                self.cursor_position = 0
                self.editor_scroll = 0
                self.copy_status = ""
        elif ord('1') <= key <= ord('4'):
            n = key - ord('1')
            if n < len(self.sql_buffers):
                self._switch_buffer(n)
        # any other key: cancel (tab_mode already cleared)

    def load_new_database(self, db_path):
        try:
            self.conn.close()
            self.db_path = os.path.abspath(db_path)
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.cursor = self.conn.cursor()
            self._set_db_pragmas()
            self.load_objects()
            self.selected_table = self.tables[0] if self.tables else None
            self.query_results = [f"Loaded: {self.db_path}"]
            self.query_col_names = []
            self.result_scroll = 0
            self.result_col_scroll = 0
        except Exception as e:
            self.query_results = [f"Error loading database: {str(e)}"]

    # --- Drawing ---

    def _get_left_items(self):
        """Build flat list of (kind, name, label) for the left panel."""
        items = []

        def col_items(obj_name):
            try:
                for name, col_type, is_pk, is_indexed in self.get_table_columns(obj_name):
                    tags = []
                    if is_pk:
                        tags.append('[PK]')
                    if is_indexed:
                        tags.append('[I]')
                    tag_str = '  ' + ' '.join(tags) if tags else ''
                    label = f"{name}{'  ' + col_type if col_type else ''}{tag_str}"
                    items.append(('col', obj_name, label))
            except Exception as e:
                items.append(('col', obj_name, f'Err: {e}'))

        if self.tables:
            items.append(('section', '', 'TABLES'))
            for table in self.tables:
                items.append(('table', table, table))
                if table in self.expanded_tables:
                    col_items(table)

        if self.views:
            items.append(('section', '', 'VIEWS'))
            for view in self.views:
                items.append(('view', view, view))
                if view in self.expanded_tables:
                    col_items(view)

        if self.triggers:
            items.append(('section', '', 'TRIGGERS'))
            for trig in self.triggers:
                items.append(('trigger', trig['name'], trig['name']))
                if trig['name'] in self.expanded_tables:
                    items.append(('triginfo', trig['name'], f"on:  {trig['table']}"))
                    items.append(('triginfo', trig['name'], f"evt: {trig['event']}"))

        return items

    def _draw_left_panel(self, stdscr, height, left_width):
        try:
            stdscr.addstr(0, 0, "Tables", curses.A_BOLD)
        except curses.error:
            pass

        items = self._get_left_items()
        n = len(items)

        # Clamp cursor and scroll
        if n:
            self.left_cursor = max(0, min(self.left_cursor, n - 1))
        visible = height - 3   # rows between header and help bar
        self.left_scroll = max(0, min(self.left_scroll,
                                      max(0, n - visible)))
        # Keep cursor in view
        if self.left_cursor < self.left_scroll:
            self.left_scroll = self.left_cursor
        elif self.left_cursor >= self.left_scroll + visible:
            self.left_scroll = self.left_cursor - visible + 1

        for i, (kind, obj_name, label) in enumerate(items[self.left_scroll:]):
            screen_row = 1 + i
            if screen_row >= height - 2:
                break
            idx = self.left_scroll + i
            is_cursor = (idx == self.left_cursor) and (self.current_panel == "left")

            try:
                if kind == 'section':
                    full = label
                    text = full[self.left_col_scroll:self.left_col_scroll + left_width]
                    stdscr.addstr(screen_row, 0, text, curses.A_BOLD)
                elif kind in ('table', 'view', 'trigger'):
                    prefix = "- " if obj_name in self.expanded_tables else "+ "
                    full = prefix + label
                    text = full[self.left_col_scroll:self.left_col_scroll + left_width]
                    stdscr.addstr(screen_row, 0, text,
                                  curses.A_REVERSE if is_cursor else 0)
                else:  # col / triginfo
                    full = "  " + label
                    text = full[self.left_col_scroll:self.left_col_scroll + left_width]
                    stdscr.addstr(screen_row, 0, text,
                                  curses.A_REVERSE if is_cursor else 0)
            except curses.error:
                pass

    def _draw_right_panel(self, stdscr, height, width, left_width):
        right_width = width - left_width - 1
        sql_input_height = max(3, min(height - 8, height // 2 - 2 + self.divider_y))
        col0 = left_width + 1
        # Reserve 1 col on the far right for the scrollbar
        text_width = right_width - 2
        sb_col = width - 2   # scrollbar column

        # --- SQL editor (top half) ---
        if self.command_mode and self.current_panel == "right":
            mode_text = " [CMD]"
        elif self.current_panel == "right" and self.in_quote:
            mode_text = f" [IN {self.in_quote}]"
        else:
            mode_text = ""
        copy_text = f"  [{self.copy_status}]" if self.copy_status else ""
        n_buf = len(self.sql_buffers)
        buf_text = f" [{self.current_buffer + 1}/{n_buf}]" if n_buf > 1 else ""
        try:
            stdscr.addstr(0, col0, f"SQL Editor{mode_text}{buf_text}{copy_text}"[:right_width], curses.A_BOLD)
            stdscr.addstr(1, left_width, "_" * min(right_width, width - left_width - 1))
        except curses.error:
            pass

        wrap_width = max(1, right_width - 2)  # 2 for "> " prefix
        editor_bot = sql_input_height + 2     # exclusive row boundary for editor
        visible_editor_rows = editor_bot - 2  # number of display rows for SQL lines

        # Clamp editor_scroll
        self.editor_scroll = max(0, min(self.editor_scroll, len(self.sql_lines) - 1))

        # Scroll up: ensure cursor line is not above the viewport
        if self.current_line < self.editor_scroll:
            self.editor_scroll = self.current_line

        # Scroll down: count visual rows from editor_scroll to current_line;
        # advance editor_scroll if cursor would fall off the bottom
        rows_to_cursor = 0
        for i in range(self.editor_scroll, self.current_line + 1):
            line_i = self.sql_lines[i]
            rows_to_cursor += max(1, -(-len(line_i) // wrap_width))
        while rows_to_cursor > visible_editor_rows and self.editor_scroll < self.current_line:
            line_i = self.sql_lines[self.editor_scroll]
            rows_to_cursor -= max(1, -(-len(line_i) // wrap_width))
            self.editor_scroll += 1

        start_row = 2
        for i in range(self.editor_scroll, len(self.sql_lines)):
            line = self.sql_lines[i]
            if start_row >= editor_bot:
                break
            is_current = (i == self.current_line and self.current_panel == "right")
            chunks = [line[j:j + wrap_width] for j in range(0, len(line), wrap_width)] or ['']
            for chunk_idx, chunk in enumerate(chunks):
                if start_row >= editor_bot:
                    break
                prefix = "> " if (is_current and chunk_idx == 0) else "  "
                if is_current:
                    chunk_start = chunk_idx * wrap_width
                    if chunk_start <= self.cursor_position <= chunk_start + len(chunk):
                        lp = self.cursor_position - chunk_start
                        display = chunk[:lp] + "|" + chunk[lp:]
                    else:
                        display = chunk
                    attr = curses.A_BOLD
                else:
                    display = chunk
                    attr = 0
                try:
                    stdscr.addstr(start_row, col0, (prefix + display)[:right_width], attr)
                except curses.error:
                    pass
                start_row += 1

        # --- Results (bottom half) ---
        results_focused = self.current_panel == "results"
        results_label_attr = curses.A_REVERSE if results_focused else curses.A_BOLD
        total = len(self.query_results)
        count_text = f" ({total})" if total else ""
        export_text = f"  [{self.export_status}]" if self.export_status else ""
        try:
            stdscr.addstr(sql_input_height + 2, col0,
                          f"Results{count_text}{export_text}:"[:right_width],
                          results_label_attr)
            stdscr.addstr(sql_input_height + 3, left_width,
                          "_" * min(right_width, width - left_width - 1))
        except curses.error:
            pass

        # Column headers row (pinned)
        data_start_row = sql_input_height + 4
        if self.query_col_names:
            header_str = " | ".join(str(c) for c in self.query_col_names)
            header_display = header_str[self.result_col_scroll:
                                        self.result_col_scroll + text_width]
            try:
                stdscr.addstr(data_start_row, col0, header_display, curses.A_BOLD)
            except curses.error:
                pass
            data_start_row += 1

        # Visible data rows
        last_row = height - 2   # row height-1 is the help bar
        visible = max(0, last_row - data_start_row)
        self.results_visible_rows = visible  # share with input handler

        for i in range(visible):
            idx = self.result_scroll + i
            if idx >= total:
                break
            row_data = self.query_results[idx]
            if isinstance(row_data, (tuple, list)):
                row_str = " | ".join(str(v) for v in row_data)
            else:
                row_str = str(row_data)
            row_display = row_str[self.result_col_scroll:
                                  self.result_col_scroll + text_width]
            screen_row = data_start_row + i
            if screen_row >= last_row:
                break
            try:
                stdscr.addstr(screen_row, col0, row_display)
            except curses.error:
                pass

        # --- Vertical scrollbar ---
        sb_top = data_start_row
        sb_height = last_row - sb_top
        if sb_height > 0 and total > visible and visible > 0:
            max_scroll = total - visible
            thumb_size = max(1, sb_height * visible // total)
            if max_scroll > 0:
                thumb_pos = int(self.result_scroll / max_scroll * (sb_height - thumb_size))
            else:
                thumb_pos = 0
            for i in range(sb_height):
                screen_row = sb_top + i
                if screen_row >= last_row:
                    break
                ch = "\u2588" if thumb_pos <= i < thumb_pos + thumb_size else "\u2502"
                try:
                    stdscr.addstr(screen_row, sb_col, ch)
                except curses.error:
                    pass

    def _draw_help(self, stdscr, height, width):
        if self.export_mode:
            help_text = "EXPORT: r=Results(CSV)  s=SQL(.sql file)  (other key=cancel)"
        elif self.tab_mode:
            help_text = "TAB: n=New  d=Del  1-4=Switch  (other key=cancel)"
        elif self.current_panel == "results":
            if self.command_mode:
                help_text = "CMD: q=Quit f=Files e=Export y=Copy t=Tabs  (@=ExitCMD) | 5/6/4/7: Scroll"
            else:
                help_text = "Tab/$: SwitchPanel | @: CommandMode | 5↑6↓: Scroll | 4←7→: H-Scroll"
        elif self.current_panel == "right":
            if self.command_mode:
                help_text = "CMD: Enter=Run c=Clr e=Exp y=Copy t=Tabs f=Files 56=↕ 47=↔ q=Quit (@=Exit)"
            else:
                help_text = "Tab/$: SwitchPanel | @: CommandMode | Enter: NewLine | ←→↑↓: Move"
        else:  # left
            if self.command_mode:
                help_text = "CMD: 56=Nav f=Files e=Export y=Copy t=Tabs q=Quit  (@=ExitCMD)"
            else:
                help_text = "Tab/$: SwitchPanel | @: CommandMode | 56: Navigate | 47: H-Scroll | Space: Expand"
        try:
            stdscr.addstr(height - 1, 0, help_text[:width - 1])
        except curses.error:
            pass

    # --- Quote state ---

    def _recalc_in_quote(self):
        """Scan SQL text up to the cursor and determine if we're inside a quoted string."""
        in_q = None
        for line_idx, line in enumerate(self.sql_lines):
            if line_idx < self.current_line:
                text = line
            elif line_idx == self.current_line:
                text = line[:self.cursor_position]
            else:
                break
            for ch in text:
                if in_q is None:
                    if ch in ('"', "'"):
                        in_q = ch
                elif ch == in_q:
                    in_q = None
        self.in_quote = in_q

    # --- Input handling ---

    def _handle_results_panel_input(self, key):
        if key == ord('@'):
            self.command_mode = not self.command_mode
            return
        # @q and @f work from command mode
        if self.command_mode:
            if key == ord('q'):
                return "quit"
            elif key == ord('f'):
                self.command_mode = False
                return "open_browser"
            elif key == ord('e'):
                self.export_mode = True
                self.command_mode = False
            elif key == ord('y'):
                self.copy_sql()
                self.command_mode = False
            elif key == ord('t'):
                self.tab_mode = True
                self.command_mode = False
        # Navigation always active (results is read-only)
        total = len(self.query_results)
        max_v = max(0, total - self.results_visible_rows)
        if key in (ord('5'), curses.KEY_UP):
            if self.result_scroll > 0:
                self.result_scroll -= 1
        elif key in (ord('6'), curses.KEY_DOWN):
            if self.result_scroll < max_v:
                self.result_scroll += 1
        elif key in (ord('4'), curses.KEY_LEFT):
            if self.result_col_scroll > 0:
                self.result_col_scroll -= 1
        elif key in (ord('7'), curses.KEY_RIGHT):
            self.result_col_scroll += 1
        elif key in (9, ord('$')):  # Tab or $ — cycle to left panel
            self.current_panel = "left"
            self.command_mode = False

    def _handle_right_panel_input(self, key):
        self._recalc_in_quote()
        if key == ord('@'):
            if self.in_quote:
                line = self.sql_lines[self.current_line]
                self.sql_lines[self.current_line] = (line[:self.cursor_position]
                                                     + '@'
                                                     + line[self.cursor_position:])
                self.cursor_position += 1
            else:
                self.command_mode = not self.command_mode
            return
        if self.command_mode:
            if key == ord('f'):
                self.command_mode = False
                return "open_browser"
            elif key == ord('e'):
                self.export_mode = True
                self.command_mode = False
            elif key == ord('y'):
                self.copy_sql()
                self.command_mode = False
            elif key == ord('t'):
                self.tab_mode = True
                self.command_mode = False
            elif key == 10:  # Execute
                self.execute_query()
                self.command_mode = False
            elif key == ord('q'):
                return "quit"
            elif key == ord('c'):
                self.sql_lines = [""]
                self.current_line = 0
                self.cursor_position = 0
                self.editor_scroll = 0
                self.command_mode = False
            elif key in (ord('5'), curses.KEY_UP):
                if self.current_line > 0:
                    self.current_line -= 1
                    self.cursor_position = min(self.cursor_position,
                                               len(self.sql_lines[self.current_line]))
            elif key in (ord('6'), curses.KEY_DOWN):
                if self.current_line < len(self.sql_lines) - 1:
                    self.current_line += 1
                    self.cursor_position = min(self.cursor_position,
                                               len(self.sql_lines[self.current_line]))
            elif key == ord('4'):
                if self.cursor_position > 0:
                    self.cursor_position -= 1
            elif key == ord('7'):
                if self.cursor_position < len(self.sql_lines[self.current_line]):
                    self.cursor_position += 1
        else:
            if key == 9 or (key == ord('$') and not self.in_quote):  # Tab or $ — cycle to results panel
                self.current_panel = "results"
            elif key == 10:  # Enter — split line at cursor
                current = self.sql_lines[self.current_line]
                self.sql_lines[self.current_line] = current[:self.cursor_position]
                self.sql_lines.insert(self.current_line + 1, current[self.cursor_position:])
                self.current_line += 1
                self.cursor_position = 0
            elif key == curses.KEY_UP:
                if self.current_line > 0:
                    self.current_line -= 1
                    self.cursor_position = min(self.cursor_position,
                                               len(self.sql_lines[self.current_line]))
            elif key == curses.KEY_DOWN:
                if self.current_line < len(self.sql_lines) - 1:
                    self.current_line += 1
                    self.cursor_position = min(self.cursor_position,
                                               len(self.sql_lines[self.current_line]))
            elif key == curses.KEY_LEFT:
                if self.cursor_position > 0:
                    self.cursor_position -= 1
                elif self.current_line > 0:
                    self.current_line -= 1
                    self.cursor_position = len(self.sql_lines[self.current_line])
            elif key == curses.KEY_RIGHT:
                if self.cursor_position < len(self.sql_lines[self.current_line]):
                    self.cursor_position += 1
                elif self.current_line < len(self.sql_lines) - 1:
                    self.current_line += 1
                    self.cursor_position = 0
            elif key in (curses.KEY_BACKSPACE, 127):
                if self.cursor_position > 0:
                    line = self.sql_lines[self.current_line]
                    self.sql_lines[self.current_line] = (line[:self.cursor_position - 1]
                                                         + line[self.cursor_position:])
                    self.cursor_position -= 1
                elif self.current_line > 0:
                    prev = self.sql_lines[self.current_line - 1]
                    curr = self.sql_lines.pop(self.current_line)
                    self.current_line -= 1
                    self.cursor_position = len(prev)
                    self.sql_lines[self.current_line] = prev + curr
            elif key == curses.KEY_DC:  # Delete — forward delete
                line = self.sql_lines[self.current_line]
                if self.cursor_position < len(line):
                    self.sql_lines[self.current_line] = (line[:self.cursor_position]
                                                         + line[self.cursor_position + 1:])
                elif self.current_line < len(self.sql_lines) - 1:
                    curr = self.sql_lines.pop(self.current_line + 1)
                    self.sql_lines[self.current_line] = line + curr
            elif 32 <= key <= 126:
                line = self.sql_lines[self.current_line]
                self.sql_lines[self.current_line] = (line[:self.cursor_position]
                                                     + chr(key)
                                                     + line[self.cursor_position:])
                self.cursor_position += 1
                self.copy_status = ""

    def _handle_left_panel_input(self, key):
        if key == ord('@'):
            self.command_mode = not self.command_mode
            return
        if self.command_mode:
            if key == ord('q'):
                return "quit"
            elif key == ord('f'):
                self.command_mode = False
                return "open_browser"
            elif key == ord('e'):
                self.export_mode = True
                self.command_mode = False
            elif key == ord('y'):
                self.copy_sql()
                self.command_mode = False
            elif key == ord('t'):
                self.tab_mode = True
                self.command_mode = False
        # Tab / $ — cycle to SQL editor (works in both modes)
        if key in (9, ord('$')):
            self.current_panel = "right"
            self.command_mode = False
            return
        # Up/down navigation (works in both modes)
        if key in (ord('5'), curses.KEY_UP, ord('6'), curses.KEY_DOWN):
            items = self._get_left_items()
            if not items:
                return
            delta = -1 if key in (ord('5'), curses.KEY_UP) else 1
            new_cursor = max(0, min(len(items) - 1, self.left_cursor + delta))
            # Skip over section headers
            while 0 < new_cursor < len(items) - 1 and items[new_cursor][0] == 'section':
                new_cursor += delta
            self.left_cursor = new_cursor
            kind, obj_name, _ = items[self.left_cursor]
            if kind in ('table', 'view'):
                self.selected_table = obj_name
        # Left/right horizontal scroll (works in both modes)
        elif key in (ord('4'), curses.KEY_LEFT):
            if self.left_col_scroll > 0:
                self.left_col_scroll -= 1
        elif key in (ord('7'), curses.KEY_RIGHT):
            self.left_col_scroll += 1
        # Space — toggle expand/collapse on any expandable item
        elif key == ord(' '):
            items = self._get_left_items()
            if not items:
                return
            self.left_cursor = max(0, min(len(items) - 1, self.left_cursor))
            kind, obj_name, _ = items[self.left_cursor]
            if kind in ('table', 'view', 'trigger'):
                if obj_name in self.expanded_tables:
                    self.expanded_tables.discard(obj_name)
                else:
                    self.expanded_tables.add(obj_name)
                # Reposition cursor to the same object header after rebuild
                items = self._get_left_items()
                for i, item in enumerate(items):
                    if item[0] == kind and item[1] == obj_name:
                        self.left_cursor = i
                        break

    # --- Main loop ---

    def run(self, stdscr):
        curses.curs_set(0)
        self.load_objects()
        if self.tables:
            self.selected_table = self.tables[0]
        # Start cursor on first real item (skip section header)
        self.left_cursor = 1 if self.tables or self.views or self.triggers else 0

        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            left_width = max(8, min(width - 8, width // 3 + self.divider_x))

            stdscr.vline(0, left_width, curses.ACS_VLINE, height)
            self._draw_left_panel(stdscr, height, left_width)
            self._draw_right_panel(stdscr, height, width, left_width)
            self._draw_help(stdscr, height, width)
            stdscr.refresh()

            key = stdscr.getch()
            result = None

            if key == curses.KEY_SRIGHT:
                self.divider_x += 1
            elif key == curses.KEY_SLEFT:
                self.divider_x -= 1
            elif key == curses.KEY_SF:    # Shift+Down
                self.divider_y += 1
            elif key == curses.KEY_SR:    # Shift+Up
                self.divider_y -= 1
            elif self.export_mode:
                self._handle_export_mode(key)
            elif self.tab_mode:
                self._handle_tab_mode(key)
            elif self.current_panel == "results":
                result = self._handle_results_panel_input(key)
            elif self.current_panel == "right":
                result = self._handle_right_panel_input(key)
            else:
                result = self._handle_left_panel_input(key)

            if result == "quit":
                self.conn.close()
                return
            elif result == "open_browser":
                browser = FileBrowser(start_path=os.path.dirname(self.db_path))
                chosen = browser.run(stdscr)
                if chosen:
                    self.load_new_database(chosen)


if __name__ == "__main__":
    args = sys.argv[1:]
    create_new = False

    if args and args[0] in ('-c', '--create'):
        create_new = True
        args = args[1:]

    if not args:
        print("Usage: python sqlite_curses.py [-c|--create] <database.db>")
        print("  -c, --create   Create a new database (required if file does not exist)")
        sys.exit(1)

    db_path = args[0]
    if not create_new and not os.path.exists(db_path):
        print(f"Error: '{db_path}' not found.")
        print(f"To create it, run: python sqlite_curses.py --create {db_path}")
        sys.exit(1)

    app = SQLiteCursesApp(db_path)
    curses.wrapper(app.run)
