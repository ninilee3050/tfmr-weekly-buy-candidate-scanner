from __future__ import annotations

import pandas as pd

from csv_io import describe_save_error, read_csv_flexible
from scenario_tracker import load_active_scenarios


def test_reads_csv_resaved_by_korean_excel(tmp_path) -> None:
    path = tmp_path / "excel.csv"
    pd.DataFrame([{"티커": "AAA", "현재상태": "보유 중"}]).to_csv(
        path, index=False, encoding="cp949"
    )

    loaded = read_csv_flexible(path)

    assert loaded.loc[0, "현재상태"] == "보유 중"


def test_reads_utf8_csv_written_by_app(tmp_path) -> None:
    path = tmp_path / "app.csv"
    pd.DataFrame([{"티커": "AAA", "결과": "매수 성공"}]).to_csv(
        path, index=False, encoding="utf-8-sig"
    )

    assert read_csv_flexible(path).columns.tolist() == ["티커", "결과"]


def test_active_state_loads_after_excel_resave(tmp_path) -> None:
    path = tmp_path / "active.csv"
    pd.DataFrame(
        [{"티커": "AAA", "현재상태": "보유 중", "1차매수일": "2024-01-08"}]
    ).to_csv(path, index=False, encoding="cp949")

    loaded = load_active_scenarios(path)

    assert loaded.loc[0, "현재상태"] == "보유 중"
    assert loaded.loc[0, "1차매수일"] == pd.Timestamp("2024-01-08")


def test_locked_file_message_names_target_not_temp_file() -> None:
    exc = PermissionError(13, "Access is denied", "outputs/active.csv.tmp", None, "outputs/active.csv")

    message = describe_save_error(exc)

    assert message.startswith("active.csv 파일이 엑셀 등 다른 프로그램에서 열려 있어")


def test_other_save_errors_are_described() -> None:
    message = describe_save_error(OSError(28, "No space left", "outputs/x.csv"))

    assert message.startswith("x.csv 파일 저장 실패")
