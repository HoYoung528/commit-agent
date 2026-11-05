# 커밋 메시지 생성 정확도 평가

## 평가 방법

계획서의 검증 방법을 따른다 — 특정 시점 이전 커밋만 인덱싱하고, 그 이후 커밋은
diff만 입력해 메시지를 생성한 뒤 실제 커밋 메시지와 비교한다.

- 대상 저장소: vercel/ai, crewAIInc/crewAI, goreleaser/goreleaser
- 커밋 수집 깊이: 1200건. 머지 커밋, 봇 커밋, 규약을 벗어난 커밋은 제외
- 시점 분할: 최신 20%를 평가 대상으로 떼어내고 나머지를 인덱싱
- 인덱싱: 분할 지점 이전 최대 500건. 봇 커밋도 포함(실사용과 동일)
- 표본 추출: 타입별 최대 5건. 무작위로 뽑으면 fix에 몰려 분류 능력을 재지 못함
- 검색: 유사 커밋 상위 5건을 프롬프트 예시로 제시. 정답 커밋은 제외
- 생성: 이슈 매핑·초안 제안·브랜치 제안은 끔. 허용 타입은 좁히지 않음

지표는 실제 커밋 메시지 첫 줄과 비교한다. 제목 유사도는 문자 단위(difflib),
의미 유사도는 임베딩 코사인이다.

## 저장소별 결과

### vercel/ai

| 구분 | 표본 | 형식 준수 | 타입 일치 | scope 유무 일치 | scope 값 일치 | 제목 유사도 | 의미 유사도 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RAG 미적용 | 24 | 100% | 75% | 79% | 93% | 0.494 | 0.735 |
| RAG 적용 | 24 | 100% | 83% | 83% | 94% | 0.587 | 0.789 |

<details><summary>생성 예시</summary>

- 실제: `chore(docs): align Angular package readme and add verifier script for `README.md` conventions (#24114)`
  - RAG 적용: `docs: standardize package READMEs and add verification to CI to keep`
  - RAG 미적용: `ci: enforce minimal, standardized package READMEs and add CI`
- 실제: `chore(deepseek): lazily initialize validation schemas (#22552)`
  - RAG 적용: `perf(deepseek): defer validation schema construction until first use and`
  - RAG 미적용: `perf(deepseek): Defer schema construction with lazy/cached Zod schemas`
- 실제: `chore: upgrade to pnpm 12 (#23684)`
  - RAG 적용: `ci: switch CI to pnpm/setup v3 with runtime-managed Node and lockfile`
  - RAG 미적용: `ci: use pnpm/setup to provision pnpm + Node, require lockfile, and bump`

</details>

### crewAIInc/crewAI

| 구분 | 표본 | 형식 준수 | 타입 일치 | scope 유무 일치 | scope 값 일치 | 제목 유사도 | 의미 유사도 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RAG 미적용 | 29 | 100% | 69% | 69% | 40% | 0.411 | 0.646 |
| RAG 적용 | 29 | 100% | 69% | 66% | 82% | 0.451 | 0.641 |

<details><summary>생성 예시</summary>

- 실제: `chore: update litellm model catalog for v1.15.34 (#8922)`
  - RAG 적용: `fix(llms): sync Azure AI model catalog with latest pricing, features,`
  - RAG 미적용: `feat(litellm_catalog): Expand Azure AI model metadata with new`
- 실제: `chore(deps): drop the nltk advisory ignore now that 3.10.4 is locked (#8918)`
  - RAG 적용: `chore(deps): bump nltk to 3.10.4 and drop GHSA-8mgp-746c-j5xp ignores`
  - RAG 미적용: `fix: Raise nltk floor to 3.10.4 and drop stale vulnerability ignore`
- 실제: `chore: update litellm model catalog for v1.15.35 (#9011)`
  - RAG 적용: `feat(llms): add Azure GPT Realtime pricing and capabilities, and mark`
  - RAG 미적용: `feat(litellm-catalog): Add Azure Realtime and Whisper/Translate models`

</details>

### goreleaser/goreleaser

| 구분 | 표본 | 형식 준수 | 타입 일치 | scope 유무 일치 | scope 값 일치 | 제목 유사도 | 의미 유사도 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RAG 미적용 | 35 | 100% | 71% | 83% | 69% | 0.350 | 0.604 |
| RAG 적용 | 35 | 100% | 83% | 83% | 64% | 0.420 | 0.685 |

<details><summary>생성 예시</summary>

- 실제: `chore: auto-update generated files (#7254)`
  - RAG 적용: `chore: auto-update generated files`
  - RAG 미적용: `chore: update Node.js release checksums and add new sponsor entry`
- 실제: `chore: auto-update generated files (#7231)`
  - RAG 적용: `chore: auto-update generated files`
  - RAG 미적용: `chore: Publish v2.19.0 as latest release (including pro)`
- 실제: `chore: auto-update generated files (#6811)`
  - RAG 적용: `chore: auto-update generated files`
  - RAG 미적용: `chore: Publish v2.18.0: update latest pointers and release listings`

</details>

## 전체

| 구분 | 표본 | 형식 준수 | 타입 일치 | scope 유무 일치 | scope 값 일치 | 제목 유사도 | 의미 유사도 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RAG 미적용 | 88 | 100% | 72% | 77% | 71% | 0.410 | 0.653 |
| RAG 적용 | 88 | 100% | 78% | 77% | 80% | 0.475 | 0.699 |

## 사전 기준 대비

| 기준 | 판정 |
| --- | --- |
| 타입 일치율 70% 이상 | 충족 |
| 타입 일치율이 RAG 미적용 대비 20%p 이상 개선 | **미달** |
| scope 유무 일치율 80% 이상 | **미달** |
| RAG 적용이 모든 지표에서 우위 | **미달** |

4개 중 1개 충족.
