from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .astro_core import Site


CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "RubinSolarClock"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_SITE = Site(
    id="rubin_cerro_pachon",
    name="Rubin (Cerro Pachon)",
    lat=-30.2446,
    lon=-70.7494,
    elevation_m=2663.0,
)

WFST_SITE = Site(
    id="wfst_lenghu",
    name="WFST (Lenghu)",
    lat=38.6068,
    lon=93.8961,
    elevation_m=4200.0,
)

BUILTIN_SITES = [DEFAULT_SITE, WFST_SITE]


@dataclass
class AppConfig:
    selected_site_id: str
    sites: list[Site]

    def selected_site(self) -> Site:
        for site in self.sites:
            if site.id == self.selected_site_id:
                return site
        return self.sites[0]


def create_site_id(name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower())
    normalized = normalized.strip("_")
    return normalized or "site"


def ensure_unique_site_id(config: AppConfig, preferred_id: str) -> str:
    existing = {site.id for site in config.sites}
    if preferred_id not in existing:
        return preferred_id

    suffix = 2
    while f"{preferred_id}_{suffix}" in existing:
        suffix += 1
    return f"{preferred_id}_{suffix}"


def _site_from_raw(raw: dict) -> Site:
    return Site(
        id=str(raw["id"]),
        name=str(raw["name"]),
        lat=float(raw["lat"]),
        lon=float(raw["lon"]),
        elevation_m=float(raw.get("elevation_m", 0.0)),
    )


def _site_to_raw(site: Site) -> dict:
    return {
        "id": site.id,
        "name": site.name,
        "lat": site.lat,
        "lon": site.lon,
        "elevation_m": site.elevation_m,
    }


def _with_builtin_sites(sites: list[Site]) -> list[Site]:
    by_id = {site.id: site for site in sites}
    merged = list(sites)
    for builtin in BUILTIN_SITES:
        if builtin.id not in by_id:
            merged.append(builtin)
    return merged


def _default_config() -> AppConfig:
    return AppConfig(selected_site_id=DEFAULT_SITE.id, sites=list(BUILTIN_SITES))


def save_config(config: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "selected_site_id": config.selected_site_id,
        "sites": [_site_to_raw(site) for site in config.sites],
    }
    CONFIG_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        config = _default_config()
        save_config(config)
        return config

    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        sites = [_site_from_raw(item) for item in raw.get("sites", [])]
        if not sites:
            sites = [DEFAULT_SITE]

        sites = _with_builtin_sites(sites)
        ids = {site.id for site in sites}

        selected = str(raw.get("selected_site_id", DEFAULT_SITE.id))
        if selected not in ids:
            selected = DEFAULT_SITE.id

        config = AppConfig(selected_site_id=selected, sites=sites)
        save_config(config)
        return config
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        backup_path = CONFIG_PATH.with_suffix(".corrupt.json")
        try:
            CONFIG_PATH.replace(backup_path)
        except OSError:
            pass

        config = _default_config()
        save_config(config)
        return config


def upsert_site(config: AppConfig, site: Site, select_after_insert: bool = False) -> AppConfig:
    replaced = False
    new_sites: list[Site] = []
    for existing in config.sites:
        if existing.id == site.id:
            new_sites.append(site)
            replaced = True
        else:
            new_sites.append(existing)

    if not replaced:
        new_sites.append(site)

    selected_site_id = site.id if select_after_insert else config.selected_site_id
    if selected_site_id not in {s.id for s in new_sites}:
        selected_site_id = DEFAULT_SITE.id if DEFAULT_SITE.id in {s.id for s in new_sites} else new_sites[0].id

    updated = AppConfig(selected_site_id=selected_site_id, sites=new_sites)
    save_config(updated)
    return updated


def set_selected_site(config: AppConfig, site_id: str) -> AppConfig:
    if site_id not in {site.id for site in config.sites}:
        return config

    updated = AppConfig(selected_site_id=site_id, sites=config.sites)
    save_config(updated)
    return updated


__all__ = [
    "CONFIG_PATH",
    "DEFAULT_SITE",
    "WFST_SITE",
    "BUILTIN_SITES",
    "AppConfig",
    "create_site_id",
    "ensure_unique_site_id",
    "load_config",
    "save_config",
    "set_selected_site",
    "upsert_site",
]
