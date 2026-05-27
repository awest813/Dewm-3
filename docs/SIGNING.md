# Code Signing & Notarization Setup

This guide explains how to configure the repository secrets needed for automatic
code signing and notarization of macOS release DMGs.

When signing secrets are present the [release workflow](../.github/workflows/release.yml)
automatically produces a `dhewm3-macos-universal-signed.dmg` that passes
Gatekeeper on any Mac — no "right-click → Open" workaround required.

---

## Why sign?

macOS Gatekeeper blocks apps from unidentified developers by default. Signing
with an Apple Developer ID certificate (and notarizing with Apple) lets your
users double-click the app and play immediately, with no security prompts.

---

## Prerequisites

1. An **Apple Developer account** (paid, $99/year).
2. A **Developer ID Application** certificate issued from Xcode or
   developer.apple.com → Certificates.
3. An **app-specific password** for your Apple ID:
   <https://support.apple.com/HT204397>

---

## Exporting the certificate

1. Open Keychain Access on your Mac.
2. Find your *Developer ID Application: …* certificate.
3. Right-click → Export → save as `certificate.p12` with a strong password.
4. Base64-encode it:
   ```sh
   base64 -i certificate.p12 | pbcopy
   ```
   (The result is now in your clipboard.)

---

## Setting repository secrets

Go to your repository on GitHub → **Settings → Secrets and variables → Actions**
→ **New repository secret** and add each of the following:

| Secret name | Value |
|-------------|-------|
| `MACOS_CERTIFICATE` | Base64-encoded `.p12` from the step above |
| `MACOS_CERTIFICATE_PWD` | Password you used when exporting the `.p12` |
| `MACOS_KEYCHAIN_PWD` | Any strong random string (used for a temporary keychain) |
| `NOTARIZE_APPLE_ID` | Your Apple ID email (e.g. `you@example.com`) |
| `NOTARIZE_TEAM_ID` | Your 10-character Apple Developer Team ID (found at developer.apple.com → Membership) |
| `NOTARIZE_PASSWORD` | The app-specific password from the prerequisite step |

---

## How the workflow uses these secrets

When a `v*` tag is pushed, the [release workflow](../.github/workflows/release.yml)
runs its `universal` job. Near the end of that job:

1. A step checks whether `MACOS_CERTIFICATE` is non-empty.
2. If it is, the certificate is imported into a temporary keychain, the `.app`
   is signed with `codesign --deep --force --options runtime` using the
   `Developer ID Application` identity that matches `NOTARIZE_TEAM_ID`, the DMG
   is repackaged, notarized with `xcrun notarytool`, and the ticket is stapled.
3. The signed `dhewm3-macos-universal-signed.dmg` is uploaded as a release
   artifact and attached to the GitHub Release alongside the unsigned DMGs.

If the secrets are not set, the workflow skips those steps and only produces
the unsigned DMGs (with a console note explaining how to configure signing).

---

## Verifying a signed build

After a signed release:

```sh
# On a clean Mac (not your development machine):
spctl --assess --type exec dhewm3.app
# Expected: dhewm3.app: accepted   source=Notarized Developer ID

codesign -dvv dhewm3.app 2>&1 | grep -E 'Authority|TeamIdentifier'
# Expected: lines referencing your Developer ID and Team ID
```
