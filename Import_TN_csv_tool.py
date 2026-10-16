"""Convert pasted US/Canada phone numbers into a headerless four-column CSV.

Output columns: country code (1), area code, ten-digit phone number, US.
Run with: python phone_csv_tool.py
"""

import csv
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk


ALLOWED_CHARS = re.compile(r"\+?[\d\s().-]+\Z")


def convert_number(raw: str) -> list[str]:
    """Return ['1', 'AAA', 'AAABBBCCCC', 'US'] or raise ValueError."""
    value = raw.strip().strip('"').strip("'").strip()
    if not ALLOWED_CHARS.fullmatch(value):
        raise ValueError("contains characters other than digits or phone punctuation")

    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError("must have 10 digits, optionally preceded by country code 1")
    return ["1", digits[:3], digits, "US"]


def convert_lines(text: str) -> tuple[list[list[str]], list[str]]:
    rows: list[list[str]] = []
    errors: list[str] = []
    for index, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(convert_number(line))
        except ValueError as exc:
            errors.append(f"Line {index}: {line.strip()} — {exc}")
    return rows, errors


def load_existing_rows(path: Path) -> list[list[str]]:
    """Read an existing CSV for append mode; refuse headers/unexpected data."""
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))

    for number, row in enumerate(rows, start=1):
        if (
            len(row) not in (3, 4)
            or row[0] != "1"
            or not (len(row[1]) == 3 and row[1].isdigit())
            or not (len(row[2]) == 10 and row[2].isdigit())
            or row[1] != row[2][:3]
            or (len(row) == 4 and row[3] != "US")
        ):
            raise ValueError(
                f"Existing CSV row {number} is not in the expected headerless "
                "1,AAA,AAABBBCCCC,US format. Select Replace instead, or fix the CSV."
            )
        # Upgrade files saved by the older version of this app on append.
        if len(row) == 3:
            row.append("US")
    return rows


def write_csv(path: Path, rows: list[list[str]], mode: str) -> tuple[Path, int]:
    """Back up the original, then atomically write the updated CSV."""
    if not path.is_file():
        raise FileNotFoundError(f"CSV file not found: {path}")
    existing = load_existing_rows(path) if mode == "append" else []
    all_rows = existing + rows

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = path.with_name(f"{path.stem}_backup_{timestamp}{path.suffix}")
    shutil.copy2(path, backup)

    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8", suffix=".csv",
            prefix=".phone_csv_", dir=path.parent, delete=False
        ) as handle:
            temporary_name = handle.name
            csv.writer(handle).writerows(all_rows)
        shutil.copymode(path, temporary_name)
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)

    return backup, len(all_rows)


class PhoneCSVApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Phone Number → CSV")
        root.geometry("760x650")
        root.minsize(590, 520)

        self.file_path = tk.StringVar()
        self.mode = tk.StringVar(value="replace")
        self.status = tk.StringVar(value="Paste one phone number per line.")

        main = ttk.Frame(root, padding=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(4, weight=3)
        main.rowconfigure(7, weight=2)

        ttk.Label(main, text="Target CSV file (existing file)").grid(
            row=0, column=0, sticky="w"
        )
        file_line = ttk.Frame(main)
        file_line.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        file_line.columnconfigure(0, weight=1)
        ttk.Entry(file_line, textvariable=self.file_path).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(file_line, text="Browse…", command=self.browse).grid(
            row=0, column=1
        )

        options = ttk.Frame(main)
        options.grid(row=2, column=0, sticky="w", pady=(0, 12))
        ttk.Label(options, text="Save mode:").pack(side="left", padx=(0, 8))
        ttk.Radiobutton(
            options, text="Replace existing rows", variable=self.mode, value="replace"
        ).pack(side="left", padx=(0, 14))
        ttk.Radiobutton(
            options, text="Append new rows", variable=self.mode, value="append"
        ).pack(side="left")

        ttk.Label(main, text="Paste phone numbers (one per line)").grid(
            row=3, column=0, sticky="w"
        )
        self.input_text = scrolledtext.ScrolledText(main, wrap="none", height=11)
        self.input_text.grid(row=4, column=0, sticky="nsew", pady=(4, 10))

        actions = ttk.Frame(main)
        actions.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(actions, text="Preview", command=self.preview).pack(side="left")
        ttk.Button(actions, text="Save to CSV", command=self.save).pack(
            side="left", padx=(10, 0)
        )
        ttk.Button(actions, text="Clear input", command=self.clear).pack(
            side="right"
        )

        ttk.Label(main, text="Preview (country code, area code, 10-digit number, US)").grid(
            row=6, column=0, sticky="w"
        )
        self.preview_text = scrolledtext.ScrolledText(
            main, wrap="none", height=8, state="disabled"
        )
        self.preview_text.grid(row=7, column=0, sticky="nsew", pady=(4, 8))
        ttk.Label(main, textvariable=self.status).grid(row=8, column=0, sticky="w")

    def browse(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select the CSV file to edit",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if selected:
            self.file_path.set(selected)

    def refresh_preview(self) -> tuple[list[list[str]], list[str]]:
        rows, errors = convert_lines(self.input_text.get("1.0", "end-1c"))
        content = "\n".join(",".join(row) for row in rows)
        if errors:
            content += "\n\nINVALID INPUT (nothing will be saved until fixed):\n"
            content += "\n".join(errors)
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", content)
        self.preview_text.config(state="disabled")
        self.status.set(f"{len(rows)} valid number(s), {len(errors)} invalid line(s).")
        return rows, errors

    def preview(self) -> None:
        self.refresh_preview()

    def clear(self) -> None:
        self.input_text.delete("1.0", "end")
        self.refresh_preview()

    def save(self) -> None:
        path = Path(self.file_path.get().strip().strip('"'))
        if not path.is_file():
            messagebox.showerror("Choose a CSV", "Select an existing CSV file first.")
            return

        rows, errors = self.refresh_preview()
        if errors:
            messagebox.showerror(
                "Invalid phone numbers",
                "Fix the invalid lines shown in the preview before saving."
            )
            return
        if not rows:
            messagebox.showwarning("No numbers", "Paste at least one phone number.")
            return

        action = "replace all rows in" if self.mode.get() == "replace" else "append rows to"
        if not messagebox.askyesno(
            "Confirm CSV update",
            f"This will {action}:\n{path}\n\n"
            f"New numbers: {len(rows)}\nA backup of the original will be saved first.\n\nContinue?",
        ):
            return

        try:
            backup, count = write_csv(path, rows, self.mode.get())
        except (OSError, UnicodeError, csv.Error, ValueError) as exc:
            messagebox.showerror("Could not save CSV", str(exc))
            return

        self.status.set(f"Saved {len(rows)} number(s). CSV now has {count} row(s).")
        messagebox.showinfo(
            "CSV updated",
            f"Updated: {path}\nNew rows: {len(rows)}\n"
            f"Total rows: {count}\nBackup: {backup}"
        )


if __name__ == "__main__":
    window = tk.Tk()
    PhoneCSVApp(window)
    window.mainloop()
