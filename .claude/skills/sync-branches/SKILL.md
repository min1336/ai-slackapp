---
description: main을 pull하고, root/ 브랜치를 rebase 후 push하고, feat/ 및 fix/ 브랜치를 로컬+원격 모두 삭제
---

# Sync Branches Skill

main 기준으로 root/ 브랜치를 최신화하고, 완료된 feat/ 및 fix/ 브랜치를 정리하는 skill.

## Procedure

### 1. 상태 확인
- `git fetch origin`
- `git branch -a`로 전체 브랜치 목록 확인
- root/, feat/, fix/ 브랜치 목록(로컬+원격)을 사용자에게 표로 보여주기

### 2. main 최신화
- `git checkout main && git pull origin main`

### 3. root/ 브랜치 rebase
- 모든 로컬 `root/*` 브랜치를 순회하며:
  - `git checkout <branch> && git rebase main`
  - conflict 발생 시 `git rebase --abort` 후 해당 브랜치 건너뛰기 (사용자에게 알림)

### 4. root/ 브랜치 push
- rebase 성공한 모든 `root/*` 브랜치를 `git push origin <branch> --force-with-lease`

### 5. feat/ 및 fix/ 브랜치 삭제
- 로컬 `feat/*`, `fix/*` 브랜치: `git branch -D <branch>`
- 원격 `feat/*`, `fix/*` 브랜치: `git push origin --delete <branch>`
- 현재 체크아웃된 브랜치가 feat/ 또는 fix/이면 먼저 main으로 checkout

### 6. 결과 보고
- `git branch -a`로 최종 상태 확인
- 작업 결과를 표로 요약 (성공/실패/건너뛴 브랜치)

## Rules
- conflict 발생한 root/ 브랜치는 건너뛰고 사용자에게 수동 해결 안내
- `--force-with-lease` 사용 (안전한 force push)
- 작업 전 브랜치 목록을 보여주고 확인 없이 바로 진행
- 완료 후 main 브랜치로 checkout
