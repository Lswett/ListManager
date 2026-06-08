from __future__ import annotations

import argparse
from pathlib import Path

from .converter import convert_many


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Convert messy mailing-list workbooks to ListManager format.")
    parser.add_argument("input", help="Input .xlsx/.xlsm file or folder")
    parser.add_argument("output_dir", help="Folder for converted workbooks")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = convert_many([Path(args.input)], output_dir)
    for result in results:
        output = result.output_path.name if result.output_path else ""
        print(
            f"{result.source_path.name}: {result.detected_format} | "
            f"rows={result.rows_scanned} converted={result.rows_converted} "
            f"review={result.rows_needing_review} warnings={result.warning_count} "
            f"errors={result.error_count} output={output}"
        )


if __name__ == "__main__":
    main()
