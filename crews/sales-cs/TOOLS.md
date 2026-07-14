# Customer Service — Tools

## Restrictions

- No arbitrary shell command execution
- The only permitted shell commands are those explicitly allowlisted for declared skills
- No file writes outside `feedback/` and `db/` directories
- No self-modification of workspace files (SOUL.md, AGENTS.md, MEMORY.md, etc.)
- Do not expose internal DB fields or schema to users
- Schema changes require main agent approval, never self-modify
