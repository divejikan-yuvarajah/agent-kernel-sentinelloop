"""QR catalog and poster generation. No live WhatsApp or model calls."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote, unquote

import pytest

from scripts.generate_location_qr import deep_link, generate_location_qrs, main
from tools.location_catalog import LocationConfigError, load_locations
from tools.qr_tags import format_loc_prefix, parse_loc_tag

ROOT = Path(__file__).resolve().parents[1]


def _write_yaml(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_demo_locations_yaml_is_valid():
    entries = load_locations(ROOT / "locations.yaml")
    ids = [row.qr_id for row in entries]
    assert len(entries) >= 3
    assert "SNT-LAB-B-M4-001" in ids
    assert "SNT-PROD-HP-01" in ids
    assert "SNT-CHEM-SA-01" in ids
    lab = next(row for row in entries if row.qr_id == "SNT-LAB-B-M4-001")
    assert lab.location == "Lab B"
    assert lab.equipment == "Machine 4"


def test_invalid_yaml_is_config_error(tmp_path):
    path = _write_yaml(tmp_path / "locations.yaml", "locations: [")
    with pytest.raises(LocationConfigError, match="invalid locations YAML"):
        load_locations(path)


def test_missing_locations_key(tmp_path):
    path = _write_yaml(tmp_path / "locations.yaml", "sites: []\n")
    with pytest.raises(LocationConfigError, match="top-level 'locations' list"):
        load_locations(path)


def test_duplicate_qr_ids(tmp_path):
    path = _write_yaml(
        tmp_path / "locations.yaml",
        """
locations:
  - location: "Lab B"
    equipment: "Machine 4"
    qr_id: "SNT-LAB-B-M4-001"
  - location: "Lab C"
    equipment: "Machine 5"
    qr_id: "SNT-LAB-B-M4-001"
""",
    )
    with pytest.raises(LocationConfigError, match="duplicate QR ID"):
        load_locations(path)


def test_missing_required_fields(tmp_path):
    path = _write_yaml(
        tmp_path / "locations.yaml",
        """
locations:
  - location: "Lab B"
""",
    )
    with pytest.raises(LocationConfigError, match="invalid"):
        load_locations(path)


def test_empty_equipment_rejected(tmp_path):
    path = _write_yaml(
        tmp_path / "locations.yaml",
        """
locations:
  - location: "Lab B"
    equipment: ""
""",
    )
    with pytest.raises(LocationConfigError):
        load_locations(path)


def test_versioned_qr_id_suffix(tmp_path):
    path = _write_yaml(
        tmp_path / "locations.yaml",
        """
locations:
  - location: "Lab B"
    equipment: "Machine 4"
    area_code: "LAB-B-M4"
    version: 2
""",
    )
    entries = load_locations(path)
    assert entries[0].qr_id == "SNT-LAB-B-M4-V2"


def test_parse_loc_tag_valid_and_invalid():
    parsed = parse_loc_tag("[LOC:Lab B|Machine 4] Oil leaking near machine")
    assert parsed.valid is True
    assert parsed.location == "Lab B"
    assert parsed.equipment == "Machine 4"
    assert parsed.human_text == "Oil leaking near machine"
    assert parsed.encoded_message == "[LOC:Lab B|Machine 4]"
    for text in ("[LOC:test]", "[LOC:Lab B]", "[LOC:]"):
        bad = parse_loc_tag(text)
        assert bad.present is True
        assert bad.valid is False
        assert bad.human_text == text


def test_format_loc_prefix_rejects_urls_and_scripts():
    with pytest.raises(ValueError):
        format_loc_prefix("https://evil.example", "Machine 4")
    with pytest.raises(ValueError):
        format_loc_prefix("Lab B", "<script>alert(1)</script>")
    with pytest.raises(ValueError):
        format_loc_prefix("Lab|B", "Machine 4")


def test_generate_writes_images_registry_and_payload(tmp_path):
    config = _write_yaml(
        tmp_path / "locations.yaml",
        """
locations:
  - location: "Lab B"
    equipment: "Machine 4"
    qr_id: "SNT-LAB-B-M4-001"
  - location: "Chemical Storage"
    equipment: "Storage Cabinet A"
    qr_id: "SNT-CHEM-SA-01"
""",
    )
    output = tmp_path / "qr"
    result = generate_location_qrs(
        config_path=config,
        output_dir=output,
        whatsapp_number="94770000000",
    )
    assert result["count"] == 2
    assert (output / "SNT-LAB-B-M4-001.png").is_file()
    assert (output / "posters" / "SNT-LAB-B-M4-001-poster.png").is_file()
    registry = json.loads((output / "location_registry.json").read_text(encoding="utf-8"))
    item = next(row for row in registry["items"] if row["qr_id"] == "SNT-LAB-B-M4-001")
    assert item["location"] == "Lab B"
    assert item["equipment"] == "Machine 4"
    assert item["encoded_message"] == "[LOC:Lab B|Machine 4]"
    assert "created" in item
    assert "qr_file_path" in item
    dumped = json.dumps(registry)
    assert "sk-" not in dumped
    assert "OPENROUTER" not in dumped
    url = deep_link("94770000000", item["encoded_message"])
    assert url.startswith("https://wa.me/94770000000?text=")
    assert unquote(url.split("text=", 1)[1]) == "[LOC:Lab B|Machine 4]"
    assert quote("[LOC:Lab B|Machine 4]") in url


def test_cli_invalid_yaml_returns_one(tmp_path, capsys):
    config = _write_yaml(tmp_path / "locations.yaml", "locations: [\n")
    code = main(["--config", str(config), "--output", str(tmp_path / "out"), "--whatsapp-number", "94770000000"])
    assert code == 1
    assert "QR generation failed" in capsys.readouterr().err
