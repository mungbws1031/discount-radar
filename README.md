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
