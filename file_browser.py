#!/usr/bin/env python3
"""
A curses-based directory browser/file chooser component.

This module provides a reusable file browser that can be integrated into other
curses applications. The browser allows users to navigate directories, view files,
and select a file to return its path to the calling program.

Features:
- Left pane: Directory tree navigation (arrow keys)
- Right pane: File list with name, creation date, and modification date
- Tab key to switch between panes
- Enter key to select file or enter directory
- Escape key to cancel
"""

import curses
import os
import sqlite3
import time
from datetime import datetime


class FileBrowser:
    """A curses-based file browser component."""
    
    def __init__(self, start_path=None):
        """
        Initialize the file browser.
        
        Args:
            start_path: Starting directory path (default: current directory)
        """
        self.start_path = start_path or os.getcwd()
        self.current_path = self.start_path
        self.directory_stack = [self.start_path]
        
        # Current selection
        self.current_dir_index = 0
        self.current_file_index = 0
        
        # Scroll offsets for long lists
        self.dir_scroll_offset = 0
        self.file_scroll_offset = 0
        
        self.active_pane = "left"  # 'left' or 'right'

        # New database prompt state
        self.new_db_mode = False
        self.new_db_name = ""
        self.new_db_error = ""

        # File info
        self.files = []
        self.directories = []
        
    def _init_curses(self):
        """Initialize curses settings."""
        try:
            curses.curs_set(0)  # Hide cursor
            self.stdscr.keypad(True)  # Enable keypad
            curses.start_color()
            
            # Color pairs
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)  # Header
            curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLACK)  # Selected item
            curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Directory
            curses.init_pair(4, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # File
        except Exception:
            # If curses initialization fails, we'll run in minimal mode
            pass
        
    def _get_file_info(self, path):
        """Get file information for display."""
        try:
            stat = os.stat(path)
            created = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M")
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            return created, modified
        except Exception:
            return "Unknown", "Unknown"
    
    def _refresh_directory_list(self):
        """Refresh the list of directories and files in current path."""
        try:
            items = os.listdir(self.current_path)
            self.directories = []
            self.files = []
            
            # Add ".." for navigating up (unless we're at filesystem root)
            if self.current_path != "/":
                self.directories.append("..")
            
            for item in sorted(items):
                full_path = os.path.join(self.current_path, item)
                if os.path.isdir(full_path):
                    self.directories.append(item)
                else:
                    created, modified = self._get_file_info(full_path)
                    self.files.append({
                        'name': item,
                        'created': created,
                        'modified': modified,
                        'path': full_path
                    })
        except Exception:
            self.directories = [".."] if self.current_path != "/" else []
            self.files = []
    
    def _draw_header(self):
        """Draw the header section."""
        try:
            header = f" File Browser - {self.current_path} "
            self.stdscr.addstr(0, 0, header[:self.width-1], curses.color_pair(1))
        except curses.error:
            pass
    
    def _draw_left_pane(self):
        """Draw the directory tree pane."""
        try:
            # Draw border
            for i in range(1, self.height-1):
                try:
                    self.stdscr.addch(i, self.left_width, curses.ACS_VLINE)
                except curses.error:
                    pass
            
            # Draw directory list
            for i in range(self.height - 2):
                if self.dir_scroll_offset + i >= len(self.directories):
                    break
                
                directory = self.directories[self.dir_scroll_offset + i]
                color = curses.color_pair(4)
                if (self.dir_scroll_offset + i) == self.current_dir_index and self.active_pane == "left":
                    color = curses.color_pair(2)
                
                try:
                    self.stdscr.addstr(i+1, 1, f"  {directory}", color)
                except curses.error:
                    pass
        except Exception:
            pass
    
    def _draw_right_pane(self):
        """Draw the file list pane."""
        try:
            # Draw file list with headers
            headers = "Name" + " " * (self.right_width//4) + "Created" + " " * 10 + "Modified"
            try:
                self.stdscr.addstr(1, self.left_width + 2, headers[:self.right_width-3], curses.A_BOLD)
            except curses.error:
                pass
            
            # Draw files
            for i in range(self.height - 4):
                if self.file_scroll_offset + i >= len(self.files):
                    break
                
                file_info = self.files[self.file_scroll_offset + i]
                color = curses.color_pair(4)
                if (self.file_scroll_offset + i) == self.current_file_index and self.active_pane == "right":
                    color = curses.color_pair(2)
                
                line = f"{file_info['name']:<20} {file_info['created']:<16} {file_info['modified']}"
                try:
                    self.stdscr.addstr(i+2, self.left_width + 2, line[:self.right_width-3], color)
                except curses.error:
                    pass
        except Exception:
            pass
    
    def _draw_status(self):
        """Draw the status bar."""
        try:
            status = "↑↓/56: Navigate | Tab/$: Switch pane | Enter: Select | Bksp: Up | n: New DB | q: Quit"
            self.stdscr.addstr(self.height-1, 0, status[:self.width-1], curses.A_REVERSE)
        except curses.error:
            pass

    def _draw_new_db_prompt(self):
        """Draw the new database name prompt."""
        try:
            prompt = f" New DB: {self.new_db_name}_"
            if self.new_db_error:
                prompt += f"  ({self.new_db_error})"
            self.stdscr.addstr(self.height-1, 0, prompt[:self.width-1], curses.A_REVERSE)
        except curses.error:
            pass
    
    def _handle_input(self):
        """Handle user input."""
        while True:
            key = self.stdscr.getch()

            # --- New DB prompt mode ---
            if self.new_db_mode:
                if key in (curses.KEY_BACKSPACE, 127):
                    self.new_db_name = self.new_db_name[:-1]
                    self.new_db_error = ""
                elif key in (27, ord('q')):   # Escape or q — cancel
                    self.new_db_mode = False
                    self.new_db_name = ""
                    self.new_db_error = ""
                elif key in (10, 13):          # Enter — create
                    name = self.new_db_name.strip()
                    if name:
                        if not any(name.endswith(e) for e in ('.db', '.sqlite', '.sqlite3')):
                            name += '.db'
                        path = os.path.join(self.current_path, name)
                        try:
                            conn = sqlite3.connect(path)
                            conn.close()
                            return path
                        except Exception as e:
                            self.new_db_error = str(e)
                elif 32 <= key <= 126:
                    self.new_db_name += chr(key)
                # Redraw with prompt and continue
                self.stdscr.clear()
                self._draw_header()
                self._draw_left_pane()
                self._draw_right_pane()
                self._draw_new_db_prompt()
                self.stdscr.refresh()
                continue
            
            if key == curses.KEY_UP or key == ord('5'):
                if self.active_pane == "left" and self.current_dir_index > 0:
                    self.current_dir_index -= 1
                    # Scroll up if needed
                    if self.current_dir_index < self.dir_scroll_offset:
                        self.dir_scroll_offset = self.current_dir_index
                elif self.active_pane == "right" and self.current_file_index > 0:
                    self.current_file_index -= 1
                    # Scroll up if needed
                    if self.current_file_index < self.file_scroll_offset:
                        self.file_scroll_offset = self.current_file_index
            
            elif key == curses.KEY_DOWN or key == ord('6'):
                if self.active_pane == "left":
                    # Scroll down if we're at the bottom of visible area
                    if self.current_dir_index - self.dir_scroll_offset >= self.height - 3 and self.current_dir_index < len(self.directories) - 1:
                        self.dir_scroll_offset += 1
                    if self.current_dir_index < len(self.directories) - 1:
                        self.current_dir_index += 1
                elif self.active_pane == "right":
                    # Scroll down if we're at the bottom of visible area
                    if self.current_file_index - self.file_scroll_offset >= self.height - 5 and self.current_file_index < len(self.files) - 1:
                        self.file_scroll_offset += 1
                    if self.current_file_index < len(self.files) - 1:
                        self.current_file_index += 1
            
            elif key in (ord('\t'), ord('$')):
                # Tab or $ - switch panes
                self.active_pane = "right" if self.active_pane == "left" else "left"
                # Reset appropriate index and scroll offset when switching
                if self.active_pane == "left" and len(self.directories) > 0:
                    self.current_dir_index = min(self.current_dir_index, len(self.directories) - 1)
                    self.dir_scroll_offset = 0
                elif self.active_pane == "right" and len(self.files) > 0:
                    self.current_file_index = min(self.current_file_index, len(self.files) - 1)
                    self.file_scroll_offset = 0
            
            elif key == curses.KEY_BACKSPACE or key == 127 or key == 8:
                # Backspace - go up one directory (alternative to ..)
                if self.current_path != "/":
                    if len(self.directory_stack) > 1:
                        self.directory_stack.pop()  # Remove current directory
                    self.current_path = os.path.dirname(self.current_path)
                    self.current_dir_index = 0
                    self.current_file_index = 0
                    self.dir_scroll_offset = 0
                    self.file_scroll_offset = 0
                    self._refresh_directory_list()

            elif key == curses.KEY_ENTER or key in [10, 13]:
                # Enter key - select item
                if self.active_pane == "left":
                    if self.current_dir_index < len(self.directories):
                        selected_dir = self.directories[self.current_dir_index]
                        if selected_dir == "..":
                            # Navigate up
                            if self.current_path != "/":
                                if len(self.directory_stack) > 1:
                                    self.directory_stack.pop()  # Remove current directory
                                self.current_path = os.path.dirname(self.current_path)
                                self.current_dir_index = 0
                                self.current_file_index = 0
                                self.dir_scroll_offset = 0
                                self.file_scroll_offset = 0
                                self._refresh_directory_list()
                        else:
                            # Enter directory
                            new_path = os.path.join(self.current_path, selected_dir)
                            if os.path.isdir(new_path):
                                self.directory_stack.append(self.current_path)
                                self.current_path = new_path
                                self.current_dir_index = 0
                                self.current_file_index = 0
                                self.dir_scroll_offset = 0
                                self.file_scroll_offset = 0
                                self._refresh_directory_list()
                elif self.active_pane == "right" and self.current_file_index < len(self.files):
                    # Select file
                    return self.files[self.current_file_index]['path']
            
            elif key == ord('n'):  # New database
                self.new_db_mode = True
                self.new_db_name = ""
                self.new_db_error = ""
                self.stdscr.clear()
                self._draw_header()
                self._draw_left_pane()
                self._draw_right_pane()
                self._draw_new_db_prompt()
                self.stdscr.refresh()
                continue

            elif key == 27:  # Escape key to cancel/quit
                return None
            elif key in (ord('q'), ord('Q')):  # 'q' or 'Q' to cancel/quit
                return None

            # Redraw screen
            self.stdscr.clear()
            self._draw_header()
            self._draw_left_pane()
            self._draw_right_pane()
            self._draw_status()
            self.stdscr.refresh()
    
    def run(self, stdscr):
        """
        Run the file browser and return the selected file path.
        
        Args:
            stdscr: The curses standard screen object
            
        Returns:
            str: Selected file path, or None if cancelled
        """
        self.stdscr = stdscr
        
        # Initialize dimensions (requires stdscr)
        self.height, self.width = stdscr.getmaxyx()
        self.left_width = self.width // 4
        self.right_width = self.width - self.left_width - 1
        
        self._init_curses()
        
        # Initialize directory stack with current path
        self.directory_stack = [self.current_path]
        
        self._refresh_directory_list()
        
        self.stdscr.clear()
        self._draw_header()
        self._draw_left_pane()
        self._draw_right_pane()
        self._draw_status()
        self.stdscr.refresh()

        return self._handle_input()


def choose_file(start_path=None):
    """
    Main function to launch the file browser and get selected file.
    
    Args:
        start_path: Starting directory path (default: current directory)
    
    Returns:
        str: Selected file path, or None if cancelled
    """
    def wrapper_main(stdscr):
        browser = FileBrowser(start_path)
        return browser.run(stdscr)
    
    try:
        return curses.wrapper(wrapper_main)
    except curses.error as e:
        # Handle case where terminal doesn't support curses
        print(f"Error: Terminal doesn't support curses mode: {e}")
        print("This application requires a proper terminal environment.")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None


if __name__ == "__main__":
    # Example usage
    selected_file = choose_file()
    if selected_file:
        print(f"Selected file: {selected_file}")
    else:
        print("No file selected.")