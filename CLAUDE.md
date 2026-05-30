# Project: upstream-label-correction

## Context Management (CRITICAL)
* Check /context before starting any major task
* Proactively run /compact when context exceeds 70%
* Do NOT wait for autocompact -- it is unreliable in VS Code
* After compaction, verify context dropped below 40% before continuing
* For large file generation tasks, compact between phases

## Compact Template
When compacting, preserve:
* Current task and progress state
* File paths already created/modified
* Key decisions and architecture choices
* What remains to be done

## Tool Usage
* Execute file operations sequentially, not in parallel
* Wait for each tool call to complete before starting the next
* For multi-file changes, batch into single operations where possible

## Git Discipline
* Map commits to specific tasks or requirements
* Use conventional commit messages
* Do not amend or rebase without explicit instruction

## Session Rules
* If context exceeds 80%, STOP current work and compact immediately
* Output git commit commands -- do not run them without permission
* When resuming after compact, read CLAUDE.md and check /context first
