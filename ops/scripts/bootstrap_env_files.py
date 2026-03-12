#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _write_if_missing(target: Path, template: Path) -> None:
    if target.exists():
        print(f"exists: {target.name}")
        return
    target.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"created: {target.name}")


def main() -> int:
    template = ROOT / ".env.example"
    _write_if_missing(ROOT / ".env.local", template)
    _write_if_missing(ROOT / ".env.staging", template)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
