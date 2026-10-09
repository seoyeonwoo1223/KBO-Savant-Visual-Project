"""공식 프로필의 이름 대조와 결측 신장 배제를 검증한다."""
from collect_kbo_heights import parse_profile

def content(name,height):
    return f'<span id="x_playerProfile_lblName">{name}</span><span id="x_playerProfile_lblHeightWeight">{height}</span>'.encode()

def test_matching_profile():
    result=parse_profile(content('김선수','183cm/85kg'),{'player_name':'김선수'})
    assert result['status']=='ok' and result['height_cm']==183

def test_zero_or_missing_height_is_not_zero_measurement():
    for raw in ['0cm/0kg','', '999cm/85kg']:
        result=parse_profile(content('김선수',raw),{'player_name':'김선수'})
        assert result['height_cm'] is None and result['status']=='missing_profile_or_height'

def test_name_mismatch_remains_unverified():
    result=parse_profile(content('박선수','183cm/85kg'),{'player_name':'김선수'})
    assert result['status']=='name_mismatch' and result['height_cm'] is None
