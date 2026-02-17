# Releasing Hearsay

Steps to create a new GitHub release with the installer attached.

## Prerequisites

- `build.bat` dependencies (Python 3.11+, PyInstaller)
- Inno Setup 6+ (`winget install JRSoftware.InnoSetup`)
- GitHub CLI (`winget install GitHub.cli`)

## Build the installer

```bash
# 1. Bundle the app with PyInstaller
build.bat

# 2. Compile the Windows installer
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

Output: `installer_output\HearsaySetup.exe`

## Create the release

```bash
# Tag and create the release with the installer attached
gh release create v1.0.2 installer_output/HearsaySetup.exe --title "Hearsay v1.0.2" --notes "$(cat <<'EOF'
### New features

- **About window** — new "About" menu item in the system tray shows version, author, GitHub link, open-source acknowledgements, and license (closes #3)
- **Transcript delay disclaimer** — the Live Transcript window now shows a note explaining the ~30–60 second delay between speech and text appearing (closes #1)
- **Session separators** — a "Recording ended at ..." divider is inserted between sessions in the Live Transcript so they no longer blend together (closes #2)

### Bug fixes

- **Fix race condition between recording stop and start** — rapidly stopping and starting a new recording no longer causes empty transcripts or "didn't seem to start" failures. The new recording now waits for the previous teardown to fully complete before opening audio devices or loading a model.
- **Fix microphone not picked up in "Both" mode** — the audio mixer now RMS-normalises each stream independently before mixing, so a quiet microphone is no longer drowned out by louder system audio.
- **Clean shutdown after stop** — quitting the app immediately after stopping a recording now waits for the teardown to finish instead of exiting prematurely.
- **Clean uninstall** — the installer now terminates any running Hearsay process before removing files, so uninstall no longer fails with locked-file errors (closes #4)
EOF
)"
```

For subsequent releases, bump the version tag and update the notes:

```bash
gh release create vX.Y.Z installer_output/HearsaySetup.exe --title "Hearsay vX.Y.Z" --notes "Description of changes."
```

To generate notes from commits since the last release:

```bash
gh release create vX.Y.Z installer_output/HearsaySetup.exe --title "Hearsay vX.Y.Z" --generate-notes
```

## Verify

After creating the release, confirm:

1. The release appears at https://github.com/parkscloud/Hearsay/releases
2. `HearsaySetup.exe` is listed as a downloadable asset
3. The "Installed version" link in README.md resolves to the releases page

## Notes

- The version in `installer.iss` (`AppVersion=`) should match the release tag
- This file is tracked in the repo for portability
