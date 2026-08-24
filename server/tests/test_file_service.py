"""Tests for bounded CSV upload metadata extraction."""

import asyncio
import tempfile
import unittest
from pathlib import Path

from app.services.file_service import extract_metadata, inspect_csv


class FileServiceTests(unittest.TestCase):
    def test_inspect_csv_counts_rows_and_keeps_only_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.csv"
            path.write_text(
                "order_id,value\n"
                "o1,10\n"
                "o2,20\n"
                "o3,30\n"
                "o4,40\n",
                encoding="utf-8",
            )
            headers, row_count, preview = inspect_csv(str(path))

        self.assertEqual(headers, ["order_id", "value"])
        self.assertEqual(row_count, 4)
        self.assertEqual(len(preview), 4)
        self.assertEqual(preview[-1], ["o3", "30"])

    def test_extract_metadata_preserves_profile_and_row_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.csv"
            path.write_text("order_id,value\no1,10\no2,20\n", encoding="utf-8")
            metadata = asyncio.run(
                extract_metadata(str(path), "sample.csv", "temporary.csv")
            )

        self.assertEqual(metadata["rows"], 2)
        self.assertEqual(metadata["columns"], 2)
        self.assertEqual(metadata["profile"]["row_count"], 2)


if __name__ == "__main__":
    unittest.main()
