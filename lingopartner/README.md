# Pepper Local AI POC — conversations and hands-free turns (v2 prototype)

**Windows backend + Android Studio Arctic Fox (2020.3.1) / Android API 23 Pepper tablet.**

This builds on the original Pepper Local AI POC, where the tablet already talks to a
Windows Python server, which invokes `whisper-cli.exe` (Whisper tiny + Silero VAD) and a
separately running `llama-server.exe` (Qwen). It adds four incremental capabilities:

1. **Session memory:** sends recent conversation turns back to Qwen, keyed by stable session ID.
2. **Hands-free utterance segmentation:** while explicitly enabled, the Pepper app reads audio
   frames and uses **energy-based speech onset / silence detection** instead of a fixed four-second window.
3. **Safe half-duplex turn-taking:** stop and release the mic → transcribe → generate → QiSDK
   speech completion → reopen the microphone. Stop, app backgrounding, errors or speech timeout halt listening.
4. **Optional SQLite persistence:** opt-in text conversation history and explicit per-lesson
   aggregate progress. No recording archive or automatic learner assessment.

> **Validation status:** The Python backend's automated tests were run in this authoring
> environment. The changed Kotlin source has **not been built in Arctic Fox or run on your Pepper**.
> Your team's local project has previous bug fixes; **merge deliberately—do not overwrite your
> latest working local files blindly**. See [UPGRADE_GUIDE](docs/UPGRADE_GUIDE.md).

## Architecture

```text
Pepper tablet / Kotlin QiSDK (Android >=23)
  MainActivity + AudioCaptureManager (energy-based utterance segmentation)
    │  HTTP /text or completed 16 kHz mono PCM16 WAV via /audio
    │  X-Session-Token, X-Session-Id
    ▼
Windows Python server (port 8765)
  ConversationManager (recent bounded history, optional SQLite)
  WhisperAdapter -- subprocess whisper-cli -- Silero VAD for transcription
  LlamaAdapter -- HTTP → local llama-server (port 8080) → Qwen
    │ JSON: transcript, response_text, tool_calls, history_turns
    ▼
Pepper RobotAdapterImpl → QiSDK SayBuilder → completion callback
  microphone resumes ONLY after successful speech completion
```

The LLM's `gesture/greeting` tool requests are displayed for diagnostics, **not executed**.
This project does **not** include Studerus et al.'s original source files. Its design draws
inspiration from their robot app architecture; see <https://github.com/studerus/pepper-android-realtime-chat>.

## Folder layout

```text
android-app/app/src/main/    # UI, HTTP, energy VAD, shared robot interface
android-app/app/src/pepper/  # QiSDK implementation
android-app/app/src/standalone/ # simulator implementation
backend/pepper_poc/          # server.py, pipeline.py, conversation.py
backend/tests/               # Python tests
backend/test_client.py       # text/WAV turn tests
backend/learning_client.py   # explicitly saved lesson results
windows/                     # original command-line helpers (mock mode)
docs/UPGRADE_GUIDE.md        # Windows setup and staged acceptance tests
```

## Getting started (Windows PowerShell)

### A. Python-only mock tests (no model binaries needed)

```powershell
cd "C:\PATH\TO\pepper_arcticfox_poc\backend"
py -3 -m unittest discover -s tests -v
py -3 -m pepper_poc.server
```

In a second PowerShell terminal (the backend remains open):

```powershell
cd "C:\PATH\TO\pepper_arcticfox_poc\backend"
py -3 test_client.py --session group-demo --text "My name is Ana"
py -3 test_client.py --session group-demo --text "What is my name?"
py -3 test_client.py --session group-demo --reset
py -3 test_client.py --session group-demo --text "What is my name?"
```

The first follow-up must remember Ana; after reset it must not.

### B. Real local backend

Start your **existing** `llama-server.exe` in its own PowerShell terminal and load your
known-working GGUF. Leave it listening at `127.0.0.1:8080`. Test its `/health` endpoint.
You can use Qwen 0.6B as the known baseline or separately test 9B when RAM permits.

Stop the mock Python backend (Ctrl+C). In PowerShell:

```powershell
cd "C:\PATH\TO\pepper_arcticfox_poc\backend"
$Tools = Join-Path $HOME "PepperTools"
$WhisperExe = (Get-ChildItem "$Tools\whisper" -Recurse -File -Filter whisper-cli.exe |
    Select-Object -First 1).FullName
$env:PEPPER_POC_TOKEN = [guid]::NewGuid().ToString("N")
Write-Host "Enter this token into the Pepper app: $env:PEPPER_POC_TOKEN"
py -3 -m pepper_poc.server --live `
    --host 0.0.0.0 --port 8765 `
    --token "$env:PEPPER_POC_TOKEN" `
    --llama-url "http://127.0.0.1:8080" `
    --whisper-exe "$WhisperExe" `
    --whisper-model "$Tools\models\ggml-tiny.bin" `
    --vad-model "$Tools\models\ggml-silero-v6.2.0.bin" `
    --history-turns 6
```

`--host 0.0.0.0` binds to the **trusted private LAN only**. Do not forward port 8765 to
the internet. Windows Firewall should allow TCP 8765 only on a trusted Private network
and ideally only from Pepper's address. Port 8080 stays bound to `127.0.0.1`.
The shared token is transmitted over unencrypted HTTP; **not production authentication**.

With the server running, in another PowerShell terminal:

```powershell
cd "C:\PATH\TO\pepper_arcticfox_poc\backend"
# Paste the token printed by the SERVER terminal; PowerShell windows don't share env vars.
$token = "PASTE_CURRENT_TOKEN"
py -3 test_client.py --token "$token" --session group-demo --text "My name is Carlos"
py -3 test_client.py --token "$token" --session group-demo --text "What is my name?"
py -3 test_client.py --token "$token" --session group-demo --wav "$HOME\PepperTools\audio\spoken.wav"
```

### C. Optional text/learning persistence

To retain **text** across backend restarts, add this flag to the server command:

```powershell
--db-path "$env:LOCALAPPDATA\PepperPOC\private\conversations.sqlite3"
```

**Do not paste that line by itself into PowerShell:** it is an extra argument to the Python
server startup command, before the last line's closing arguments. Its parent directory is
created automatically. Keep the database outside Git. Persistence is **off by default**.

Once the server is restarted with `--db-path`, explicitly record lesson progress:

```powershell
py -3 learning_client.py --token "$token" --session group-demo --lesson intro-es `
    --language es --completed 5 --correct 4
py -3 learning_client.py --token "$token" --session group-demo --show
py -3 learning_client.py --token "$token" --session group-demo --reset
```

This API only records scores **submitted by the learning app/operator**; it does not grade
pronunciation or infer progress automatically. `/session/reset` clears conversation only;
`/learning/reset` clears lesson records. If desired, delete the SQLite database after
stopping the server to clear all persisted records.

### D. Android on Pepper

- Use the **already verified** Android Studio Arctic Fox setup, **JDK 11**, **Gradle 7.0.2**,
  **AGP 7.0.4**, **QiSDK 1.7.5**, and Android API 23 min; keep your working Gradle Wrapper.
- Compare/merge new `MainActivity.kt`, `AudioCaptureManager.kt`, `RobotAdapter.kt`, and both
  flavor-specific `RobotAdapterImpl.kt` files with your known-working project. The supplied
  reference manifest already has the `tools:replace` fixes you applied in your Windows copy.
- Build **standaloneDebug** first and then **pepperDebug**. This archive does not
  include the missing Gradle launcher scripts/JAR from the original baseline;
  preserve the wrapper you fixed locally or generate the official Gradle 7.0.2 wrapper.
- Enter **http://WINDOWS_IPV4:8765** and your current session token in the Pepper UI.
- Confirm robot focus and fixed speech, then typed question/response, then manual WAV.
- Press **Start hands-free listening** and grant RECORD_AUDIO permission. Watch the
  visible states LISTENING → SPEECH DETECTED → PROCESSING → SPEAKING → LISTENING.
- Press **Stop hands-free listening** to stop microphone monitoring. Leaving the app
  also stops listening. This does not interrupt Pepper's already-running speech.
- Press **Reset conversation's memory** only when not listening or processing.

## API contract

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | process status and persistence flag |
| POST | `/text` | JSON `{ "text": "Hello" }` |
| POST | `/audio` | completed 16 kHz mono PCM16 WAV, <=15 sec |
| POST | `/session/reset` | `{}`; discard conversation for session |
| GET | `/learning/progress` | view explicitly saved lesson results (SQLite only) |
| POST | `/learning/progress` | JSON lesson_id, language, completed, correct (SQLite only) |
| POST | `/learning/reset` | `{}`; clear saved lesson scores (SQLite only) |

All routes other than health use `X-Session-Token` when token is configured and
`X-Session-Id` for isolation. Session IDs must be 1–80 ASCII alphanumeric, `_`, or `-`.
The Android app generates and locally remembers a random per-install session ID.
Older clients without the header use the shared legacy ID `legacy`, which is
**not appropriate for multiple real users**.

## Safety, privacy and limitations

- **Consent is required** before starting unattended microphone monitoring; show a visible
  listening indicator. There is **no wake word or speaker recognition**. Ambient people and
  other voices can trigger the energy detector. Use only in supervised, consented trials.
- Listening is **half-duplex**: the microphone is closed during network processing and
  QiSDK speech. Voice barge-in is not provided. A tablet Stop button is provided.
- Energy threshold (~350 RMS minimum, adaptive noise multiplier 3), 300 ms pre-roll,
  900 ms end silence, 12 s segment limit. These are **initial tuning settings** and
  may fail in noisy rooms. Silero in `whisper-cli` performs a separate VAD pass.
- Microphone source routing is device dependent. Verify whether audio comes from Pepper's
  head microphones or the tablet hardware; this code cannot guarantee that.
- Audio is saved **temporarily** to a Windows temp WAV by WhisperAdapter, then deleted
  after transcription; it is **not** stored in SQLite. Do not publish real recordings.
- No full lesson curriculum, pronunciation scoring, wake-word isolation, speaker ID,
  model tool execution, cloud auth, production TLS, or encrypted SQLite is included.
- Serialized LLM conversations and blocking per-turn inference are fine for one robot POC,
  **not** multiple concurrent robots. Long 9B inference may make turn taking feel slow.
- Direct line-of-sight, trusted private LAN, supervised Pepper trials only. Avoid motion
  during the microphone experiments. Do not use the prototype with personal data of
  students/minors without appropriate consent and institutional safeguards.

## Attribution and dependency sources

- Studerus et al., [Pepper Android realtime chat](https://github.com/studerus/pepper-android-realtime-chat) — architectural reference, **not copied source**.
- [SoftBank QiSDK](https://qisdk.softbankrobotics.com/sdk/doc/pepper-sdk/) — Android Pepper robot control.
- [llama.cpp](https://github.com/ggml-org/llama.cpp) — local LLM inference.
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp) — local ASR and Silero VAD interface.
- Qwen GGUF, Whisper tiny and Silero model weights **not included**.

Before publishing publicly, review licenses and add a license for **your own team's source**.
Never commit local model weights, EXEs/DLLs, tokens, recordings, or SQLite files. Consult
[UPGRADE_GUIDE](docs/UPGRADE_GUIDE.md) for the staged test and rollback plan.
