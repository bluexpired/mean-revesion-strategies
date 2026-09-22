# Residual Reversal

시장·업종으로 설명되지 않는 최근 종목 하락을 찾는 가격 기반 연구 코드입니다.
2026-09-22에 `quantresearcherbeginner`의 mr-v2 구현에서 분리했습니다.
기존 저장소의 페어 트레이딩 파일과 독립적으로 실행합니다.

## 계산

1. 종목·시장 ETF·업종 ETF의 완료된 거래일을 정렬합니다.
2. 최근 3거래일을 제외한 직전 60개 로그수익률로 절편이 있는 2요인 OLS를 추정합니다.
3. 고정된 계수로 최근 3일의 잔차를 계산하고 합산합니다.
4. 학습 구간의 겹치는 3일 잔차 합의 평균과 표준편차로 z를 계산합니다.
5. 기본값 z ≤ -2이면 `REVIEW_CANDIDATE`, 조건 미달이면 `NO_SIGNAL`입니다.
   거래일 누락·업종 ETF 부재·요인 공선성 등은 `DATA_BLOCKED`로 처리합니다.

이 z는 이탈 척도이며 수익확률이나 통계적 유의확률이 아닙니다.
매수 방향 스크리너이며 OU·공적분·시장중립 헤지·수익성 백테스트·주문 실행은 구현하지 않습니다.
RSI와 가격 밴드는 비교용입니다. 뉴스는 잔차 계산에 사용하지 않습니다.

## 실행

Python 3.10 이상에서 저장소의 `residual_reversal` 폴더로 이동합니다.

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python mean_reversion_analysis.py --snapshot "C:/path/to/snapshot.json"
```

기존 연구 프로그램이 수집한 snapshot을 입력합니다. 이 폴더는 데이터 수집기를 포함하지 않습니다.
입력 JSON에는 `mode`, 시간대가 포함된 `cutoff`, `config`, `bars`가 필요합니다.
`bars`는 심볼별 일봉 목록이며 각 봉에 `t`, `o`, `h`, `l`, `c`가 필요하고 `v`는 선택입니다.
`config.json`은 설정 예시이며 실행 시에는 **snapshot 안의 config**를 사용합니다.
종목과 SPY 및 지정 업종 ETF에 최소 64개 연속 완료 거래일의 가격이 필요합니다.
최근 완료 거래일 판정에는 거래소 휴일·조기 폐장과 15분의 여유를 반영합니다.

결과는 입력 snapshot과 같은 폴더의 `mr-v2/mean_reversion.json` 및
`mr-v2/mean_reversion.md`에 저장되며 같은 입력 폴더로 재실행하면 덮어씁니다.
실제 데이터·보고서·API 키는 저장소에 포함하지 않습니다.

## 원본과의 관계

분석 본체와 공통 유틸리티는 원본 코드 그대로입니다. 거래일 모듈은 뉴스 모듈에 있던
동일한 달력 함수를 별도 `research/calendar.py`로 옮겨 뉴스 의존성을 분리했습니다.
기존 테스트 중 통합 프로그램 전용 테스트 2개는 제외했고, 합성 데이터 날짜는 실제
거래소 거래일로 정렬했습니다. `pairs.min_price` 설정은 기존 코드가 참조하는 가격 필터의
호환 키이며 페어 분석을 실행하는 것은 아닙니다.

원본 프로젝트를 수정한다고 이 복사본이 자동 갱신되지는 않습니다.
이 저장소의 Residual Reversal 변경은 아래처럼 기록합니다.

```powershell
# 저장소 최상위 폴더에서
git diff -- residual_reversal
git add residual_reversal
git commit -m "Describe the Residual Reversal change"
git push origin main
```

작업 단위로 검증 후 커밋합니다. 파일 저장만으로 자동 커밋되지는 않습니다.
