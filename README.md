# commit-agent

코드 diff 분석 기반 커밋 메시지 생성 및 이슈 연동 AI 에이전트

아주대학교 소프트웨어학과 자기주도프로젝트 (2026-2학기)

## 개요

staged된 코드 diff를 분석해 Conventional Commits 형식의 커밋 메시지를 생성하고, 관련 GitHub 이슈를 자동으로 매핑한다. 매칭되는 이슈가 없으면 신규 이슈를 생성한다.

기존 도구(aicommits, opencommit, gptcommit 등)가 현재 diff만 보고 메시지를 생성하는 것과 달리, RAG로 해당 저장소의 과거 커밋·이슈 이력을 검색해 레포별 컨벤션을 반영한다. 또한 LLM이 상황에 따라 필요한 도구(이력 검색, 이슈 검색, 이슈 생성)를 스스로 선택하는 tool-use 구조로 동작한다.

## 기술 스택

- **Agent**: LangGraph
- **LLM**: Anthropic Claude SDK
- **Git/GitHub**: GitPython, PyGithub
- **CLI**: typer

## 프로젝트 구조

```
src/commit_agent/
├── cli/                # typer 진입점
├── analysis/           # diff 기반 변경 분석
├── rag/                # 과거 커밋/이슈 이력 인덱싱 및 검색
├── agent/              # LangGraph 에이전트 흐름, 도구 정의
└── git_integration/    # GitPython, PyGithub 연동
```

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env    # API 키 입력
```

## 사용법

```bash
commit-agent index        # 과거 커밋/이슈 인덱싱
commit-agent generate     # 커밋 메시지 생성 및 이슈 매핑
```