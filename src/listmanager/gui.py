from __future__ import annotations

import csv
import os
import queue
import threading
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from listmanager.cli import SUPPORTED_EXTS, _gather_input_files
from listmanager.config import build_config
from listmanager.core.dbf_breakdown import (
    DBFBreakdown,
    RULE_INFO,
    analyze_dbf,
    create_clean_and_quarantine,
    export_records_by_column,
    list_dbf_columns,
    prepare_clean_export,
)
from listmanager.core.merge import merge_files
from listmanager.format_checker import ConversionResult, convert_many, scan_many


class BackgroundTask:
    def __init__(self, target, on_success, on_error, on_done) -> None:
        self.target = target
        self.on_success = on_success
        self.on_error = on_error
        self.on_done = on_done


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("List Manager")
        self.geometry("900x650")
        self.minsize(780, 520)

        self.input_dir = tk.StringVar(value=str(Path("ListInput").resolve()))
        self.output_dir = tk.StringVar(value=str(Path("out").resolve()))
        self.start_row = tk.IntVar(value=8)
        self.status = tk.StringVar(value="")
        self.dbf_status = tk.StringVar(value="Ready.")
        self.dbf_path = tk.StringVar(value="No file selected.")
        self.detected_column = tk.StringVar(value="")
        self.selected_dbf: Path | None = None
        self.dbf_columns: list[str] = []
        self.dbf_column = tk.StringVar(value="")
        self.last_dbf_result: DBFBreakdown | None = None
        self.dbf_records: list[dict[str, object]] = []
        self.dbf_headers: list[str] = []
        self.dbf_clean_records: list[dict[str, object]] | None = None
        self.dbf_quarantine_records: list[dict[str, object]] | None = None
        self.dbf_quarantine_headers: list[str] | None = None
        self.format_input = tk.StringVar(value="")
        self.format_output_dir = tk.StringVar(value=str(Path("examples/converted_outputs").resolve()))
        self.format_status = tk.StringVar(value="Ready.")
        self.format_inputs: list[Path] = []
        self.format_results: list[ConversionResult] = []
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running_tasks = 0

        self._configure_style()
        self._build_ui()
        self.refresh_file_list()
        self.after(100, self._poll_events)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TButton", padding=(10, 5))
        style.configure("TLabel", padding=(0, 2))
        style.configure("Status.TLabel", foreground="#555555")

    def _build_ui(self) -> None:
        tabs = ttk.Notebook(self)
        tabs.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        tabs.add(self._build_merge_tab(tabs), text="Merge")
        tabs.add(self._build_format_checker_tab(tabs), text="Format Checker")
        tabs.add(self._build_dbf_tab(tabs), text="DBF Breakdown")

    def _build_merge_tab(self, parent: ttk.Notebook) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=10)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)

        ttk.Label(frame, text="Input Dir").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.input_dir).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="Browse...", command=self._browse_input_dir).grid(row=0, column=2, padx=(8, 0), pady=4)

        ttk.Label(frame, text="Data Start Row").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(frame, from_=1, to=1_000_000, textvariable=self.start_row, width=12).grid(
            row=1, column=1, sticky="w", pady=4
        )

        ttk.Label(frame, text="Output Dir").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.output_dir).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="Browse...", command=self._browse_output_dir).grid(row=2, column=2, padx=(8, 0), pady=4)

        ttk.Label(frame, text="Detected Files").grid(row=3, column=0, sticky="nw", padx=(0, 8), pady=4)
        files_frame = ttk.Frame(frame)
        files_frame.grid(row=3, column=1, columnspan=2, sticky="nsew", pady=4)
        files_frame.columnconfigure(0, weight=1)
        self.files_list = tk.Listbox(files_frame, height=7, activestyle="none")
        self.files_list.grid(row=0, column=0, sticky="nsew")
        files_scroll = ttk.Scrollbar(files_frame, orient=tk.VERTICAL, command=self.files_list.yview)
        files_scroll.grid(row=0, column=1, sticky="ns")
        self.files_list.configure(yscrollcommand=files_scroll.set)

        actions = ttk.Frame(frame)
        actions.grid(row=4, column=1, columnspan=2, sticky="ew", pady=(4, 8))
        self.run_button = ttk.Button(actions, text="Run Merge", command=self.run_merge)
        self.run_button.pack(side=tk.LEFT)
        ttk.Button(actions, text="Refresh Files", command=self.refresh_file_list).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Clear Log", command=self.clear_log).pack(side=tk.RIGHT)

        ttk.Label(frame, text="Log").grid(row=5, column=0, sticky="nw", padx=(0, 8), pady=4)
        log_frame = ttk.Frame(frame)
        log_frame.grid(row=5, column=1, columnspan=2, sticky="nsew", pady=4)
        frame.rowconfigure(5, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, wrap=tk.WORD, height=12, state=tk.DISABLED)
        self.log.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_scroll.set)

        ttk.Label(frame, textvariable=self.status, style="Status.TLabel").grid(
            row=6, column=0, columnspan=3, sticky="ew", pady=(8, 0)
        )
        return frame

    def _build_format_checker_tab(self, parent: ttk.Notebook) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=10)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(3, weight=1)

        ttk.Label(frame, text="Messy Inputs").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.format_input).grid(row=0, column=1, sticky="ew", pady=4)
        input_actions = ttk.Frame(frame)
        input_actions.grid(row=0, column=2, sticky="e", padx=(8, 0), pady=4)
        ttk.Button(input_actions, text="Files...", command=self._select_format_files).pack(side=tk.LEFT)
        ttk.Button(input_actions, text="Folder...", command=self._select_format_folder).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(frame, text="Output Folder").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.format_output_dir).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="Browse...", command=self._browse_format_output_dir).grid(
            row=1, column=2, sticky="e", padx=(8, 0), pady=4
        )

        actions = ttk.Frame(frame)
        actions.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(6, 8))
        self.format_scan_button = ttk.Button(actions, text="Scan", command=self.run_format_scan)
        self.format_scan_button.pack(side=tk.LEFT)
        self.format_convert_button = ttk.Button(actions, text="Convert", command=self.run_format_convert)
        self.format_convert_button.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Open Output Folder", command=self.open_format_output_folder).pack(side=tk.RIGHT)

        columns = ("file", "format", "scanned", "converted", "review", "warnings", "errors", "output")
        self.format_table = ttk.Treeview(frame, columns=columns, show="headings")
        headings = {
            "file": "File",
            "format": "Detected Format",
            "scanned": "Rows Scanned",
            "converted": "Converted Rows",
            "review": "Needs Review Rows",
            "warnings": "Warnings",
            "errors": "Errors",
            "output": "Output File",
        }
        widths = {
            "file": 190,
            "format": 120,
            "scanned": 95,
            "converted": 105,
            "review": 120,
            "warnings": 80,
            "errors": 70,
            "output": 210,
        }
        for column in columns:
            self.format_table.heading(column, text=headings[column])
            anchor = tk.W if column in {"file", "format", "output"} else tk.E
            self.format_table.column(column, width=widths[column], anchor=anchor)
        self.format_table.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=4)

        ttk.Label(frame, textvariable=self.format_status, style="Status.TLabel").grid(
            row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0)
        )
        return frame

    def _build_dbf_tab(self, parent: ttk.Notebook) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=10)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Button(frame, text="Select DBF File...", command=self._select_dbf_file).grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=4
        )
        ttk.Label(frame, textvariable=self.dbf_path).grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(frame, text="Detected grouping column").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Label(frame, textvariable=self.detected_column).grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(frame, text="Split/export column").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        self.dbf_column_combo = ttk.Combobox(frame, textvariable=self.dbf_column, state="disabled", values=[])
        self.dbf_column_combo.grid(row=2, column=1, columnspan=2, sticky="ew", pady=4)

        button_row = ttk.Frame(frame)
        button_row.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(6, 8))
        self.analyze_button = ttk.Button(button_row, text="Analyze", command=self.run_dbf_analysis)
        self.analyze_button.pack(side=tk.LEFT)
        self.clean_button = ttk.Button(button_row, text="Create Clean List", command=self._create_clean_list, state=tk.DISABLED)
        self.clean_button.pack(side=tk.LEFT, padx=(8, 0))
        self.export_button = ttk.Button(button_row, text="Export Lists", command=self._export_default_lists, state=tk.DISABLED)
        self.export_button.pack(side=tk.LEFT, padx=(8, 0))
        self.export_clean_button = ttk.Button(
            button_row, text="Export Clean List", command=lambda: self._export_dataset("clean"), state=tk.DISABLED
        )
        self.export_clean_button.pack(side=tk.LEFT, padx=(8, 0))
        self.export_quarantine_button = ttk.Button(
            button_row,
            text="Export Quarantined Rows",
            command=lambda: self._export_dataset("quarantine"),
            state=tk.DISABLED,
        )
        self.export_quarantine_button.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(frame, text="Validation Summary").grid(row=4, column=0, sticky="nw", padx=(0, 8), pady=4)
        summary_frame = ttk.Frame(frame)
        summary_frame.grid(row=4, column=1, columnspan=2, sticky="nsew", pady=4)
        summary_frame.columnconfigure(0, weight=1)
        self.dbf_summary = tk.Text(summary_frame, wrap=tk.WORD, height=8, state=tk.DISABLED)
        self.dbf_summary.grid(row=0, column=0, sticky="nsew")
        self._set_text(self.dbf_summary, "Run Analyze to see validation summary.")

        columns = ("value", "count", "percent")
        self.dbf_table = ttk.Treeview(frame, columns=columns, show="headings")
        self.dbf_table.heading("value", text="Group Value")
        self.dbf_table.heading("count", text="Count")
        self.dbf_table.heading("percent", text="Percent")
        self.dbf_table.column("value", width=360)
        self.dbf_table.column("count", width=100, anchor=tk.E)
        self.dbf_table.column("percent", width=100, anchor=tk.E)
        self.dbf_table.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=4)

        ttk.Label(frame, textvariable=self.dbf_status, style="Status.TLabel").grid(
            row=6, column=0, columnspan=3, sticky="ew", pady=(8, 0)
        )
        return frame

    def _browse_input_dir(self) -> None:
        directory = filedialog.askdirectory(title="Select Input Directory", initialdir=self.input_dir.get())
        if directory:
            self.input_dir.set(directory)
            self.refresh_file_list()

    def _browse_output_dir(self) -> None:
        directory = filedialog.askdirectory(title="Select Output Directory", initialdir=self.output_dir.get())
        if directory:
            self.output_dir.set(directory)

    def _select_format_files(self) -> None:
        file_paths = filedialog.askopenfilenames(
            title="Select Messy Excel Files",
            filetypes=[("Excel Files", "*.xlsx *.xlsm"), ("All Files", "*.*")],
        )
        if not file_paths:
            return
        self.format_inputs = [Path(path) for path in file_paths]
        self.format_input.set("; ".join(path.name for path in self.format_inputs))

    def _select_format_folder(self) -> None:
        directory = filedialog.askdirectory(title="Select Messy Input Folder")
        if not directory:
            return
        self.format_inputs = [Path(directory)]
        self.format_input.set(directory)

    def _browse_format_output_dir(self) -> None:
        directory = filedialog.askdirectory(title="Select Format Checker Output Folder", initialdir=self.format_output_dir.get())
        if directory:
            self.format_output_dir.set(directory)

    def _select_dbf_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select DBF File",
            initialdir=str(self.selected_dbf.parent if self.selected_dbf else Path.cwd()),
            filetypes=[("DBF Files", "*.dbf"), ("All Files", "*.*")],
        )
        if not file_path:
            return
        self.selected_dbf = Path(file_path)
        self.dbf_path.set(str(self.selected_dbf))
        self._reset_dbf_state()
        self._load_dbf_columns(self.selected_dbf)

    def refresh_file_list(self) -> None:
        self.files_list.delete(0, tk.END)
        path = Path(self.input_dir.get())
        if not path.is_dir():
            self.files_list.insert(tk.END, "Input directory not found.")
            self.status.set("Input directory missing.")
            return
        files = [p for p in sorted(path.iterdir()) if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]
        if not files:
            self.files_list.insert(tk.END, "No supported files found.")
            self.status.set("Waiting for files...")
            return
        for file_path in files:
            self.files_list.insert(tk.END, file_path.name)
        self.status.set(f"{len(files)} file(s) ready.")

    def run_merge(self) -> None:
        inputdir = Path(self.input_dir.get())
        outdir = Path(self.output_dir.get())
        start_row = self.start_row.get()
        if not inputdir.is_dir():
            messagebox.showwarning("Invalid Input Directory", f"Input directory not found:\n{inputdir}")
            return

        self._append_log("Starting merge...")
        self.status.set("Running...")
        self.run_button.configure(state=tk.DISABLED)

        def work() -> dict[str, int]:
            cfg = build_config(start_row)
            self.events.put(("log", f"Using data_start_row={cfg['data_start_row']}"))
            input_files = _gather_input_files(inputdir)
            outdir.mkdir(parents=True, exist_ok=True)
            self.events.put(("log", f"Running merge for {len(input_files)} files..."))
            return merge_files(input_files, outdir, cfg)

        self._run_background(
            work,
            on_success=self._merge_succeeded,
            on_error=lambda text: self._task_error("Merge Error", text, self.status),
            on_done=lambda: self.run_button.configure(state=tk.NORMAL),
        )

    def run_dbf_analysis(self) -> None:
        if not self.selected_dbf:
            messagebox.showwarning("Select DBF File", "Please select a DBF file first.")
            return
        if not self.selected_dbf.is_file():
            messagebox.showwarning("Missing File", f"Selected DBF file not found:\n{self.selected_dbf}")
            return
        column_choice = self.dbf_column.get().strip()
        if not column_choice:
            messagebox.showwarning("Choose Column", "Select a column to analyze/split by before running.")
            return

        self._reset_dbf_result()
        self.dbf_status.set("Analyzing...")
        self.analyze_button.configure(state=tk.DISABLED)

        self._run_background(
            lambda: analyze_dbf(str(self.selected_dbf), preferred_column=column_choice),
            on_success=self._dbf_succeeded,
            on_error=lambda text: self._task_error("DBF Analysis Error", text, self.dbf_status),
            on_done=lambda: self.analyze_button.configure(state=tk.NORMAL),
        )

    def _format_input_paths(self) -> list[Path]:
        if self.format_inputs:
            return self.format_inputs
        text = self.format_input.get().strip()
        return [Path(text)] if text else []

    def run_format_scan(self) -> None:
        input_paths = self._format_input_paths()
        if not input_paths:
            messagebox.showwarning("Format Checker", "Select messy input files or a folder first.")
            return
        output_dir = Path(self.format_output_dir.get())
        self.format_status.set("Scanning...")
        self.format_scan_button.configure(state=tk.DISABLED)

        self._run_background(
            lambda: scan_many(input_paths, output_dir),
            on_success=self._format_scan_succeeded,
            on_error=lambda text: self._task_error("Format Checker Scan Error", text, self.format_status),
            on_done=lambda: self.format_scan_button.configure(state=tk.NORMAL),
        )

    def run_format_convert(self) -> None:
        input_paths = self._format_input_paths()
        if not input_paths:
            messagebox.showwarning("Format Checker", "Select messy input files or a folder first.")
            return
        output_dir = Path(self.format_output_dir.get())
        output_dir.mkdir(parents=True, exist_ok=True)
        self.format_status.set("Converting...")
        self.format_convert_button.configure(state=tk.DISABLED)

        self._run_background(
            lambda: convert_many(input_paths, output_dir),
            on_success=self._format_convert_succeeded,
            on_error=lambda text: self._task_error("Format Checker Convert Error", text, self.format_status),
            on_done=lambda: self.format_convert_button.configure(state=tk.NORMAL),
        )

    def _run_background(self, target, on_success, on_error, on_done) -> None:
        task = BackgroundTask(target, on_success, on_error, on_done)
        self.running_tasks += 1

        def runner() -> None:
            try:
                self.events.put(("success", (task, target())))
            except Exception:
                self.events.put(("error", (task, traceback.format_exc())))
            finally:
                self.events.put(("done", task))

        threading.Thread(target=runner, daemon=True).start()

    def _poll_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(payload))
            elif kind == "success":
                task, result = payload
                task.on_success(result)
            elif kind == "error":
                task, text = payload
                task.on_error(text)
            elif kind == "done":
                payload.on_done()
                self.running_tasks = max(0, self.running_tasks - 1)
        self.after(100, self._poll_events)

    def _merge_succeeded(self, summary: dict[str, int]) -> None:
        self._append_log(
            "Rows written - merged_us: {merged_us}, international: {international}, errors: {errors}".format(
                **summary
            )
        )
        self._append_log("Merge finished successfully.")
        self.status.set("Completed.")
        self.refresh_file_list()

    def _dbf_succeeded(self, breakdown: DBFBreakdown) -> None:
        self.last_dbf_result = breakdown
        self.dbf_records = breakdown.records
        self.dbf_headers = breakdown.headers
        self.detected_column.set(breakdown.detected_column)
        self._set_combo_values(breakdown.columns, selected=breakdown.detected_column)
        for item in self.dbf_table.get_children():
            self.dbf_table.delete(item)
        for row in breakdown.rows:
            self.dbf_table.insert("", tk.END, values=(row.value, row.count, f"{row.percent:.2f}%"))
        self._update_validation_summary()
        self._update_export_controls()
        if breakdown.barcode_missing:
            self.dbf_status.set(f"Barcode missing in {len(breakdown.barcode_missing)} row(s).")
        else:
            self.dbf_status.set("Analysis completed.")

    def _format_scan_succeeded(self, results: list[ConversionResult]) -> None:
        self.format_results = results
        self._populate_format_results(results)
        self.format_status.set(f"Scan completed for {len(results)} file(s).")

    def _format_convert_succeeded(self, results: list[ConversionResult]) -> None:
        self.format_results = results
        self._populate_format_results(results)
        converted = sum(1 for result in results if result.output_path)
        review_rows = sum(result.rows_needing_review for result in results)
        self.format_status.set(f"Converted {converted} file(s). Needs review rows: {review_rows}.")

    def _populate_format_results(self, results: list[ConversionResult]) -> None:
        for item in self.format_table.get_children():
            self.format_table.delete(item)
        for result in results:
            self.format_table.insert(
                "",
                tk.END,
                values=(
                    result.source_path.name,
                    result.detected_format,
                    result.rows_scanned,
                    result.rows_converted,
                    result.rows_needing_review,
                    result.warning_count,
                    result.error_count,
                    result.output_path.name if result.output_path else "",
                ),
            )

    def open_format_output_folder(self) -> None:
        output_dir = Path(self.format_output_dir.get())
        output_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(output_dir)

    def _task_error(self, title: str, text: str, status_var: tk.StringVar) -> None:
        status_var.set("Error encountered.")
        messagebox.showerror(title, text)

    def _load_dbf_columns(self, path: Path) -> None:
        try:
            columns = list_dbf_columns(str(path))
        except Exception as exc:
            self._set_combo_values([])
            messagebox.showwarning("DBF Columns", f"Unable to read columns:\n{exc}")
            return
        selected = "SCHOOL" if "SCHOOL" in {column.upper() for column in columns} else (columns[0] if columns else "")
        if selected == "SCHOOL":
            selected = next(column for column in columns if column.upper() == "SCHOOL")
        self._set_combo_values(columns, selected=selected)
        self.dbf_status.set("Ready to analyze.")

    def _set_combo_values(self, values: list[str], selected: str = "") -> None:
        self.dbf_columns = list(values)
        self.dbf_column_combo.configure(values=self.dbf_columns, state="readonly" if values else "disabled")
        self.dbf_column.set(selected if selected in values else (values[0] if values else ""))

    def _reset_dbf_state(self) -> None:
        self._reset_dbf_result()
        self.detected_column.set("")
        self.dbf_status.set("Ready.")

    def _reset_dbf_result(self) -> None:
        self.last_dbf_result = None
        self.dbf_records = []
        self.dbf_headers = []
        self.dbf_clean_records = None
        self.dbf_quarantine_records = None
        self.dbf_quarantine_headers = None
        self._set_text(self.dbf_summary, "Run Analyze to see validation summary.")
        for item in self.dbf_table.get_children():
            self.dbf_table.delete(item)
        self._update_export_controls()

    def _update_validation_summary(self) -> None:
        if not self.last_dbf_result:
            self._set_text(self.dbf_summary, "Run Analyze to see validation summary.")
            return

        validation = self.last_dbf_result.validation
        lines = [
            f"Total records: {validation.total_rows}",
            f"Hard stop errors: {validation.hard_stop_total}",
            f"Review warnings: {validation.review_total}",
        ]
        if any(validation.hard_stop_counts.values()):
            lines.extend(["", "Hard-stop details:"])
            lines.extend(f"  - {desc}: {count}" for desc, count in validation.hard_stop_counts.items() if count)
        if any(validation.review_counts.values()):
            lines.extend(["", "Review warnings:"])
            lines.extend(f"  - {desc}: {count}" for desc, count in validation.review_counts.items() if count)
        self._set_text(self.dbf_summary, "\n".join(lines))

    def _update_export_controls(self) -> None:
        has_result = self.last_dbf_result is not None and bool(self.dbf_records)
        validation = self.last_dbf_result.validation if self.last_dbf_result else None
        has_rules = bool(
            validation
            and any(count for count in {**validation.hard_stop_counts, **validation.review_counts}.values())
        )
        self.clean_button.configure(state=tk.NORMAL if has_rules else tk.DISABLED)
        self.export_button.configure(state=tk.NORMAL if has_result and self.dbf_clean_records is None else tk.DISABLED)
        self.export_clean_button.configure(state=tk.NORMAL if self.dbf_clean_records else tk.DISABLED)
        self.export_quarantine_button.configure(state=tk.NORMAL if self.dbf_quarantine_records else tk.DISABLED)

    def _create_clean_list(self) -> None:
        if not self.last_dbf_result or not self.dbf_records:
            messagebox.showinfo("Create Clean List", "Run Analyze before creating a clean list.")
            return
        selected_rules = self._prompt_quarantine_rules()
        if selected_rules is None:
            return
        if not selected_rules:
            messagebox.showinfo("Create Clean List", "Select at least one rule to quarantine.")
            return
        clean, quarantine, quarantine_headers = create_clean_and_quarantine(
            self.dbf_records,
            self.dbf_headers,
            self.last_dbf_result.validation,
            selected_rules=selected_rules,
        )
        self.dbf_clean_records = clean
        self.dbf_quarantine_records = quarantine or None
        self.dbf_quarantine_headers = quarantine_headers if quarantine else None
        self.dbf_status.set(f"Clean list ready. Removed {len(quarantine)} row(s).")
        self._update_export_controls()

    def _prompt_quarantine_rules(self) -> list[str] | None:
        validation = self.last_dbf_result.validation if self.last_dbf_result else None
        if not validation:
            return None

        options: list[tuple[str, int, list[int]]] = []
        for desc, count in validation.hard_stop_counts.items():
            if count:
                options.append((desc, count, validation.hard_stop_rows_by_rule.get(desc, [])))
        for desc, count in validation.review_counts.items():
            if count:
                options.append((desc, count, validation.review_rows_by_rule.get(desc, [])))
        if not options:
            messagebox.showinfo("Create Clean List", "No warnings or errors available to quarantine.")
            return []

        dialog = tk.Toplevel(self)
        dialog.title("Select Rules to Quarantine")
        dialog.transient(self)
        dialog.grab_set()
        result: list[str] | None = None
        checks: list[tuple[str, tk.BooleanVar]] = []

        container = ttk.Frame(dialog, padding=12)
        container.pack(fill=tk.BOTH, expand=True)
        ttk.Label(container, text="Choose which warnings/errors should be quarantined:").pack(anchor="w")
        for desc, count, rows in options:
            var = tk.BooleanVar(value=True)
            ttk.Checkbutton(container, text=f"{desc} ({count})", variable=var).pack(anchor="w", pady=(8, 0))
            description = RULE_INFO.get(desc, {}).get("description", "")
            if description:
                ttk.Label(container, text=description, wraplength=560).pack(anchor="w", padx=(22, 0))
            row_text = f"Rows: {', '.join(map(str, rows[:20]))}{'...' if len(rows) > 20 else ''}"
            ttk.Label(container, text=row_text, wraplength=560).pack(anchor="w", padx=(22, 0))
            checks.append((desc, var))

        buttons = ttk.Frame(container)
        buttons.pack(fill=tk.X, pady=(12, 0))

        def accept() -> None:
            nonlocal result
            result = [desc for desc, var in checks if var.get()]
            dialog.destroy()

        def cancel() -> None:
            dialog.destroy()

        ttk.Button(buttons, text="OK", command=accept).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Cancel", command=cancel).pack(side=tk.RIGHT, padx=(0, 8))
        self.wait_window(dialog)
        return result

    def _export_default_lists(self) -> None:
        if not self.last_dbf_result:
            messagebox.showinfo("Export Lists", "Run an analysis before exporting.")
            return
        self._export_records("Export Lists", self.dbf_records, self.dbf_headers)

    def _export_dataset(self, dataset: str) -> None:
        if dataset == "clean":
            if not self.dbf_clean_records:
                messagebox.showinfo("Export Clean List", "Create a clean list first.")
                return
            headers, rows = prepare_clean_export(self.dbf_clean_records, self.dbf_headers)
            self._export_single_file("Export Clean List", rows, headers, "clean_list.csv")
            return
        if dataset == "quarantine":
            if not self.dbf_quarantine_records or not self.dbf_quarantine_headers:
                messagebox.showinfo("Export Quarantined Rows", "No quarantined records available.")
                return
            self._export_single_file(
                "Export Quarantined Rows",
                self.dbf_quarantine_records,
                self.dbf_quarantine_headers,
                "quarantine_rows.csv",
            )

    def _export_records(self, title: str, records: list[dict[str, object]], headers: list[str]) -> None:
        target_dir = filedialog.askdirectory(
            title="Select Export Folder",
            initialdir=str(self.selected_dbf.parent if self.selected_dbf else Path.cwd()),
        )
        if not target_dir:
            return
        try:
            files = export_records_by_column(records, headers, self.dbf_column.get().strip(), Path(target_dir))
        except Exception as exc:
            messagebox.showerror(title, str(exc))
            self.dbf_status.set("Export failed.")
            return
        self.dbf_status.set(f"{title}: Exported {len(files)} file(s).")
        messagebox.showinfo(title, f"Exported {len(files)} file(s) to:\n{target_dir}")

    def _export_single_file(
        self,
        title: str,
        records: list[dict[str, object]],
        headers: list[str],
        default_name: str,
    ) -> None:
        target_dir = filedialog.askdirectory(
            title="Select Export Folder",
            initialdir=str(self.selected_dbf.parent if self.selected_dbf else Path.cwd()),
        )
        if not target_dir:
            return
        dest = Path(target_dir) / default_name
        counter = 1
        while dest.exists():
            dest = Path(target_dir) / f"{Path(default_name).stem}_{counter}{Path(default_name).suffix}"
            counter += 1
        try:
            with dest.open("w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=headers)
                writer.writeheader()
                for row in records:
                    writer.writerow({header: row.get(header, "") for header in headers})
        except Exception as exc:
            messagebox.showerror(title, f"Failed to export list:\n{exc}")
            self.dbf_status.set("Export failed.")
            return
        self.dbf_status.set(f"{title}: Exported 1 file.")
        messagebox.showinfo(title, f"Exported file to:\n{dest}")

    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def clear_log(self) -> None:
        self._set_text(self.log, "")

    def _set_text(self, widget: tk.Text, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)


def main() -> None:
    app = MainWindow()
    app.protocol("WM_DELETE_WINDOW", app.destroy)
    app.mainloop()


if __name__ == "__main__":
    main()
