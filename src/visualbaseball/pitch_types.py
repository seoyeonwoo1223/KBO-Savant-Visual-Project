"""Pitch-type codes shared by every pitch-level metric."""
from __future__ import annotations


PITCH_CODES = ("FF", "FT", "SI", "FC", "SL", "ST", "CH", "CU", "FS")
PITCH_NAMES = {
    "FF": "포심", "FT": "투심", "SI": "싱커", "FC": "커터", "SL": "슬라이더",
    "ST": "스위퍼", "CH": "체인지업", "CU": "커브", "FS": "포크",
}
KOREAN_TO_CODE = {name: code for code, name in PITCH_NAMES.items()}
PITCH_TYPE_OVERRIDES = {
    # Confirmed by video review: 2026-07-08 SSG at Doosan, top 5th, Lee Ji-young PA, pitch 1.
    "20260708SKOB0-20260708SKOB0-037-01": "FC",
}


def pitch_code(row: dict) -> str:
    override = PITCH_TYPE_OVERRIDES.get(str(row.get("pitch_id") or "").strip())
    if override:
        return override
    code = str(row.get("pitch_type_code") or "").strip().upper()
    if code in PITCH_CODES:
        return code
    return KOREAN_TO_CODE.get(str(row.get("pitch_type_kr") or "").strip(), "")
