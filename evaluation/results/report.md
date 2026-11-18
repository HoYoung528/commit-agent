# 커밋 메시지 생성 정확도 평가

## 평가 방법

계획서의 검증 방법을 따른다 — 특정 시점 이전 커밋만 인덱싱하고, 그 이후 커밋은
diff만 입력해 메시지를 생성한 뒤 실제 커밋 메시지와 비교한다.

- 대상 저장소: vercel/ai, crewAIInc/crewAI, goreleaser/goreleaser
- 커밋 수집 깊이: 1200건. 머지 커밋, 봇 커밋, 규약을 벗어난 커밋은 제외
- 시점 분할: 최신 20%를 평가 대상으로 떼어내고 나머지를 인덱싱
- 인덱싱: 분할 지점 이전 최대 500건. 봇 커밋도 포함(실사용과 동일)
- 표본 추출: 타입별 최대 5건. 무작위로 뽑으면 fix에 몰려 분류 능력을 재지 못함
- 검색: 유사 커밋 상위 3건을 프롬프트 예시로 제시. 정답 커밋은 제외
- 생성: 이슈 매핑·초안 제안·브랜치 제안은 끔. 허용 타입은 좁히지 않음

지표는 실제 커밋 메시지 첫 줄과 비교한다. 제목 유사도는 문자 단위(difflib),
의미 유사도는 임베딩 코사인이다.

## 저장소별 결과

### vercel/ai

| 구분 | 표본 | 형식 준수 | 타입 일치 | scope 유무 일치 | scope 값 일치 | 제목 유사도 | 의미 유사도 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RAG 미적용 | 28 | 100% | 79% | 61% | 92% | 0.513 | 0.705 |
| RAG 적용 | 28 | 100% | 86% | 75% | 94% | 0.578 | 0.790 |

<details><summary>생성 예시</summary>

- 실제: `chore(tool-bash): mark the bash tool as experimental (#23614)`
  - RAG 적용: `chore(tool-bash): mark bash tool as experimental`
  - RAG 미적용: `chore(tool-bash): mark bash tool as experimental`
- 실제: `chore: fix timeout issue for global declaration test (#23346)`
  - RAG 적용: `test(ai): raise timeout for global declaration compatibility test`
  - RAG 미적용: `test: extend timeout for declaration compatibility test on CI`
- 실제: `chore(examples): add HarnessAgent image input docs and e2e support (#23683)`
  - RAG 적용: `feat(examples): enable image inputs in e2e harness chats`
  - RAG 미적용: `feat: Enable image input in harness examples`

</details>

### crewAIInc/crewAI

| 구분 | 표본 | 형식 준수 | 타입 일치 | scope 유무 일치 | scope 값 일치 | 제목 유사도 | 의미 유사도 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RAG 미적용 | 31 | 100% | 68% | 52% | 86% | 0.443 | 0.648 |
| RAG 적용 | 31 | 100% | 71% | 77% | 75% | 0.490 | 0.682 |

<details><summary>생성 예시</summary>

- 실제: `chore(tools): make the vision_tool more dynamic (#7350)`
  - RAG 적용: `feat(vision_tool): Add query and complexity-based model selection`
  - RAG 미적용: `feat: Add query and complexity-based model selection with explicit`
- 실제: `chore(telemetry): remove unused _safe_telemetry_operation from crewai_core (#6977)`
  - RAG 적용: `refactor(telemetry): remove unused _safe_telemetry_operation helper`
  - RAG 미적용: `refactor(telemetry): Remove unused helper to simplify Telemetry API`
- 실제: `chore(ci): ignore unpatched nltk GHSA-8mgp-746c-j5xp (#7215)`
  - RAG 적용: `ci: suppress nltk GHSA-8mgp-746c-j5xp in audits`
  - RAG 미적용: `chore: Align pip-audit ignores for unresolved nltk GHSA`

</details>

### goreleaser/goreleaser

| 구분 | 표본 | 형식 준수 | 타입 일치 | scope 유무 일치 | scope 값 일치 | 제목 유사도 | 의미 유사도 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RAG 미적용 | 25 | 100% | 80% | 60% | 50% | 0.320 | 0.615 |
| RAG 적용 | 25 | 100% | 84% | 76% | 50% | 0.397 | 0.669 |

<details><summary>생성 예시</summary>

- 실제: `chore: svu config`
  - RAG 적용: `chore: tighten svu tag pattern to ignore nightly tags`
  - RAG 미적용: `chore: restrict svu to proper release tags`
- 실제: `chore(ci): update deps`
  - RAG 적용: `ci(deps): bump actions to latest pins for security and compatibility`
  - RAG 미적용: `ci: Bump pinned GitHub Actions for security across workflows`
- 실제: `chore: fmt`
  - RAG 적용: `refactor(flatpak): format method declarations for readability`
  - RAG 미적용: `refactor(flatpak): align Pipe method signatures for readability`

</details>

## 전체

| 구분 | 표본 | 형식 준수 | 타입 일치 | scope 유무 일치 | scope 값 일치 | 제목 유사도 | 의미 유사도 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RAG 미적용 | 84 | 100% | 75% | 57% | 83% | 0.430 | 0.657 |
| RAG 적용 | 84 | 100% | 80% | 76% | 79% | 0.492 | 0.714 |

## 사전 기준 대비

| 기준 | 판정 |
| --- | --- |
| 타입 일치율 70% 이상 | 충족 |
| 타입 일치율이 RAG 미적용 대비 20%p 이상 개선 | **미달** |
| scope 유무 일치율 80% 이상 | **미달** |
| RAG 적용이 모든 지표에서 우위 | 충족 |

4개 중 2개 충족.
