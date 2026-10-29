# Controlled upgrade procedure — Windows + Pepper

**Do not replace your latest successfully tested POC with this archive without a backup.**
This package was based on the *original* `pepper_arcticfox_poc_trial_windows.zip`
and carries known fixes discussed in chat (manifest `tools:replace`, Kotlin QiSDK
`object` import, LLM non-thinking output check). Your local fixes may differ.

## Branch and merge

1. Commit or ZIP-backup your current working `pepper_arcticfox_poc` first. A good Git branch
   name is `feature/session-memory-handsfree`.
2. Compare the `backend/pepper_poc/` package, the test client, and the Android Kotlin
   files against your local versions. Merge deliberately rather than overwriting.
3. Keep **all your existing working Gradle wrapper files**, Android Studio configuration,
   network address, and QiSDK version. New code uses *no additional Android dependencies*.
4. Run the Python mock suite before connecting a model or Pepper:

   ```powershell
   cd "C:\PATH\TO\pepper_arcticfox_poc\backend"
   py -3 -m unittest discover -s tests -v
   ```

5. Start the mock server and test repeated queries with the **same** `--session` ID.
   Confirm different session IDs are isolated. Confirm `/session/reset` clears memory.
6. Run the real backend with your verified Windows Whisper binaries and Qwen server;
   test both `/text` and `/audio`. No need to change Qwen for the first upgrade.
7. If you want opt-in persistence, supply `--db-path` outside the Git repository, restart
   the server, test that it remembers history across a restart, and explicitly store
   and retrieve one aggregate learning score using `learning_client.py`.
8. Compile and install the Android `standaloneDebug` then `pepperDebug` variants. If you
   get build errors, record the *first* compiler error rather than repeatedly upgrading
   Gradle or guessing dependency versions.
9. In Pepper UI, verify robot focus and the original fixed speech; test typed and
   four-second recorded WAV before activating continuous listening.
10. With one consenting adult and a quiet test room, enable hands-free listening. Speak
    short sentences. Test 10 turns, 5-second silences, speech below normal volume,
    background fan/noise, an intentional Stop, loss of Wi-Fi, error recovery, and app
    backgrounding. **Confirm mic stays closed while QiSDK is speaking.**

## New/changed files

- `backend/pepper_poc/conversation.py` **new** — bounded history + SQLite + progress.
- `backend/pepper_poc/server.py` **changed** — session ID, reset and optional progress routes.
- `backend/pepper_poc/pipeline.py` **changed** — Qwen receives message history, empty output fails.
- `backend/test_client.py` **changed** — `--session`, `--reset`.
- `backend/learning_client.py` **new** — operator-submitted aggregate lesson scores.
- `backend/tests/test_conversation.py` **new** — memory, persistence, session isolation tests.
- `android-app/app/src/main/.../AudioCaptureManager.kt` **new** — energy detector.
- `android-app/app/src/main/.../MainActivity.kt` **changed** — UI and hands-free loop.
- `android-app/app/src/main/.../RobotAdapter.kt` **changed** — completion callback.
- `android-app/app/src/{pepper,standalone}/.../RobotAdapterImpl.kt` **changed** — callback.
- `android-app/app/src/main/AndroidManifest.xml` — retains merger fix.

## Milestone acceptance and limitations

| Stage | Pass criterion | Verification status |
|---|---|---|
| 1 Session memory | Follow-up question recalls earlier name; reset loses it | Python mock tests passed |
| 2 Automatic segmentation | Short speech accepted without pressing a fixed-length record button | Android hardware test pending |
| 3 Half-duplex hands-free | Auto-listening returns after *completed* QiSDK speech, not during it | Android hardware test pending |
| 4 Persistence | History and aggregate scores survive backend restart with `--db-path` | SQLite unit tests passed |

This is *not* a continuous neural VAD stream. Tablet energy VAD gates recordings;
Windows Whisper's existing Silero filter applies to completed utterances. The first
upgrade deliberately avoids an untested WebSocket protocol, ONNX dependency, and changes
to Pepper's QiSDK audio routing. Background noise may cause false activations.

## Privacy and failure stop conditions

- Only start microphone capture after explicit operator/user choice and Android permission.
- Keep a clearly visible LISTENING indication; stop when the app leaves the foreground.
- Persistent SQLite may contain conversation text and must be protected as sensitive data.
- Any speech failure/timeout ends automatic listening instead of risking acoustic feedback.
- The Stop button prevents *future* recording; a network request already in progress may
  finish on the Windows backend, but no fresh recording or response speech will start.
- No cloud service, model download, third-party EXEs, DLLs or sensitive recordings are
  included in this code package.

## Rollback

If something breaks during integration, switch back to the working Git commit or backup.
Keep both sides on the same protocol version (v2 adds `X-Session-Id`, which old backends
ignore, but the v2 UI's reset/progress features need the updated server).
