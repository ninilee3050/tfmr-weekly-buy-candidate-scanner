from __future__ import annotations

from pathlib import Path

import pandas as pd


# Korean Excel re-saves CSV files as CP949 instead of UTF-8.
CSV_READ_ENCODINGS = ("utf-8-sig", "cp949")


def read_csv_flexible(path: Path | str, **kwargs) -> pd.DataFrame:
    """Read a CSV saved by this app (UTF-8) or re-saved by Korean Excel (CP949)."""
    last_error: UnicodeDecodeError | None = None
    for encoding in CSV_READ_ENCODINGS:
        try:
            return pd.read_csv(path, encoding=encoding, **kwargs)
        except UnicodeDecodeError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def describe_save_error(exc: OSError) -> str:
    """Explain a failed CSV write, e.g. a file locked because it is open in Excel."""
    # os.replace() reports the temporary file first and the real target second.
    filename = getattr(exc, "filename2", None) or getattr(exc, "filename", None)
    name = Path(str(filename)).name if filename else "결과"
    if name.endswith(".tmp"):
        name = name[: -len(".tmp")]
    if isinstance(exc, PermissionError):
        return (
            f"{name} 파일이 엑셀 등 다른 프로그램에서 열려 있어 저장하지 못했습니다. "
            "파일을 닫은 뒤 다시 시도해 주세요."
        )
    return f"{name} 파일 저장 실패: {exc}"
