from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from listmanager.dedupe import DedupeResult
from listmanager.gui import MainWindow


class FakeVar:
    def __init__(self, value="") -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


class FakeButton:
    def __init__(self) -> None:
        self.states: list[str] = []

    def configure(self, **kwargs) -> None:
        if "state" in kwargs:
            self.states.append(kwargs["state"])


class FakeText:
    def __init__(self) -> None:
        self.value = ""
        self.state = ""

    def configure(self, **kwargs) -> None:
        self.state = kwargs.get("state", self.state)

    def delete(self, start, end) -> None:
        self.value = ""

    def insert(self, start, text) -> None:
        self.value = text


def _result() -> DedupeResult:
    return DedupeResult(
        input_path=Path("input.xlsx"),
        output_dir=Path("out"),
        data_sheet="FULLNAME",
        input_records=3,
        output_records=2,
        removed_duplicates=1,
        possible_duplicate_groups=1,
        possible_duplicate_records=2,
        deduped_output_path=Path("out/deduped_output.xlsx"),
        removed_duplicates_path=Path("out/removed_duplicates.xlsx"),
        possible_duplicates_path=Path("out/possible_duplicates_review.xlsx"),
        report_path=Path("out/duplicate_report.xlsx"),
    )


def _window() -> MainWindow:
    window = object.__new__(MainWindow)
    window.dedupe_input = FakeVar()
    window.dedupe_output_dir = FakeVar()
    window.dedupe_auto_remove_exact = FakeVar(True)
    window.dedupe_create_review = FakeVar(True)
    window.dedupe_status = FakeVar()
    window.dedupe_run_button = FakeButton()
    window.dedupe_summary = FakeText()
    return window


class GuiDedupeTests(unittest.TestCase):
    def test_dedupe_button_calls_backend_with_selected_paths_and_options(self) -> None:
        window = _window()
        window.dedupe_input.set("input.xlsx")
        window.dedupe_output_dir.set("out")
        success = Mock()
        window._dedupe_succeeded = success

        def run_now(target, on_success, on_error, on_done):
            on_success(target())
            on_done()

        window._run_background = run_now
        with patch("listmanager.gui.remove_duplicates", return_value=_result()) as dedupe_mock:
            window.run_dedupe()

        args = dedupe_mock.call_args.args
        self.assertEqual(args[0], Path("input.xlsx"))
        self.assertEqual(args[1], Path("out"))
        self.assertTrue(args[2].auto_remove_exact_individuals)
        self.assertTrue(args[2].create_possible_review)
        success.assert_called_once()
        self.assertEqual(window.dedupe_run_button.states, ["disabled", "normal"])

    def test_missing_input_path_shows_validation_error(self) -> None:
        window = _window()
        window.dedupe_output_dir.set("out")

        with patch("listmanager.gui.messagebox.showerror") as showerror:
            window.run_dedupe()

        showerror.assert_called_once_with(
            "Remove Duplicates",
            "Please select a cleaned/merged template-format workbook.",
        )

    def test_missing_output_folder_shows_validation_error(self) -> None:
        window = _window()
        window.dedupe_input.set("input.xlsx")

        with patch("listmanager.gui.messagebox.showerror") as showerror:
            window.run_dedupe()

        showerror.assert_called_once_with("Remove Duplicates", "Please choose an output folder.")

    def test_success_summary_is_displayed(self) -> None:
        window = _window()

        with patch("listmanager.gui.messagebox.showinfo") as showinfo:
            window._dedupe_succeeded(_result())

        self.assertIn("Input records: 3", window.dedupe_summary.value)
        self.assertIn("deduped_output.xlsx", window.dedupe_summary.value)
        self.assertIn("completed", window.dedupe_status.get())
        showinfo.assert_called_once()


if __name__ == "__main__":
    unittest.main()
