# 할인 레이더 (Discount Radar)

외식·키즈카페·카드·여행 등 흩어진 할인 정보를 자동 수집하고, **내 조건(보유 카드·통신사·자녀 나이·지역)에 맞는 것만** 골라 알려주는 플랫폼.

> `mungbws1031/eddies-day-planner` 브랜치에서 기획을 시작한 뒤 독립 프로젝트로 분리했습니다.

## 문서

- [`docs/DiscountRadar_Plan_v0.1.md`](docs/DiscountRadar_Plan_v0.1.md) — 기획서 v0.1 (페르소나·KPI, 소스 맵, 기능 정의, 수집 파이프라인, IA·유저플로우, PRD, 로드맵)
- [`sources/registry.yaml`](sources/registry.yaml) — Phase 0 수집 소스 레지스트리 (12개 소스, 접근 방식·주기·정책)

## 로드맵

| Phase | 범위 |
|---|---|
| 0. 개인 봇 | 소스 12개, Claude Code Routine 스케줄, Notion DB, 텔레그램 주말 브리핑 |
| 1. 베타 | 어댑터 25개, Postgres, 매칭 엔진, PWA 4탭 |
| 2. 공개 | 어댑터 50개+, 위치 기반, "이 가게 어떤 카드", 절약 리포트 |
| 3. 확장 | 마이데이터 연동, 가족 공유, 캘린더 연동 |

## 수집 원칙

- 소스별 robots.txt·약관을 레지스트리에 기록하고 `blocked` 소스는 뉴스레터 파싱·수동 입력으로 대체
- 원문을 복제하지 않고 요약 + 원문 링크만 저장
- 서버가 사용자 계정으로 대리 로그인하지 않음

## Phase 0 스캐폴드 (수집 파이프라인)

기획서 §5.1의 파이프라인을 최소 실행 가능한 형태로 구현했습니다.

```
sources/registry.yaml → Scheduler → Adapter(fetch) → Adapter(extract) → Validator
  → Dedup/Merge(SQLite) → CLI(list / briefing / health)
```

### 설치

```bash
pip install -r requirements.txt
```

### 사용

```bash
python cli.py collect              # registry.yaml에 url이 채워진 소스를 즉시 수집
python cli.py collect --due-only   # 지금 시각 기준 cron이 due인 소스만 수집 (스케줄러용)
python cli.py collect --source community.ppomppu.hotdeal
python cli.py list --domain dining # 활성 딜 목록
python cli.py briefing             # 주말 브리핑 텍스트
python cli.py health               # 소스별 헬스 상태 + 커버리지 KPI
```

### 구조

| 파일 | 역할 |
|---|---|
| `src/models.py` | 공통 Deal 스키마 (기획서 §5.2) |
| `src/registry.py` | `sources/registry.yaml` 로더, `policy=blocked` 소스 자동 제외 |
| `src/adapters/` | `rss`(동작함) · `html`(원문 저장까지만) · `browser`/`mail`(Phase 1 스텁, Playwright·IMAP 미설치) |
| `src/pipeline.py` | fetch → extract → validate → upsert 오케스트레이션, 실패 소스 격리 |
| `src/storage.py` | SQLite 기반 Deal DB, 제목·도메인·마감일 기준 중복 병합, 만료 처리 |
| `src/scheduler.py` | registry.yaml에서 쓰는 cron 패턴(`*/N`, 고정 시각)만 지원하는 최소 due-check |
| `src/briefing.py` | 주말 브리핑 텍스트 생성 (매칭 엔진 이전 단계 — 조건 필터링 없음) |

### 소스 URL 채우기

`sources/registry.yaml`의 `url` 필드는 비어 있습니다. 이 리포를 개발한
샌드박스는 조직 정책상 임의 외부 호스트로 나가는 네트워크가 차단되어
있어(egress allowlist), 실제 카드사·커뮤니티 사이트 URL을 여기서 검증할
수 없었습니다. **로컬/개인 서버 환경에서 각 소스의 실제 RSS·페이지
URL을 확인해 채운 뒤** `python cli.py collect`로 실행하세요.

- `method: rss` 소스만 즉시 동작합니다 (표준 RSS 2.0 `<item>` 파싱 + 정규식 기반 할인율/금액 추출).
- `method: html` 소스는 원문만 저장하고 Deal은 만들지 않습니다 — LLM Extractor(Claude API)를 붙이는 것이 다음 작업입니다.
- `method: browser`/`mail` 소스는 각각 Playwright/IMAP 연동이 필요한 Phase 1 스텁입니다 (`fetch()` 호출 시 명시적으로 예외 발생).

### 테스트

```bash
python -m unittest discover -s tests
```

네트워크 호출 없이 로컬 픽스처(`tests/fixtures/sample_hotdeal.rss`)로
추출·검증·중복 제거·만료·스케줄 로직을 검증합니다 (11개 테스트).

### 다음 작업 (Phase 0 잔여)

1. `sources/registry.yaml`의 ★★★ 소스 URL 확인·기입 (RSS부터)
2. `html` 어댑터에 Claude API 기반 LLM Extractor 연결 (기획서 §5.3)
3. 텔레그램/카카오 발송 연동 — `briefing.build_briefing()` 출력을 전송
4. 매칭 엔진(F-06) 붙이기 전까지는 브리핑이 "내 조건" 필터링 없이 전체 노출됨에 유의
