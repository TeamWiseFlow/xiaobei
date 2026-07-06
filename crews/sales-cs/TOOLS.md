# Customer Service — Tools

## Restrictions

- No arbitrary shell command execution (T0 security level)
- The only permitted shell commands are those explicitly allowlisted for declared skills
- No raw SQL access: all DB operations must use the named scripts in `skills/customer-db/scripts/` (no `db.sh sql`)
- No file writes outside `feedback/` and `db/` directories
- No self-modification of workspace files (SOUL.md, AGENTS.md, MEMORY.md, etc.)
- Do not expose internal DB fields or schema to users
- Schema changes require main agent approval, never self-modify
