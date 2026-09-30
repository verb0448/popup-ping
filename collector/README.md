# 🤖 팝업 자동 수집기

매주 월요일 오전 9시(KST)에 팝가(popga.co.kr)에서 서울 팝업을 모아 구글 시트를 갱신해요.

## 어떤 걸 남기나요? (실행일 기준)
| 구분 | 조건 | 결과 |
|---|---|---|
| 진행중 | 오늘이 기간 안 | 보관 |
| 오픈 예정 | 시작일이 **다음 달 말일**까지 | 보관 |
| 종료 | **시작일이 지난달**인 것만 | 보관 (앱에서 "종료"로 표시) |
| 그 외 | 오래된 종료 건 / 먼 미래 예정 건 | 시트에서 삭제 |

- 시트에 손으로 넣은 행도 같은 규칙으로 정리돼요. (같은 `참고_링크`면 수집본이 덮어써요)
- 공연·콘서트·연극 등 팝업이 아닌 카테고리는 제외해요. (`EXCLUDE_CATEGORIES`)
- 좌표는 팝가 상세 페이지에 들어 있어서 지오코딩 API가 필요 없어요.

## 🙋 직접 해야 할 일 (딱 한 번)
### 1. 구글 서비스 계정 만들기 (시트 "쓰기" 권한용)
1. https://console.cloud.google.com 접속 → 프로젝트 만들기 (이름 아무거나)
2. **API 및 서비스 → 라이브러리 → "Google Sheets API" → 사용**
3. **API 및 서비스 → 사용자 인증 정보 → 사용자 인증 정보 만들기 → 서비스 계정** (이름 예: `popup-ping`)
4. 만든 서비스 계정 클릭 → **키 → 키 추가 → 새 키 만들기 → JSON** → 파일이 다운로드돼요 (⚠️ 절대 공개 금지)
5. 그 JSON 안의 `client_email` (…@…iam.gserviceaccount.com) 을 복사
6. 구글 시트 **공유 → 그 이메일을 "편집자"로 추가** (알림 보내기는 체크 해제)

### 2. GitHub에 시크릿 등록
저장소 → **Settings → Secrets and variables → Actions → New repository secret**
- `SHEET_ID` = `1ADk_0vPkvHxv74f8M8SSSqpHSzLvP6YoVfFVfrEcSkQ`
- `GOOGLE_SERVICE_ACCOUNT_JSON` = 다운로드한 JSON 파일 **내용 전체**

### 3. 첫 실행
저장소 → **Actions → "팝업 자동 수집" → Run workflow** 로 수동 1회 실행.
(첫 실행은 상세 페이지를 수천 건 읽어서 10~20분 걸려요. 이후엔 캐시 덕분에 몇 분이면 끝나요.)

## 로컬에서 시험하기 (시트는 건드리지 않아요)
```bash
pip install -r collector/requirements.txt
DRY_RUN=1 python collector/collect_popups.py     # 결과가 collector/out.csv 로 저장돼요
DRY_RUN=1 MAX_FETCH=100 python collector/collect_popups.py   # 빠른 테스트
```

## 안전장치
- 수집 결과가 3건 미만이거나 상세 페이지 조회 실패율이 20%를 넘으면 **시트를 건드리지 않고** 종료해요.
- 시트엔 값을 먼저 쓰고 남는 아래쪽 행만 지워서, 중간에 실패해도 데이터가 통째로 사라지지 않아요.

## 참고
- 크롤링은 robots.txt 허용 범위 안에서, 동시 4건·요청 간격 0.15초로 천천히 해요. 개인 프로젝트 용도로만 쓰고, 이용약관도 한 번 확인해 주세요.
- 사이트 구조가 바뀌면 파싱이 깨질 수 있어요(JSON-LD 기반이라 비교적 튼튼해요). 실패하면 Actions 탭에 빨간 ❌ 로 보여요.
- GitHub는 저장소에 60일간 활동이 없으면 예약 실행을 멈춰요. 멈추면 Actions 탭에서 다시 켜 주세요.
