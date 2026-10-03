from visualbaseball.pitch_types import pitch_code


def test_video_review_pitch_type_override():
    row = {
        "pitch_id": "20260708SKOB0-20260708SKOB0-037-01",
        "pitch_type_code": "FS",
        "pitch_type_kr": "포크",
    }
    assert pitch_code(row) == "FC"
