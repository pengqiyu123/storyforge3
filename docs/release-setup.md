# Release Setup

StoryForge3 currently ships Windows desktop builds only. Phase 8 added two runtime modes:

- **Sidecar mode**: the Tauri bundle includes the Python FastAPI backend built by `scripts/build_sidecar.ps1`.
- **Venv mode**: the desktop shell falls back to `.venv\Scripts\python.exe` for local development when no sidecar binary is present.

The Web quickstart does not require the desktop bundle; it runs `storyforge3 serve` directly.

## Generate the Tauri updater key

Run this once on a trusted machine:

```bash
pnpm tauri signer generate -w ~/.tauri/storyforge3.key
```

The command prints a public key and writes the private key file. Put the public key in `src-tauri/tauri.conf.json` at `plugins.updater.pubkey`.

## Configure GitHub Secrets

Add these repository secrets before pushing a release tag:

| Secret | Value |
| --- | --- |
| `TAURI_SIGNING_PRIVATE_KEY` | Full contents of `~/.tauri/storyforge3.key` |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | Password used when generating the key, or empty if no password was used |

`GITHUB_TOKEN` is provided automatically by GitHub Actions.

## Publish a release

Before creating a release tag, build the Python sidecar:

```powershell
cd D:\python\Novel\storyforge3
powershell -ExecutionPolicy Bypass -File scripts\build_sidecar.ps1
```

The script writes a PyInstaller `--onedir` output under `src-tauri\binaries\storyforge3-api-x86_64-pc-windows-msvc\`. The desktop process manager starts that sidecar first and falls back to `.venv` only when the sidecar is missing.

Create and push a version tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The release workflow builds on `windows-2022`, publishes the installer assets, and verifies that Tauri updater artifacts include `latest.json`.

## Runtime requirement

In sidecar mode, end users should not need to install Python separately. If you intentionally run venv mode for development, install the package locally:

```bash
python -m pip install storyforge3
```

The sidecar packaging path still needs a real release smoke test: PyInstaller output, package data, install size, API health, and first-window startup must be verified on a clean Windows machine before public distribution.
