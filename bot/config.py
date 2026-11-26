"""Carga de config.yaml."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent


def load(path=None):
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
