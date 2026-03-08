import importlib
import json
import os
import shutil
import unittest
from pathlib import Path


_WORK_TMP_ROOT = Path("tests") / ".tmp"


def _prepare_case_dir(case_name: str) -> Path:
    case_dir = (_WORK_TMP_ROOT / case_name).resolve()
    shutil.rmtree(case_dir, ignore_errors=True)
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


class ConfigStoreTests(unittest.TestCase):
    def test_default_config_contains_rubin_and_wfst(self) -> None:
        case_dir = _prepare_case_dir("config_case_default")
        original_appdata = os.environ.get("APPDATA")
        os.environ["APPDATA"] = str(case_dir)
        try:
            module = importlib.import_module("rubin_clock.config_store")
            module = importlib.reload(module)

            config = module.load_config()
            site_ids = {site.id for site in config.sites}

            self.assertIn("rubin_cerro_pachon", site_ids)
            self.assertIn("wfst_lenghu", site_ids)
            self.assertEqual(config.selected_site_id, "rubin_cerro_pachon")
            self.assertEqual(config.language, "zh")
        finally:
            if original_appdata is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = original_appdata

    def test_existing_config_is_auto_backfilled_with_wfst(self) -> None:
        case_dir = _prepare_case_dir("config_case_backfill")
        original_appdata = os.environ.get("APPDATA")
        os.environ["APPDATA"] = str(case_dir)
        try:
            module = importlib.import_module("rubin_clock.config_store")
            module = importlib.reload(module)

            module.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "selected_site_id": "rubin_cerro_pachon",
                "language": "en",
                "sites": [
                    {
                        "id": "rubin_cerro_pachon",
                        "name": "Rubin (Cerro Pachon)",
                        "lat": -30.2446,
                        "lon": -70.7494,
                        "elevation_m": 2663.0,
                    }
                ],
            }
            module.CONFIG_PATH.write_text(json.dumps(payload), encoding="utf-8")

            config = module.load_config()
            site_ids = {site.id for site in config.sites}

            self.assertIn("rubin_cerro_pachon", site_ids)
            self.assertIn("wfst_lenghu", site_ids)
            self.assertEqual(config.language, "en")
        finally:
            if original_appdata is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = original_appdata


if __name__ == "__main__":
    unittest.main()
