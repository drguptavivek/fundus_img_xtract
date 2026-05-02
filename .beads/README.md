# Beads - AI-Native Issue Tracking

Welcome to Beads! This repository uses **Beads** for issue tracking - a modern, AI-native tool designed to live directly in your codebase alongside your code.

## What is Beads?

Beads is issue tracking that lives in your repo, making it perfect for AI coding agents and developers who want their issues close to their code. No web UI required - everything works through the CLI and integrates seamlessly with git.

**Learn more:** [github.com/steveyegge/beads](https://github.com/steveyegge/beads)

## Quick Start

### Repository Mode

This repository uses Beads with Dolt in **embedded** mode. The portable,
tracked issue export is `.beads/issues.jsonl`; the local embedded Dolt store is
runtime state and is ignored by Git.

Tracked Beads files:
- `.beads/config.yaml`
- `.beads/metadata.json`
- `.beads/issues.jsonl`
- `.beads/README.md`
- `.beads/.gitignore`

Ignored local/runtime Beads files include `.beads/dolt/`,
`.beads/embeddeddolt/`, `.beads/backup/`, logs, locks, credentials, and
export-state files.

After issue changes, refresh the tracked export:

```bash
bd export -o .beads/issues.jsonl
```

Do not use `bd sync` or `bd dolt push` in this repository's normal workflow.

### Essential Commands

```bash
# Create new issues
bd create "Add user authentication"

# View all issues
bd list

# View issue details
bd show <issue-id>

# Update issue status
bd update <issue-id> --status in_progress
bd update <issue-id> --status done

# Refresh tracked issue export
bd export -o .beads/issues.jsonl
```

### Working with Issues

Issues in Beads are:
- **Git-native**: Exported to `.beads/issues.jsonl` and committed like code
- **AI-friendly**: CLI-first design works perfectly with AI coding agents
- **Branch-aware**: Issues can follow your branch workflow
- **Portable**: Refresh the tracked export with `bd export -o .beads/issues.jsonl`

## Why Beads?

✨ **AI-Native Design**
- Built specifically for AI-assisted development workflows
- CLI-first interface works seamlessly with AI coding agents
- No context switching to web UIs

🚀 **Developer Focused**
- Issues live in your repo, right next to your code
- Works offline, then travels with your Git commits
- Fast, lightweight, and stays out of your way

🔧 **Git Integration**
- Automatic sync with git commits
- Branch-aware issue tracking
- Intelligent JSONL merge resolution

## Get Started with Beads

Try Beads in your own projects:

```bash
# Install Beads
curl -sSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash

# Initialize in your repo
bd init

# Create your first issue
bd create "Try out Beads"
```

## Learn More

- **Documentation**: [github.com/steveyegge/beads/docs](https://github.com/steveyegge/beads/tree/main/docs)
- **Quick Start Guide**: Run `bd quickstart`
- **Examples**: [github.com/steveyegge/beads/examples](https://github.com/steveyegge/beads/tree/main/examples)

---

*Beads: Issue tracking that moves at the speed of thought* ⚡
