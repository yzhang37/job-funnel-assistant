from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from job_search_assistant.runtime.config_files import ensure_config_file


class RuntimeConfigFileTests(unittest.TestCase):
    def test_missing_config_is_copied_from_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            template_dir = repo_root / "config_templates"
            template_dir.mkdir()
            (template_dir / "runtime.toml").write_text("version = 1\n", encoding="utf-8")

            target = ensure_config_file(repo_root, "config/runtime.toml")

            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "version = 1\n")


if __name__ == "__main__":
    unittest.main()
