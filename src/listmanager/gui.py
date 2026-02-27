from __future__ import annotations

import csv
import sys
import traceback
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QCheckBox,
)

from qt_material import apply_stylesheet
import qdarktheme

from listmanager.cli import SUPPORTED_EXTS, _gather_input_files
from listmanager.config import build_config
from listmanager.core.merge import merge_files
from listmanager.core.dbf_breakdown import (
    DBFBreakdown,
    analyze_dbf,
    list_dbf_columns,
    export_records_by_column,
    create_clean_and_quarantine,
    prepare_clean_export,
    RULE_INFO,
)


class MergeWorker(QObject):
    finished = Signal()
    errored = Signal(str)
    message = Signal(str)

    def __init__(self, inputdir: Path, outdir: Path, start_row: int) -> None:
        super().__init__()
        self.inputdir = inputdir
        self.outdir = outdir
        self.start_row = start_row

    @Slot()
    def run(self) -> None:
        try:
            self.message.emit("Preparing configuration...")
            cfg = build_config(self.start_row)
            self.message.emit(f"Using data_start_row={cfg['data_start_row']}")

            self.message.emit("Discovering input files...")
            input_files = _gather_input_files(self.inputdir)

            self.message.emit(f"Ensuring output folder exists at {self.outdir}...")
            self.outdir.mkdir(parents=True, exist_ok=True)

            self.message.emit(f"Running merge for {len(input_files)} files...")
            summary = merge_files(input_files, self.outdir, cfg)
            self.message.emit(
                "Rows written - merged_us: {merged_us}, international: {international}, errors: {errors}".format(
                    **summary
                )
            )
            self.message.emit("Merge completed successfully.")
        except Exception:
            self.errored.emit(traceback.format_exc())
        finally:
            self.finished.emit()


class DBFBreakdownWorker(QObject):
    finished = Signal()
    errored = Signal(str)
    succeeded = Signal(object)

    def __init__(self, path: Path, column_name: Optional[str]) -> None:
        super().__init__()
        self.path = path
        self.column_name = column_name

    @Slot()
    def run(self) -> None:
        try:
            breakdown = analyze_dbf(str(self.path), preferred_column=self.column_name)
            self.succeeded.emit(breakdown)
        except Exception:
            self.errored.emit(traceback.format_exc())
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("List Manager")
        self.worker_thread: Optional[QThread] = None
        self.worker: Optional[MergeWorker] = None
        self.dbf_worker_thread: Optional[QThread] = None
        self.dbf_worker: Optional[DBFBreakdownWorker] = None
        self._had_error = False
        self._dbf_had_error = False
        self.selected_dbf: Optional[Path] = None
        self._last_dbf_result: Optional[DBFBreakdown] = None
        self.dbf_records: list[dict[str, object]] = []
        self.dbf_headers: list[str] = []
        self.dbf_validation = None
        self.dbf_clean_records: Optional[list[dict[str, object]]] = None
        self.dbf_quarantine_records: Optional[list[dict[str, object]]] = None
        self.dbf_quarantine_headers: Optional[list[str]] = None
        self.current_theme = "material_dark"
        self.theme_action_group: Optional[QActionGroup] = None
        self._build_ui()
        self._reset_dbf_state()
        self._setup_menu()
        self.apply_theme(self.current_theme)
        self.refresh_file_list()

    def _build_ui(self) -> None:
        container = QWidget(self)
        root_layout = QVBoxLayout()
        container.setLayout(root_layout)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_merge_tab(), "Merge")
        self.tabs.addTab(self._build_dbf_tab(), "DBF Breakdown")
        root_layout.addWidget(self.tabs)

        self.setCentralWidget(container)

    def _setup_menu(self) -> None:
        settings_menu = self.menuBar().addMenu("Settings")
        theme_menu = settings_menu.addMenu("Theme")
        self.theme_action_group = QActionGroup(self)
        self.theme_action_group.setExclusive(True)

        themes = [
            ("Material Light (qt-material)", "material_light"),
            ("Material Dark (qt-material)", "material_dark"),
            ("Dark Mode (PyQtDarkTheme)", "qdark_dark"),
        ]

        for label, key in themes:
            action = theme_menu.addAction(label)
            action.setCheckable(True)
            action.setData(key)
            if key == self.current_theme:
                action.setChecked(True)
            self.theme_action_group.addAction(action)

        def on_theme_triggered(action):
            if action and action.data():
                self.apply_theme(action.data())

        self.theme_action_group.triggered.connect(on_theme_triggered)

    def _build_merge_tab(self) -> QWidget:
        tab = QWidget()
        layout = QGridLayout()
        tab.setLayout(layout)

        # Input directory
        self.input_edit = QLineEdit(str(Path("ListInput").resolve()))
        browse_input = QPushButton("Browse...")
        browse_input.clicked.connect(self._browse_input_dir)
        layout.addWidget(QLabel("Input Dir"), 0, 0)
        layout.addWidget(self.input_edit, 0, 1)
        layout.addWidget(browse_input, 0, 2)

        # Data start row
        self.start_row_spin = QSpinBox()
        self.start_row_spin.setRange(1, 1_000_000)
        self.start_row_spin.setValue(8)
        layout.addWidget(QLabel("Data Start Row"), 1, 0)
        layout.addWidget(self.start_row_spin, 1, 1)

        # Output directory
        self.output_edit = QLineEdit(str(Path("out").resolve()))
        browse_output = QPushButton("Browse...")
        browse_output.clicked.connect(self._browse_output_dir)
        layout.addWidget(QLabel("Output Dir"), 2, 0)
        layout.addWidget(self.output_edit, 2, 1)
        layout.addWidget(browse_output, 2, 2)

        # File list + actions
        self.files_list = QListWidget()
        refresh_button = QPushButton("Refresh Files")
        refresh_button.clicked.connect(self.refresh_file_list)

        layout.addWidget(QLabel("Detected Files"), 3, 0)
        layout.addWidget(self.files_list, 3, 1, 1, 2)
        layout.addWidget(refresh_button, 4, 2)

        # Run + status/log
        self.run_button = QPushButton("Run Merge")
        self.run_button.clicked.connect(self.run_merge)
        layout.addWidget(self.run_button, 4, 1)

        self.clear_log_button = QPushButton("Clear Log")
        self.clear_log_button.clicked.connect(self.clear_log)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("Log"))
        log_header.addStretch()
        log_header.addWidget(self.clear_log_button)
        layout.addLayout(log_header, 5, 0, 1, 3)
        layout.addWidget(self.log, 6, 0, 1, 3)

        self.status_label = QLabel("")
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Status:"))
        status_layout.addWidget(self.status_label, stretch=1)
        layout.addLayout(status_layout, 7, 0, 1, 3)

        return tab

    def _build_dbf_tab(self) -> QWidget:
        tab = QWidget()
        layout = QGridLayout()
        tab.setLayout(layout)

        self.dbf_path_label = QLabel("No file selected.")
        select_button = QPushButton("Select DBF File...")
        select_button.clicked.connect(self._select_dbf_file)

        layout.addWidget(select_button, 0, 0)
        layout.addWidget(self.dbf_path_label, 0, 1, 1, 2)

        self.dbf_detected_label = QLabel("")
        detected_layout = QHBoxLayout()
        detected_layout.addWidget(QLabel("Detected grouping column:"))
        detected_layout.addWidget(self.dbf_detected_label, stretch=1)
        layout.addLayout(detected_layout, 1, 0, 1, 3)

        self.dbf_column_combo = QComboBox()
        self.dbf_column_combo.setEnabled(False)
        column_layout = QHBoxLayout()
        column_layout.addWidget(QLabel("Split/export column:"))
        column_layout.addWidget(self.dbf_column_combo, stretch=1)
        layout.addLayout(column_layout, 2, 0, 1, 3)

        self.dbf_warning_label = QLabel("")
        self.dbf_warning_label.setWordWrap(True)
        self.dbf_warning_label.setStyleSheet(
            "background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; padding: 6px;"
        )
        self.dbf_warning_label.hide()
        layout.addWidget(self.dbf_warning_label, 3, 0, 1, 3)

        self.dbf_summary = QPlainTextEdit("Run Analyze to see validation summary.")
        self.dbf_summary.setReadOnly(True)
        layout.addWidget(self.dbf_summary, 4, 0, 1, 3)

        button_row = QHBoxLayout()
        self.dbf_analyze_button = QPushButton("Analyze")
        self.dbf_analyze_button.clicked.connect(self.run_dbf_analysis)
        button_row.addWidget(self.dbf_analyze_button)

        self.dbf_create_clean_button = QPushButton("Create Clean List")
        self.dbf_create_clean_button.setEnabled(False)
        self.dbf_create_clean_button.clicked.connect(self._create_clean_list)
        button_row.addWidget(self.dbf_create_clean_button)

        self.dbf_export_default_button = QPushButton("Export Lists")
        self.dbf_export_default_button.setEnabled(False)
        self.dbf_export_default_button.clicked.connect(self._export_default_lists)
        button_row.addWidget(self.dbf_export_default_button)

        self.dbf_export_clean_button = QPushButton("Export Clean List")
        self.dbf_export_clean_button.setEnabled(False)
        self.dbf_export_clean_button.clicked.connect(lambda: self._export_dataset("clean"))
        self.dbf_export_clean_button.hide()
        button_row.addWidget(self.dbf_export_clean_button)

        self.dbf_export_quarantine_button = QPushButton("Export Quarantined Rows")
        self.dbf_export_quarantine_button.setEnabled(False)
        self.dbf_export_quarantine_button.clicked.connect(lambda: self._export_dataset("quarantine"))
        self.dbf_export_quarantine_button.hide()
        button_row.addWidget(self.dbf_export_quarantine_button)
        button_row.addStretch()
        layout.addLayout(button_row, 5, 0, 1, 3)

        self.dbf_table = QTableWidget(0, 3)
        self.dbf_table.setHorizontalHeaderLabels(["Group Value", "Count", "Percent"])
        self.dbf_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.dbf_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Stretch)
        self.dbf_table.verticalHeader().setVisible(False)
        layout.addWidget(self.dbf_table, 6, 0, 1, 3)

        self.dbf_status_label = QLabel("Idle.")
        layout.addWidget(self.dbf_status_label, 7, 0, 1, 3)

        return tab

    def _browse_input_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select Input Directory", self.input_edit.text())
        if directory:
            self.input_edit.setText(directory)
            self.refresh_file_list()

    def _browse_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.output_edit.text())
        if directory:
            self.output_edit.setText(directory)

    def _select_dbf_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select DBF File",
            str(self.selected_dbf or Path.cwd()),
            "DBF Files (*.dbf);;All Files (*)",
        )
        if file_path:
            self.selected_dbf = Path(file_path)
            self.dbf_path_label.setText(str(self.selected_dbf))
            self.dbf_status_label.setText("Ready to analyze.")
            self._reset_dbf_state()
            self._load_dbf_columns(self.selected_dbf)
        else:
            if not self.selected_dbf:
                self.dbf_path_label.setText("No file selected.")
                self.dbf_column_combo.clear()
                self.dbf_column_combo.setEnabled(False)
                self._reset_dbf_state()

    def refresh_file_list(self) -> None:
        self.files_list.clear()
        path = Path(self.input_edit.text())
        if not path.is_dir():
            self.files_list.addItem(QListWidgetItem("Input directory not found."))
            self.status_label.setText("Input directory missing.")
            return

        files = [
            p for p in sorted(path.iterdir())
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
        ]
        if not files:
            self.files_list.addItem(QListWidgetItem("No supported files found."))
            self.status_label.setText("Waiting for files...")
            return

        for file_path in files:
            item = QListWidgetItem(file_path.name)
            item.setToolTip(str(file_path))
            self.files_list.addItem(item)

        self.status_label.setText(f"{len(files)} file(s) ready.")

    def append_log(self, text: str) -> None:
        self.log.appendPlainText(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def clear_log(self) -> None:
        self.log.clear()

    def _reset_dbf_state(self) -> None:
        self._last_dbf_result = None
        self.dbf_records = []
        self.dbf_headers = []
        self.dbf_validation = None
        self.dbf_clean_records = None
        self.dbf_quarantine_records = None
        self.dbf_quarantine_headers = None
        self._set_export_mode("default")
        if hasattr(self, "dbf_summary"):
            self._update_validation_summary()
        self.dbf_table.setRowCount(0)
        self.dbf_status_label.setText("Ready.")
        if hasattr(self, "dbf_create_clean_button"):
            self._update_export_controls()

    def _load_dbf_columns(self, path: Path) -> None:
        try:
            columns = list_dbf_columns(str(path))
        except Exception as exc:
            self.dbf_column_combo.clear()
            self.dbf_column_combo.setEnabled(False)
            QMessageBox.warning(self, "DBF Columns", f"Unable to read columns:\n{exc}")
            return

        self.dbf_column_combo.clear()
        self.dbf_column_combo.addItems(columns)
        school_idx = next(
            (i for i, name in enumerate(columns) if str(name).upper() == "SCHOOL"),
            None,
        )
        if school_idx is not None:
            self.dbf_column_combo.setCurrentIndex(school_idx)
        elif columns:
            self.dbf_column_combo.setCurrentIndex(0)
        self.dbf_column_combo.setEnabled(bool(columns))

    def _update_validation_summary(self) -> None:
        if not self.dbf_validation:
            self.dbf_summary.setPlainText("Run Analyze to see validation summary.")
            self.dbf_warning_label.hide()
            return

        validation = self.dbf_validation
        lines = [
            f"Total records: {validation.total_rows}",
            f"Hard stop errors: {validation.hard_stop_total}",
            f"Review warnings: {validation.review_total}",
        ]
        if any(validation.hard_stop_counts.values()):
            lines.append("")
            lines.append("Hard-stop details:")
            for desc, count in validation.hard_stop_counts.items():
                if count:
                    lines.append(f"  - {desc}: {count}")
        if any(validation.review_counts.values()):
            lines.append("")
            lines.append("Review warnings:")
            for desc, count in validation.review_counts.items():
                if count:
                    lines.append(f"  - {desc}: {count}")

        lines.append("")
        lines.append("Automation-ready records need ZIP5 + ZIP+4 + DLVPNT, STD_STATUS S/C/R, DPV_FLAG Y, and IMB populated.")
        self.dbf_summary.setPlainText("\n".join(lines))

        if validation.hard_stop_total > 0 and self.dbf_clean_records:
            self.dbf_warning_label.setText(
                f"Clean list excludes {validation.hard_stop_total} hard-stop row(s)."
            )
            self.dbf_warning_label.show()
        elif validation.hard_stop_total > 0:
            self.dbf_warning_label.setText(
                f"{validation.hard_stop_total} hard-stop row(s) detected. Consider creating a clean list."
            )
            self.dbf_warning_label.show()
        elif validation.review_total > 0:
            self.dbf_warning_label.setText(
                f"{validation.review_total} row(s) have review warnings. Double-check addresses."
            )
            self.dbf_warning_label.show()
        else:
            self.dbf_warning_label.hide()

    def _set_export_mode(self, mode: str) -> None:
        if mode == "clean":
            self.dbf_export_default_button.hide()
            self.dbf_export_clean_button.show()
            self.dbf_export_quarantine_button.show()
        else:
            self.dbf_export_default_button.show()
            self.dbf_export_clean_button.hide()
            self.dbf_export_quarantine_button.hide()

    def _update_export_controls(self) -> None:
        if not self.dbf_validation:
            self.dbf_create_clean_button.setVisible(False)
            self.dbf_create_clean_button.setEnabled(False)
            self.dbf_export_default_button.setEnabled(False)
            self.dbf_export_clean_button.setEnabled(False)
            self.dbf_export_quarantine_button.setEnabled(False)
            return

        has_rules = any(
            count for count in {**self.dbf_validation.hard_stop_counts, **self.dbf_validation.review_counts}.values()
        )
        has_records = bool(self.dbf_records)
        self.dbf_create_clean_button.setVisible(has_rules)
        self.dbf_create_clean_button.setEnabled(has_rules)

        if self.dbf_clean_records is not None:
            self._set_export_mode("clean")
            self.dbf_export_clean_button.setEnabled(bool(self.dbf_clean_records))
            self.dbf_export_quarantine_button.setEnabled(bool(self.dbf_quarantine_records))
        else:
            self._set_export_mode("default")
            self.dbf_export_default_button.setEnabled(has_records)
            self.dbf_export_clean_button.setEnabled(False)
            self.dbf_export_quarantine_button.setEnabled(False)

    def _prompt_quarantine_rules(self) -> list[str] | None:
        if not self.dbf_validation:
            return None

        options = []
        for desc, count in self.dbf_validation.hard_stop_counts.items():
            if count:
                rows = self.dbf_validation.hard_stop_rows_by_rule.get(desc, [])
                options.append(("Hard stop", desc, count, rows))
        for desc, count in self.dbf_validation.review_counts.items():
            if count:
                rows = self.dbf_validation.review_rows_by_rule.get(desc, [])
                options.append(("Review", desc, count, rows))

        if not options:
            QMessageBox.information(self, "Create Clean List", "No warnings or errors available to quarantine.")
            return []

        dialog = QDialog(self)
        dialog.setWindowTitle("Select Rules to Quarantine")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Choose which warnings/errors should be quarantined:"))

        checkboxes = []
        for category, desc, count, rows in options:
            group_layout = QVBoxLayout()
            cb = QCheckBox(f"{desc} ({count})")
            cb.setChecked(True)
            group_layout.addWidget(cb)
            desc_text = RULE_INFO.get(desc, {}).get("description", "")
            if desc_text:
                desc_label = QLabel(desc_text)
                desc_label.setWordWrap(True)
                desc_label.setStyleSheet("color: #666; padding-left: 12px;")
                group_layout.addWidget(desc_label)
            row_label = QLabel(f"Rows: {', '.join(map(str, rows[:20]))}{'...' if len(rows) > 20 else ''}")
            row_label.setStyleSheet("color: #555; padding-left: 12px;")
            group_layout.addWidget(row_label)
            layout.addLayout(group_layout)
            checkboxes.append((desc, cb))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() != QDialog.Accepted:
            return None

        selected = [desc for desc, cb in checkboxes if cb.isChecked()]
        return selected

    def run_dbf_analysis(self) -> None:
        if self.dbf_worker_thread and self.dbf_worker_thread.isRunning():
            return

        if not self.selected_dbf:
            QMessageBox.warning(self, "Select DBF File", "Please select a DBF file first.")
            return

        if not self.selected_dbf.is_file():
            QMessageBox.warning(self, "Missing File", f"Selected DBF file not found:\n{self.selected_dbf}")
            return

        column_choice = self.dbf_column_combo.currentText().strip()
        if not column_choice:
            QMessageBox.warning(self, "Choose Column", "Select a column to analyze/split by before running.")
            return

        self._dbf_had_error = False
        self._last_dbf_result = None
        self.dbf_records = []
        self.dbf_headers = []
        self.dbf_validation = None
        self.dbf_clean_records = None
        self.dbf_quarantine_records = None
        self.dbf_quarantine_headers = None
        self._set_export_mode("default")
        self.dbf_detected_label.setText("")
        self.dbf_table.setRowCount(0)
        self.dbf_summary.setPlainText("Analyzing...")
        self.dbf_warning_label.hide()
        self.dbf_status_label.setText("Analyzing...")
        self.dbf_analyze_button.setEnabled(False)
        self.dbf_create_clean_button.setEnabled(False)
        self.dbf_export_clean_button.setEnabled(False)
        self.dbf_export_quarantine_button.setEnabled(False)

        self.dbf_worker_thread = QThread(self)
        self.dbf_worker = DBFBreakdownWorker(self.selected_dbf, column_choice)
        self.dbf_worker.moveToThread(self.dbf_worker_thread)

        self.dbf_worker_thread.started.connect(self.dbf_worker.run)
        self.dbf_worker.succeeded.connect(self._handle_dbf_success)
        self.dbf_worker.errored.connect(self._handle_dbf_error)
        self.dbf_worker.finished.connect(self._dbf_analysis_finished)
        self.dbf_worker.finished.connect(self.dbf_worker_thread.quit)
        self.dbf_worker_thread.finished.connect(self.dbf_worker.deleteLater)
        self.dbf_worker_thread.finished.connect(self.dbf_worker_thread.deleteLater)
        self.dbf_worker_thread.start()

    @Slot(object)
    def _handle_dbf_success(self, breakdown: DBFBreakdown) -> None:
        self._last_dbf_result = breakdown
        self.dbf_records = breakdown.records
        self.dbf_headers = breakdown.headers
        self.dbf_validation = breakdown.validation
        self.dbf_clean_records = None
        self.dbf_quarantine_records = None
        self.dbf_quarantine_headers = None
        self.dbf_detected_label.setText(breakdown.detected_column)
        if self.dbf_column_combo.count():
            current_text = self.dbf_column_combo.currentText().strip()
            if not current_text:
                idx = self.dbf_column_combo.findText(breakdown.detected_column)
                if idx >= 0:
                    self.dbf_column_combo.setCurrentIndex(idx)
            self.dbf_column_combo.setEnabled(True)
        self.dbf_table.setRowCount(len(breakdown.rows))
        for row_idx, row in enumerate(breakdown.rows):
            self.dbf_table.setItem(row_idx, 0, QTableWidgetItem(row.value))
            self.dbf_table.setItem(row_idx, 1, QTableWidgetItem(str(row.count)))
            self.dbf_table.setItem(row_idx, 2, QTableWidgetItem(f"{row.percent:.2f}%"))
        if breakdown.barcode_missing:
            self.dbf_status_label.setText(
                f"Barcode missing in {len(breakdown.barcode_missing)} row(s)."
            )
        self._update_validation_summary()
        self._update_export_controls()

    @Slot(str)
    def _handle_dbf_error(self, text: str) -> None:
        self._dbf_had_error = True
        self.dbf_status_label.setText("Error encountered.")
        QMessageBox.critical(self, "DBF Analysis Error", text)

    @Slot()
    def _dbf_analysis_finished(self) -> None:
        self.dbf_analyze_button.setEnabled(True)
        if self._dbf_had_error and not self._last_dbf_result:
            self.dbf_export_clean_button.setEnabled(False)
        self.dbf_worker = None
        self.dbf_worker_thread = None
        self._update_export_controls()

    def _create_clean_list(self) -> None:
        if not self.dbf_validation or not self.dbf_records:
            QMessageBox.information(self, "Create Clean List", "Run Analyze before creating a clean list.")
            return
        selected_rules = self._prompt_quarantine_rules()
        if selected_rules is None:
            return
        if not selected_rules:
            QMessageBox.information(self, "Create Clean List", "Select at least one rule to quarantine.")
            return
        clean, quarantine, quarantine_headers = create_clean_and_quarantine(
            self.dbf_records,
            self.dbf_headers,
            self.dbf_validation,
            selected_rules=selected_rules,
        )
        self.dbf_clean_records = clean
        self.dbf_quarantine_records = quarantine if quarantine else None
        self.dbf_quarantine_headers = quarantine_headers if quarantine else None
        removed = len(quarantine)
        self.dbf_status_label.setText(
            f"Clean list ready. Removed {removed} hard-stop row(s)."
        )
        self._set_export_mode("clean")
        self._update_validation_summary()
        self._update_export_controls()

    def _export_default_lists(self) -> None:
        if not self._last_dbf_result or not self.selected_dbf:
            QMessageBox.information(self, "Export Lists", "Run an analysis before exporting.")
            return
        self._export_records(
            title="Export Lists",
            records=self.dbf_records,
            headers=self.dbf_headers,
        )

    def _export_dataset(self, dataset: str) -> None:
        if not self._last_dbf_result or not self.selected_dbf:
            QMessageBox.information(self, "Export Breakdown", "Run an analysis before exporting.")
            return

        if dataset == "clean":
            title = "Export Clean List"
            if self.dbf_validation and self.dbf_validation.hard_stop_total > 0 and not self.dbf_clean_records:
                QMessageBox.warning(self, title, "Please create a clean list before exporting.")
                return
            if not self.dbf_clean_records:
                QMessageBox.information(self, title, "Create a clean list first.")
                return
            headers, export_rows = prepare_clean_export(self.dbf_clean_records, self.dbf_headers)
            self._export_single_file(
                title=title,
                records=export_rows,
                headers=headers,
                default_name="clean_list.csv",
            )
            return
        elif dataset == "quarantine":
            title = "Export Quarantined Rows"
            records = self.dbf_quarantine_records
            headers = self.dbf_quarantine_headers
            if not records or not headers:
                QMessageBox.information(self, title, "No quarantined records available.")
                return
            self._export_single_file(
                title=title,
                records=records,
                headers=headers,
                default_name="quarantine_rows.csv",
            )
            return

        QMessageBox.warning(self, "Export", f"Unknown dataset requested: {dataset}")

    def _export_records(self, title: str, records: list, headers: list) -> None:
        target_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Export Folder",
            str(self.selected_dbf.parent if self.selected_dbf else Path.cwd()),
        )
        if not target_dir:
            return

        column_choice = self.dbf_column_combo.currentText().strip()
        if not column_choice:
            column_choice = self._last_dbf_result.detected_column or "SCHOOL"

        try:
            files = export_records_by_column(
                records,
                headers,
                column_name=column_choice,
                outdir=Path(target_dir),
            )
        except Exception as exc:
            QMessageBox.critical(self, title, str(exc))
            self.dbf_status_label.setText("Export failed.")
            return

        self.dbf_status_label.setText(f"{title}: Exported {len(files)} file(s).")
        QMessageBox.information(
            self,
            title,
            f"Exported {len(files)} file(s) to:\n{target_dir}",
        )

    def _export_single_file(
        self,
        title: str,
        records: list[dict],
        headers: list[str],
        default_name: str,
    ) -> None:
        target_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Export Folder",
            str(self.selected_dbf.parent if self.selected_dbf else Path.cwd()),
        )
        if not target_dir:
            return

        outdir = Path(target_dir)
        filename = Path(default_name)
        dest = outdir / filename
        counter = 1
        while dest.exists():
            dest = outdir / f"{filename.stem}_{counter}{filename.suffix}"
            counter += 1

        try:
            with dest.open("w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=headers)
                writer.writeheader()
                for row in records:
                    writer.writerow({header: row.get(header, "") for header in headers})
        except Exception as exc:
            QMessageBox.critical(self, title, f"Failed to export list:\n{exc}")
            self.dbf_status_label.setText("Export failed.")
            return

        self.dbf_status_label.setText(f"{title}: Exported 1 file.")
        QMessageBox.information(self, title, f"Exported file to:\n{dest}")

    def _update_theme_menu_checks(self) -> None:
        if not self.theme_action_group:
            return
        for action in self.theme_action_group.actions():
            action.setChecked(action.data() == self.current_theme)

    def apply_theme(self, theme: Optional[str] = None) -> None:
        app = QApplication.instance()
        if app is None:
            return
        if theme:
            self.current_theme = theme

        key = self.current_theme
        self._reset_palette()
        if key == "material_dark":
            apply_stylesheet(app, theme="dark_teal.xml")
        elif key == "qdark_dark":
            qdarktheme.setup_theme("dark")
        else:
            apply_stylesheet(app, theme="light_teal.xml")

        self._update_theme_menu_checks()

    def _reset_palette(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.setPalette(app.style().standardPalette())
        app.setStyleSheet("")

    def set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)

    def run_merge(self) -> None:
        inputdir = Path(self.input_edit.text())
        outdir = Path(self.output_edit.text())
        start_row = self.start_row_spin.value()

        if not inputdir.is_dir():
            QMessageBox.warning(self, "Invalid Input Directory", f"Input directory not found:\n{inputdir}")
            return

        self.append_log("Starting merge...")
        self._had_error = False
        self.set_running(True)
        self.status_label.setText("Running...")

        self.worker_thread = QThread(self)
        self.worker = MergeWorker(inputdir, outdir, start_row)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.message.connect(self.append_log)
        self.worker.errored.connect(self._handle_error)
        self.worker.finished.connect(self._merge_finished)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    @Slot()
    def _merge_finished(self) -> None:
        self.set_running(False)
        if self._had_error:
            self.append_log("Merge finished with errors.")
        else:
            self.status_label.setText("Completed.")
            self.append_log("Merge finished successfully.")
        self.refresh_file_list()
        self.worker = None
        self.worker_thread = None

    @Slot(str)
    def _handle_error(self, text: str) -> None:
        self._had_error = True
        self.append_log("ERROR:\n" + text)
        QMessageBox.critical(self, "Merge Error", text)
        self.status_label.setText("Error encountered.")


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
