# CLAUDE.md

@AGENTS.md

## Lessons

`tasks/lessons.md` holds how the agent works here (tools, shell, verifying, writing to
the operator); it is gitignored and stays on this machine. The shared, project-agnostic
list (`C:\Files\Apps\__CommonShared\docs\07-agent-lessons.md`) loads at session start
through a hook in `.claude/settings.json`. After any correction from the operator, add a
lesson to `tasks/lessons.md` in the same turn: the rule, a "Why:" with the date, and its
check. Project rules and decisions stay in this file or AGENTS.md.

@tasks/lessons.md
