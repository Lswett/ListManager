from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from listmanager.gui import MainWindow
from listmanager.template_export import TemplateExportResult


class FakeVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class FakeButton:
    def __init__(self) -> None:
        self.states: list[str] = []

    def configure(self, **kwargs) -> None:
        if "state" in kwargs:
            self.states.append(kwargs["state"])


def _window() -> MainWindow:
    window = object.__new__(MainWindow)
    window.template_converted_workbook = FakeVar()
    window.template_workbook = FakeVar()
    window.template_output = FakeVar()
    window.template_status = FakeVar()
    window.template_export_button = FakeButton()
    return window


class GuiTemplateExportTests(unittest.TestCase):
    def test_export_button_calls_backend_with_selected_paths(self) -> None:
        window = _window()
        window.template_converted_workbook.set("converted.xlsx")
        window.template_workbook.set("template.xlsx")
        window.template_output.set("output.xlsx")

        result = TemplateExportResult(
            converted_path=Path("converted.xlsx"),
            template_path=Path("template.xlsx"),
            output_path=Path("output.xlsx"),
            source_sheet="FULLNAME",
            target_sheet="FULLNAME",
            rows_exported=1,
        )
        success = Mock()
        window._template_export_succeeded = success

        def run_now(target, on_success, on_error, on_done):
            on_success(target())
            on_done()

        window._run_background = run_now

        with patch("listmanager.gui.export_to_template", return_value=result) as export_mock:
            window.run_template_export()

        export_mock.assert_called_once_with(Path("converted.xlsx"), Path("template.xlsx"), Path("output.xlsx"))
        success.assert_called_once_with(result)
        self.assertEqual(window.template_export_button.states, ["disabled", "normal"])

    def test_missing_converted_workbook_path_shows_validation_error(self) -> None:
        window = _window()
        window.template_workbook.set("template.xlsx")
        window.template_output.set("output.xlsx")

        with patch("listmanager.gui.messagebox.showerror") as showerror:
            window.run_template_export()

        showerror.assert_called_once_with("Export to Mailing Template", "Please select a converted workbook.")

    def test_missing_template_path_shows_validation_error(self) -> None:
        window = _window()
        window.template_converted_workbook.set("converted.xlsx")
        window.template_output.set("output.xlsx")

        with patch("listmanager.gui.messagebox.showerror") as showerror:
            window.run_template_export()

        showerror.assert_called_once_with(
            "Export to Mailing Template",
            "Please select the mailing list template workbook.",
        )

    def test_missing_output_path_shows_validation_error(self) -> None:
        window = _window()
        window.template_converted_workbook.set("converted.xlsx")
        window.template_workbook.set("template.xlsx")

        with patch("listmanager.gui.messagebox.showerror") as showerror:
            window.run_template_export()

        showerror.assert_called_once_with(
            "Export to Mailing Template",
            "Please choose where to save the template-ready workbook.",
        )

    def test_backend_exception_is_displayed_to_user(self) -> None:
        window = _window()
        window.template_converted_workbook.set("converted.xlsx")
        window.template_workbook.set("template.xlsx")
        window.template_output.set("output.xlsx")
        window._task_error = Mock()

        def fail_now(target, on_success, on_error, on_done):
            on_error("missing source sheet")
            on_done()

        window._run_background = fail_now
        window.run_template_export()

        window._task_error.assert_called_once_with(
            "Template Export Error",
            "missing source sheet",
            window.template_status,
        )

    def test_success_message_appears_after_export(self) -> None:
        window = _window()
        result = TemplateExportResult(
            converted_path=Path("converted.xlsx"),
            template_path=Path("template.xlsx"),
            output_path=Path("output.xlsx"),
            source_sheet="FULLNAME",
            target_sheet="FULLNAME",
            rows_exported=1,
        )

        with patch("listmanager.gui.messagebox.showinfo") as showinfo:
            window._template_export_succeeded(result)

        showinfo.assert_called_once()
        self.assertIn("Template-ready workbook created", window.template_status.get())


if __name__ == "__main__":
    unittest.main()
