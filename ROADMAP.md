# Roadmap

Privacy AI Workstation aims to be a **lean, trustworthy installer** for a local AI desk with strong privacy defaults — not a bloated “install everything” suite.

The **default install stays the v1.0.0 core forever**. Extra capability arrives through optional profiles and flags.

## Vision

A Windows/Linux machine that can:

1. Run local models (Ollama) with a solid chat UI (LibreChat)
2. Use privacy-respecting browser, VPN, and email apps
3. Optionally harden further (password manager, posture checks, checklists)
4. Optionally grow into creator/knowledge workflows — only when the user asks

Account logins (Mullvad, Proton, password vaults) always remain manual.

## Milestones

### v1.0.0 — Core (current)

First public release. Ships today:

| Layer | Components |
|--------|------------|
| Local AI | Ollama + hardware-aware model fit advice |
| Chat UI | LibreChat (Docker), wired to Ollama |
| Privacy browsers | Brave + DuckDuckGo (Windows; Brave on Linux) |
| VPN / email | Mullvad VPN, Proton Mail |
| Tooling | Git, Node.js, Docker, optional VSCodium |
| Ops | `audit` / `status` / `report` / `install` / `repair` / `start` / `stop` |

No new default apps beyond this core.

### v1.1 — Guided hardening (planned)

Make the workstation *finishable* without changing OS security policy automatically.

- Post-install checklist (printed after `install` / `repair`; possible `checklist` subcommand)
- Disk encryption **detection** (BitLocker / LUKS) in audit/status/report
- Firewall **detection** in audit/status/report
- Conservative wording (“not detected” ≠ “insecure”)

**Non-goals for v1.1:** enabling BitLocker, rewriting firewall rules, system debloat.

### v1.2 — Privacy profile (planned)

Optional deeper privacy tooling on top of core.

- `--profile core|privacy` (default: `core`)
- **KeePassXC** detect/install for the privacy profile (local/offline-first password manager)
- `--no-keepassxc` opt-out
- Audit/status fields for KeePassXC

**Non-goals for v1.2:** vault unlock automation; making KeePassXC part of the default `core` install; Bitwarden as the privacy-profile standard (may remain a future optional pick).

### v1.3 — Chat UX options (planned)

Give users a lighter UI choice without abandoning LibreChat.

- Optional **Open WebUI** via Docker behind an explicit flag (for example `--open-webui`)
- LibreChat remains the default chat UI
- Docs that explain when to prefer each UI

**Non-goals for v1.3:** replacing LibreChat; installing both UIs unless the user asks.

### v2.0 — Creator / knowledge profiles (planned)

Explicit power-user opt-in — never the default.

- `--profile creator` (and related flags) for heavy tools such as ComfyUI-class image workflows and/or Whisper-class transcription
- Optional private sync (for example Syncthing)
- Documentation-only pointers for apps that stay manual (Obsidian, Signal, and similar)

**Non-goals for v2.0:** putting creator stacks into plain `install`; silent GPU driver replacement.

## Target install shape

```text
privacy-ai-workstation install [--profile core|privacy|creator]
  core     = v1.0.0 stack (default)
  privacy  = core + KeePassXC + richer posture checklist
  creator  = core + heavy optional AI/media tools (never default)
```

## Principles

1. **Lean default** — predictable core install
2. **Idempotent** — scan → install-if-missing → skip-if-healthy
3. **Opt-in upgrades** — `--update` only when requested
4. **Audit can be strict; install must not surprise**
5. **No credential automation**
6. **No silent OS security-policy changes**

## Non-goals (product-wide)

- Automating Mullvad, Proton, or password-manager logins
- OS debloat / telemetry-kill scripts inside the installer
- Replacing antivirus or rewriting host firewall policy by default
- macOS support until explicitly scheduled
- Treating upstream app bugs as issues against this repo (report those upstream)

## Status key

| Label | Meaning |
|--------|---------|
| current | Shipped in the latest public release |
| planned | Intended work; order may shift |
| non-goal | Intentionally out of scope |
