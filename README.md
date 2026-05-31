# TFMR 주봉 1회차 매수후보 탐지 도구

TFMR 전략(Trend Following·Mean Reversion)의 주봉 1회차 매수후보 조건을 과거 확정 주봉과 이번 주 진행 중인 주봉에서 탐지하는 Python Tkinter 스캐너입니다.

TFMR 1회차 매수후보 탐지 규칙을 Python 코드가 정확히 이해했는지 확인하기 위한 검증용 GUI 프로그램입니다.

이 프로젝트는 자동매매 프로그램이 아닙니다. 주문 실행, 브로커 API 연동, 계좌 연결, 수익률 계산, 보유 상태 추적, 추가매수, 매도 판단은 v1 범위에 포함하지 않습니다.

이 도구는 매매 추천이나 수익 보장을 목적으로 하지 않습니다. 사용자가 정의한 TFMR 매매 시나리오 조건이 주봉 데이터에서 언제 포착되는지 확인하기 위한 탐지용 도구입니다.

## 현재 목적

이 프로그램의 v1 목표는 단 하나입니다.

`TFMR 1회차 매수후보 조건을 주봉 데이터에서 정확히 찾아낸다.`

기존 표현으로는 아래 목표와 같습니다.

`TFMR 1회차 매수 기준봉 조건을 주봉 데이터에서 정확히 찾아내는지 검증한다.`

주요 사용 방식은 두 가지입니다.

* 개별 티커 검색: 과거 확정 주봉에서 TFMR 1회차 매수후보가 언제 나왔는지 확인
* Top100 이번주 스캐너: 미국 시가총액 상위 종목 중 이번 주에 새 1회차 매수후보가 생겼는지 확인

이 README에서는 전략 조건에 맞는 지점을 `매수후보`라고 부릅니다.

다만 기존 코드와 CSV 파일명에는 구현 이력상 `buy_points`, `매수포인트`, `매수 기준봉`, `기준봉` 표현이 일부 남아 있을 수 있습니다. 이 표현들은 확정 수익 지점이 아니라, TFMR 시나리오 조건에 맞는 후보 지점을 의미합니다.

## 실행 방법

Windows에서 `실행하기.bat`을 더블클릭하면 GUI가 실행됩니다.

처음 실행 전 Python 패키지가 없다면 아래 명령으로 설치합니다.

```powershell
cd C:\Users\user\Documents\Codex\tfmr-weekly-buy-candidate-scanner
pip install -r requirements.txt
```

직접 GUI를 실행하려면 아래처럼 실행할 수도 있습니다.

```powershell
python app.py
```

명령형 Top100 스캔은 GUI 없이 아래처럼 실행할 수 있습니다.

```powershell
python weekly_scan.py --limit 100 --output-dir outputs
```

GitHub Actions 같은 자동실행 환경에서는 GUI 창을 띄우는 `app.py` 대신 `weekly_scan.py`를 사용합니다.

## 화면 구조

Tkinter 기본 스타일의 3단 구조입니다.

* 왼쪽: 미국 시가총액 Top100 목록
* 중앙: 티커 검색창과 과거 1회차 매수후보 표
* 오른쪽: Top100 이번주 매수후보 스캐너

왼쪽 Top100 표에서 종목을 클릭하면 중앙 검색창에 티커가 자동 입력되고 바로 검색됩니다.

현재 UI에서는 전체 계산표 탭을 보여주지 않습니다. 사용자는 매수후보만 보고 싶다고 했기 때문에 화면을 단순하게 유지합니다.

기존 코드나 컬럼명에는 `매수 기준봉`, `매수포인트`, `buy_points` 표현이 남아 있을 수 있습니다. 이 README에서는 해당 결과를 TFMR 조건이 포착된 `매수후보`로 해석합니다.

## 중앙 검색과 오른쪽 스캐너의 차이

중앙 티커 검색은 과거 확정 주봉 확인용입니다.

* `load_weekly_data(..., include_current_week=False, force_refresh=True)`를 사용합니다.
* 검색할 때마다 Yahoo 계열 일봉 데이터를 새로 받아 `data/{TICKER}.csv`를 갱신합니다.
* 진행 중인 이번 주 주봉은 제외합니다.
* 과거 확정 주봉에서 TFMR 1회차 매수후보가 언제 나왔는지 확인합니다.
* 결과는 `outputs/{TICKER}_tfmr_buy_points.csv`에 저장합니다.

오른쪽 Top100 스캐너는 이번 주 후보 확인용입니다.

* `include_current_week=True`를 사용합니다.
* 진행 중인 이번 주 주봉을 포함합니다.
* 미국 시가총액 Top100 종목 중 이번 주에 새 1회차 매수후보가 생겼는지 확인합니다.
* 결과는 확정 매수지점이 아니라 `이번주 매수후보`입니다.
* 금요일 종가 전에 조건이 바뀔 수 있습니다.
* 스캔 결과는 자동 저장하지 않습니다.
* 사용자가 `스캔 저장하기` 버튼을 눌렀을 때만 다운로드 폴더에 저장합니다.

저장 파일명:

```text
Downloads/top100_tfmr_candidates_YYYY-MM-DD.csv
Downloads/top100_tfmr_failures_YYYY-MM-DD.csv
```

## 데이터 기준

* 가격 데이터는 Yahoo 계열 일봉 데이터를 사용합니다.
* Yahoo의 `1wk` 주봉을 그대로 쓰지 않습니다.
* 일봉 데이터를 직접 월요일 시작 기준 주봉으로 묶습니다.
* 주봉 날짜는 해당 주봉의 시작일, 즉 월요일 날짜입니다.
* 가격 기준은 `Close`입니다.
* MA5, MA20, MA50, MA150, MA200은 모두 주봉 `Close` 기준 SMA입니다.
* EMA는 사용하지 않습니다.
* 거래량은 v1 매수후보 조건에 포함하지 않습니다.
* MA150과 MA200이 계산되지 않는 종목은 TFMR 검사 대상에서 제외됩니다.
* 개별 티커 검색은 진행 중인 이번 주 주봉을 제외합니다.
* Top100 이번주 스캐너와 `weekly_scan.py`는 진행 중인 이번 주 주봉까지 포함합니다.

주봉 OHLCV는 아래 기준으로 만듭니다.

* Open: 해당 주 첫 거래일 시가
* High: 해당 주 최고가
* Low: 해당 주 최저가
* Close: 해당 주 마지막 거래일 종가
* Volume: 해당 주 거래량 합계
* Adj Close: 해당 주 마지막 거래일 수정종가

`data/{TICKER}.csv` 파일은 다음 실행을 빠르게 하기 위한 캐시입니다. 사용자가 직접 CSV를 준비하지 않아도 됩니다.

기존에 저장된 캐시가 월요일 라벨 주봉이 아니면 예전 방식 캐시로 보고 무시한 뒤 새로 다운로드합니다.

이 방식은 Investing.com 주봉 화면과 최대한 맞추기 위한 선택입니다. 다만 Yahoo와 Investing.com의 원천 데이터, 배당/분할 보정, 지표 계산식이 다르면 완전히 100% 같지 않을 수 있습니다.

## Top100 목록 기준

Top100 목록은 `StockAnalysis`의 시가총액 순위 페이지를 실시간으로 조회합니다.

```text
https://stockanalysis.com/list/biggest-companies/
```

중요한 결정:

* 내장 fallback Top100 목록은 사용하지 않습니다.
* 실시간 조회에 실패하면 목록을 비워두고 오류를 보여줍니다.
* `weekly_scan.py`도 Top100 실시간 조회 실패 시 기본 목록으로 대체하지 않고 실패합니다.
* 이 구현은 기존 완성본 레포 `ninilee3050/weekly-buy-point-scanner`의 Top100 방식과 맞춘 것입니다.
* 현재 새 구조에서는 MMRM 레포 `ninilee3050/mmrm-weekly-buy-candidate-scanner`와도 같은 Top100 운용 기준을 공유합니다.

주의:

* 이전에는 `CompaniesMarketCap` 기반 파서를 시도했지만, 사이트 표 구조 변경과 Windows HTTPS 문제 때문에 실패했습니다.
* GUI에서 PowerShell/curl을 subprocess로 호출하는 우회도 시도했지만 CMD 창이 순간적으로 뜨는 부작용이 있어 제거했습니다.
* 현재는 참고 레포와 같은 `urllib.request + StockAnalysis HTML table parser` 방식입니다.

## 기준 시나리오

TFMR v1에서 1회차 매수후보는 아래 흐름을 모두 만족하는 첫 음봉 주봉입니다.

기존 표현으로는 `1회차 매수 기준봉`이며, 이 README에서는 확정 수익 지점이 아니라 전략 조건에 맞는 `1회차 매수후보`로 표현합니다.

1. MA20이 MA50을 골든크로스해서 상승 사이클이 시작되어야 합니다.
2. 골든크로스는 `이전 주 MA20 <= 이전 주 MA50` 그리고 `현재 주 MA20 > 현재 주 MA50`입니다.
3. 상승 사이클 종료는 `이전 주 MA20 >= 이전 주 MA50` 그리고 `현재 주 MA20 < 현재 주 MA50`입니다.
4. 상승 사이클이 시작된 뒤 `Close > MA20`인 주봉 이력이 한 번 이상 있어야 합니다.
5. 이후 `Close < MA5` 그리고 `Close < MA20`인 눌림 상태가 발생해야 합니다.
6. 그 눌림 안에서 첫 번째 음봉이 나오면 그 주봉을 1회차 매수후보로 기록합니다.
7. 음봉 기준은 `Close < Open`입니다.
8. 눌림 상태가 먼저 발생했더라도 그 주가 양봉이면 기록하지 않고 관찰을 유지합니다.
9. 같은 눌림 안에서 이후 첫 음봉이 나오면 그 주봉을 기록합니다.
10. 음봉이 나오기 전에 `Close > MA20`으로 회복하면 해당 눌림은 무효 처리합니다.
11. `MA150 > MA200`이어야 합니다.
12. 같은 상승 사이클에서 이미 1회차 매수후보가 기록됐으면 이후 눌림은 v1에서 무시합니다.
13. 새 1회차 후보를 다시 찾으려면 상승 사이클 종료 후 새 골든크로스가 다시 나와야 합니다.

모든 비교는 엄격 비교입니다. 같은 값은 조건 만족으로 보지 않습니다.

예:

* `Close = MA20`이면 `Close > MA20`도 아니고 `Close < MA20`도 아닙니다.
* `Close = Open`이면 음봉이 아닙니다.
* `MA150 = MA200`이면 장기추세 정배열이 아닙니다.

ConditionSummary 문구:

```text
1회차 매수후보: MA20>MA50 상승사이클 + Close>MA20 이력 + Close<MA5/MA20 + 음봉 + MA150>MA200
```

기존 코드나 CSV에 남아 있는 표현과 맞춰야 할 경우 아래 기존 문구도 같은 의미로 해석합니다.

```text
1회차 기준봉: MA20>MA50 상승사이클 + Close>MA20 이력 + Close<MA5/MA20 + 음봉 + MA150>MA200
```

## 출력 파일

개별 티커 검색 결과는 `outputs/` 폴더에 저장됩니다.

```text
outputs/{TICKER}_tfmr_buy_points.csv
```

Top100 스캐너 결과는 `스캔 저장하기` 버튼을 눌렀을 때 사용자 다운로드 폴더에 저장됩니다.

```text
Downloads/top100_tfmr_candidates_YYYY-MM-DD.csv
Downloads/top100_tfmr_failures_YYYY-MM-DD.csv
```

`weekly_scan.py`로 화면 없이 자동 스캔을 실행하면 아래 파일이 프로젝트 `outputs/` 폴더에 저장됩니다.

```text
outputs/top100_tfmr_candidates_YYYY-MM-DD.csv
outputs/top100_tfmr_failures_YYYY-MM-DD.csv
```

CSV는 Excel에서 한글이 잘 보이도록 `utf-8-sig`로 저장합니다.

## 파일 구조와 역할

```text
README.md
requirements.txt
app.py
data_provider.py
market_cap_provider.py
tfmr_scanner.py
weekly_scan.py
data/
outputs/
tests/
실행하기.bat
```

각 파일 역할:

* `app.py`: Tkinter GUI. 3단 화면, 티커 검색, Top100 목록, Top100 스캔, CSV 저장 UI를 담당합니다.
* `data_provider.py`: Yahoo 계열 일봉 데이터를 받아 월요일 시작 주봉으로 변환합니다. 중앙 검색과 스캐너의 이번 주 포함 여부도 여기서 처리합니다.
* `market_cap_provider.py`: StockAnalysis 실시간 Top100 표를 파싱합니다. fallback 목록을 두지 않습니다.
* `tfmr_scanner.py`: TFMR v1 핵심 판정 로직입니다. 가장 중요한 파일입니다.
* `weekly_scan.py`: GUI 없이 Top100 이번주 후보 스캔을 실행하는 명령형 파일입니다.
* `tests/`: pytest 테스트입니다. TFMR 상태 추적과 데이터 처리 차이를 검증합니다.
* `data/`: 내려받은 티커별 주봉 캐시 CSV가 생깁니다. `.gitignore`로 실제 CSV는 제외됩니다.
* `outputs/`: 개별 티커 검색 결과 CSV가 생깁니다. `.gitignore`로 실제 CSV는 제외됩니다.
* `실행하기.bat`: Windows 더블클릭 실행용 파일입니다.

GitHub에 올리지 않는 파일:

```text
__pycache__/
*.pyc
.pytest_cache/
data/*.csv
outputs/*.csv
```

`data/.gitkeep`와 `outputs/.gitkeep`는 빈 폴더를 GitHub에 유지하기 위한 파일입니다.

## 중요한 구현 메모

다음 세션에서 이어 작업할 때 특히 아래를 먼저 확인하세요.

* TFMR 조건을 바꾸는 작업이 아니라면 `tfmr_scanner.py`의 핵심 상태 추적 로직은 건드리지 않는 것이 좋습니다.
* 중앙 검색은 최신 확정 주봉 누락을 막기 위해 반드시 `force_refresh=True`를 유지해야 합니다.
* 중앙 검색은 `include_current_week=False`를 유지해야 합니다.
* 오른쪽 스캐너는 `include_current_week=True`를 유지해야 합니다.
* Top100은 실시간 조회 실패 시 fallback을 쓰지 않는 것이 현재 확정 기준입니다.
* `data/*.csv`, `outputs/*.csv`, `__pycache__/`, `.pytest_cache/`는 GitHub에 올리지 않습니다.
* UI는 전체화면 강제 실행이 아니라 기본 창 크기와 패널 minsize로 컬럼이 보이도록 조정되어 있습니다.
* 기존 코드나 출력 파일명에 `buy_points`, `매수포인트`, `기준봉` 표현이 남아 있더라도 README에서는 이를 `매수후보`로 해석합니다.
* 사용자가 “세이브포인트”라고 말하면 Git 커밋을 의미합니다.
* 사용자가 “푸시”라고 말하면 로컬 커밋을 GitHub에 업로드하는 것을 의미합니다.

## UI 크기 관련 메모

표 컬럼이 잘리지 않도록 `app.py`에서 기본 창과 컬럼 폭을 넓혀둔 상태입니다.

* 기본 창 크기: `2920x900`
* 최소 창 크기: `2200x720`
* 왼쪽 패널 minsize: `470`
* 중앙 패널 minsize: `1120`
* 오른쪽 패널 minsize: `1280`

컬럼 폭은 `_column_width()`에서 관리합니다.

UI 관련 수정이 필요하면 `app.py`의 `_build_layout()`, `_create_top100_table()`, `_column_width()`를 먼저 확인하세요.

## 테스트

테스트 실행:

```powershell
pytest
```

또는 pytest가 PATH에 없다면:

```powershell
python -m pytest
```

현재 테스트가 검증하는 주요 내용:

* MA20/MA50 골든크로스 계산
* 상승 사이클 종료 계산
* Close > MA20 이력이 없으면 후보가 나오지 않는 것
* 눌림 상태가 양봉이면 기록하지 않는 것
* 같은 눌림 안에서 이후 첫 음봉이 나오면 기록하는 것
* 음봉 전 Close > MA20 회복 시 눌림 관찰이 리셋되는 것
* MA150 > MA200 조건
* 같은 상승 사이클에서는 첫 번째 후보만 기록하는 것
* 상승 사이클 종료 후 새 골든크로스가 나오면 새 후보를 다시 찾는 것
* 중앙 검색은 진행 중인 이번 주를 제외하고, 오른쪽 스캐너는 포함하는 것
* Top100 실시간 조회 실패 시 fallback을 반환하지 않는 것
* 중앙 검색 호출 경로가 `force_refresh=True`를 사용하는 것
* StockAnalysis Top100 표 파싱

## GitHub Actions 자동 스캔

이 레포에는 `.github/workflows/weekly-scan.yml` 워크플로가 있습니다.

동작 방식:

* 수동 실행: GitHub 레포의 `Actions` 탭에서 `TFMR Top 100 Weekly Candidate Scan` 워크플로를 선택한 뒤 `Run workflow`를 누릅니다.
* 자동 실행: 워크플로 파일에 설정된 cron 시간에 실행됩니다.
* 실행 명령: `python weekly_scan.py --limit 100 --output-dir outputs`
* 저장 방식: 결과 CSV를 레포에 커밋하지 않고, GitHub Actions artifact로 업로드합니다.
* artifact 이름: `tfmr-top100-scan-results`
* 보관 기간: 30일

업로드되는 파일:

```text
outputs/top100_tfmr_candidates_YYYY-MM-DD.csv
outputs/top100_tfmr_failures_YYYY-MM-DD.csv
```

주의:

* GitHub Actions의 cron은 UTC 기준입니다.
* 스캔 결과 CSV는 GitHub 저장소 파일 목록에 자동 커밋되지 않습니다.
* 결과는 해당 Actions 실행 화면의 `Artifacts` 영역에서 다운로드합니다.
* GitHub 로그인 없이 Actions artifact를 직접 다운로드하기는 어렵습니다.
* Top100 목록 조회나 Yahoo 데이터 다운로드가 실패해도 failures CSV가 artifact에 같이 올라가도록 `if: always()`를 사용합니다.

## v1에서 의도적으로 제외한 기능

아래 기능은 TFMR 전체 전략에는 필요할 수 있지만 v1에서는 구현하지 않습니다.

* N번째 눌림 탐지
* 추가매수 차수 계산
* 매도 날짜 계산
* 수익률 계산
* 보유 상태 추적
* 자금 배분 계산
* 브로커 주문 연동
* 자동매매 실행
* 백테스팅

향후 v2에서는 1회차 매수후보 탐지가 충분히 안정화된 뒤 추가매수와 매도 흐름 계산을 확장할 수 있습니다.

기존 표현으로는 아래와 같은 의미입니다.

`향후 v2에서는 1회차 기준봉 탐지가 충분히 안정화된 뒤 추가매수와 매도 흐름 계산을 확장할 수 있습니다.`

## 문제 해결

Top100 목록이 안 불러와질 때:

* 인터넷 연결을 확인합니다.
* `https://stockanalysis.com/list/biggest-companies/` 접속이 가능한지 확인합니다.
* `market_cap_provider.py`의 `parse_stockanalysis_market_cap_table()` 테스트를 확인합니다.
* 참고 레포 `ninilee3050/weekly-buy-point-scanner`의 `market_cap_provider.py`와 비교하면 됩니다.
* 새 구조에서는 MMRM 레포 `ninilee3050/mmrm-weekly-buy-candidate-scanner`의 `market_cap_provider.py`도 참고할 수 있습니다.

티커 검색이 실패할 때:

* Yahoo 계열 데이터 다운로드가 막혔는지 확인합니다.
* 티커가 Yahoo에서 쓰는 형식인지 확인합니다.
* 예: `BRK.B` 같은 티커는 Yahoo에서 `BRK-B` 형태가 필요할 수 있습니다.

pytest가 없을 때:

```powershell
pip install -r requirements.txt
python -m pytest
```

## GitHub 업로드 메모

현재 GitHub 레포:

```text
https://github.com/ninilee3050/tfmr-weekly-buy-candidate-scanner
```

레포 이름:

```text
tfmr-weekly-buy-candidate-scanner
```

초기 업로드 커밋:

```text
f80b4f3 Initial TFMR buy base scanner
```

초기 커밋 메시지에는 이전 명칭인 `buy base` 표현이 남아 있을 수 있습니다. 현재 README와 레포 이름에서는 `buy candidate` 표현을 사용합니다.

Codex 샌드박스에서 `git init`을 한 뒤 Windows 사용자로 Git을 실행하면 dubious ownership 경고가 날 수 있습니다. 이 경우 사용자가 아래 명령을 한 번 실행했습니다.

```powershell
git config --global --add safe.directory C:/Users/user/Documents/Codex/tfmr-weekly-buy-candidate-scanner
```

레포 이름 변경 전 경로를 기준으로는 아래 명령을 사용한 이력이 있을 수 있습니다.

```powershell
git config --global --add safe.directory C:/Users/user/Documents/Codex/tfmr-buy-base-scanner
```

사용자가 혼자 쓰는 프로젝트라 현재는 `main` 브랜치에 직접 커밋하고 푸시하는 흐름을 사용합니다.

## 다음 세션 시작 체크리스트

다른 Codex 세션에서 이어 작업한다면 먼저 아래 순서로 확인하면 됩니다.

1. `git status -sb`로 작업 트리 상태 확인
2. `README.md`의 이 섹션을 읽고 현재 설계 기준 확인
3. Top100 관련이면 `market_cap_provider.py`와 참고 레포의 동일 파일 비교
4. TFMR 판정 관련이면 `tfmr_scanner.py`와 `tests/test_tfmr_scanner.py` 먼저 확인
5. UI 관련이면 `app.py`의 `_build_layout()`, `_create_top100_table()`, `_column_width()` 확인
6. 데이터 포함/제외 관련이면 `data_provider.py`의 `include_current_week` 흐름 확인
7. GitHub Actions 관련이면 `.github/workflows/weekly-scan.yml`의 cron, 실행 명령, artifact 설정 확인
8. 변경 후 가능하면 `pytest` 실행

## 다음 작업 시 특히 유지할 기준

* 이 프로그램은 TFMR 주봉 1회차 매수후보 탐지를 목표로 합니다.
* 자동매매, 추천, 수익 보장 도구가 아닙니다.
* Yahoo `1wk` 원본 주봉은 그대로 쓰지 않습니다.
* Yahoo 일봉 데이터를 받아 월요일 시작 주봉으로 직접 재구성합니다.
* 중앙 검색은 과거 확정 주봉 기준입니다.
* 중앙 검색은 `include_current_week=False`를 유지합니다.
* 중앙 검색은 최신 확정 주봉 누락 방지를 위해 `force_refresh=True`를 유지합니다.
* Top100 스캐너는 이번 주 진행 중인 주봉까지 포함합니다.
* Top100 스캐너는 `include_current_week=True`를 유지합니다.
* Top100 목록은 StockAnalysis에서 실시간 조회합니다.
* Top100 조회 실패 시 fallback 목록을 쓰지 않습니다.
* TFMR 조건의 엄격 비교 기준을 유지합니다.
* MA150과 MA200이 계산되지 않는 종목은 TFMR 검사 대상에서 제외합니다.
* 1회차 후보 탐지가 안정화되기 전에는 추가매수, 매도, 수익률 계산, 자동매매 기능을 섞지 않습니다.
