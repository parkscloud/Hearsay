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
gh release create v1.0.1 installer_output/HearsaySetup.exe --title "Hearsay v1.0.1" --notes "Bug fixes and improvements."
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
- This file is excluded from the repo via `.gitignore`
