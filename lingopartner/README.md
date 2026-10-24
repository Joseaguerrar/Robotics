# Pepper Local AI — Proof of Concept

A **local, speech-enabled AI proof of concept for the Pepper robot**. The Pepper tablet runs a minimal **Kotlin / SoftBank QiSDK** Android application that sends typed text or recorded audio over a trusted local network to a **Python backend on Windows**. The backend invokes **Whisper (`whisper.cpp`)** for speech recognition and **Qwen through `llama.cpp`** for text generation; the robot speaks the returned `response_text` using QiSDK's `Say` action.

**Project status:** The team has tested real text and audio interaction between Pepper and the Windows backend. This is a **research/teaching POC**, not a production-ready conversational robot, a finished language curriculum, or a complete port of the Studerus et al. framework. Test results refer to the team's working copy; anyone cloning the repository should repeat the acceptance tests below.

## What works and what is experimental

| Capability | Current status |
| --- | --- |
| Local HTTP backend, independent mock tests | Implemented; tested |
| Real Whisper transcription of WAV audio | Tested on Windows |
| Local Qwen inference via `llama-server` | Tested with **Qwen3-0.6B** |
| Backend audio → transcription → LLM response | Tested |
| Android `pepperDebug` app on Pepper | Installed and tested |
| Typed input from Pepper → Qwen response → audible QiSDK speech | Tested |
| Recorded audio from app → Whisper → Qwen → audible response | Tested |
| Qwen 9B replacement | Tested |
| Robot gesture tool calls | **Displayed only; no physical gesture execution** |
| Autonomous navigation, camera perception, streaming/full-duplex audio | **Not implemented** |

For detailed evidence and unresolved test conditions, see [`VALIDATION_REPORT.md`](VALIDATION_REPORT.md). **Update that report to reflect the team's most recent tests before publishing.**

## Architecture

```text
Pepper (Android 6+ / QiSDK)
  ├─ Kotlin UI: type a message or record a short WAV
  ├─ HTTP client: POST /text or POST /audio
  └─ QiSDK Say: speak response_text
                 │  trusted local network (HTTP, port 8765)
                 ▼
Windows Python backend (backend/pepper_poc/server.py)
  ├─ /health       health check
  ├─ /text         JSON input → conversation/LLM adapter
  └─ /audio        PCM WAV → WhisperAdapter (starts whisper-cli)
                      └─ Whisper + optional Silero VAD → transcript
                                         │
                                         ▼
                         LlamaAdapter → llama-server (localhost:8080)
                                          └─ Qwen GGUF
                                         │
                                         ▼
                        { transcript, response_text, tool_calls }
                                         │
                                         ▼
                        Pepper displays requests and speaks text
```

**Process ownership matters:** `llama-server.exe` and the Python server are two processes you start independently. `whisper-cli.exe` is run **on demand** by Python for audio requests; it is **not** a permanently running speech server. Qwen does not run on Pepper's tablet.

## Repository layout

This layout reflects the original source package. Preserve the working local modifications made while resolving Gradle, manifest and Kotlin errors; do **not** overwrite them with the older starter ZIP.

```text
pepper-local-ai-poc/
├── README.md                      # This file
├── .gitignore
├── LICENSE                        # Add once the group chooses its license
├── WINDOWS_TEST_GUIDE.md          # Detailed Windows tests (review/update)
├── VALIDATION_REPORT.md           # Evidence and known limitations (update)
├── android-app/                   # Android Studio Arctic Fox project
│   ├── app/
│   │   ├── build.gradle
│   │   └── src/
│   │       ├── main/              # Shared Kotlin UI, HTTP client, manifest
│   │       ├── pepper/            # QiSDK robot integration and manifest
│   │       └── standalone/        # No-robot testing implementation
│   ├── build.gradle
│   ├── settings.gradle
│   ├── gradle.properties
│   └── gradle/wrapper/             # Gradle 7.0.2 wrapper configuration
├── backend/
│   ├── pepper_poc/
│   │   ├── server.py               # HTTP gateway, live/mock modes
│   │   └── pipeline.py             # Qwen/Whisper adapters and output parser
│   ├── test_client.py             # Text and WAV integration client
│   └── tests/                     # Python unit tests
└── windows/                       # Existing .cmd test helpers
```

Do **not** commit an entire locally installed `PepperTools/` directory into this repository. It is a machine-local dependency directory described below.

## Tested development stack

- **Host:** 64-bit Windows computer; the first trial used approximately **8 GB RAM**.
- **Python:** Python 3.10; the provided backend initially uses the **standard library**, so no backend `pip install` is required.
- **Android Studio:** **Arctic Fox 2020.3.1**.
- **Build:** Android Gradle Plugin **7.0.4**, Gradle **7.0.2**, Kotlin **1.5.31**, **JDK 11**.
- **Android SDK:** `minSdk 23`, `compileSdk 30`, `targetSdk 28` in the initial project; QiSDK **1.7.5** for the `pepper` flavor.
- **Inference:** Windows x64 `llama-server.exe`, Windows x64 `whisper-cli.exe`, Whisper tiny, Silero VAD, and a quantized Qwen GGUF model.

The original starter archive **did not contain** `android-app/gradlew`, `gradlew.bat`, or `gradle/wrapper/gradle-wrapper.jar`. If those have not yet been generated, the Gradle Wrapper is **not yet complete**. Commit all four wrapper files (`gradlew`, `gradlew.bat`, `.jar`, `.properties`) after generating them with Gradle 7.0.2 and JDK 11. Until then, use the team's installed Gradle 7.0.2 distribution or Android Studio configuration. Do not upgrade the project to Gradle 8 or a modern Android Gradle Plugin just to avoid this step.

## External runtimes and models (not stored in Git)

For the current Windows setup, keep the following structure **outside the cloned repository**:

```text
%USERPROFILE%\PepperTools\
├── llama\            # llama-server.exe AND its accompanying DLLs
├── whisper\          # whisper-cli.exe AND its accompanying DLLs
├── models\
│   ├── Qwen_Qwen3-0.6B-Q4_K_M.gguf       # validated baseline model
│   ├── ggml-tiny.bin                     # Whisper ASR
│   └── ggml-silero-v6.2.0.bin           # Silero VAD
├── audio\            # LOCAL ONLY: test WAV recordings
└── gradle\           # optional local Gradle distribution, not committed
```

Use the **actual executable paths on each teammate's PC**; release archives may put binaries in nested subdirectories. Don't move an EXE away from its accompanying DLLs.

Download runtimes from their official releases and models from their original distributions:

- [`llama.cpp` Windows releases](https://github.com/ggml-org/llama.cpp/releases)
- [`whisper.cpp` Windows releases](https://github.com/ggml-org/whisper.cpp/releases)
- [Qwen3-0.6B GGUF baseline](https://huggingface.co/bartowski/Qwen_Qwen3-0.6B-GGUF)
- [Qwen3.5-9B GGUF optional upgrade](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF)
- [Whisper models](https://huggingface.co/ggerganov/whisper.cpp)
- [Silero/whisper-vad models](https://huggingface.co/ggml-org/whisper-vad)
- [Microsoft Visual C++ Redistributable (if required)](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)

**Team convenience:** It is acceptable to make separate, versioned ZIP bundles of the exact tested **Windows EXEs and their required DLLs**, preferably as private GitHub Release assets rather than regular Git files, **after verifying provenance, included third-party licenses, and checksums**. Do not bundle arbitrary Windows system DLLs or the entire `PepperTools` folder. Record the upstream release/tag, archive name, SHA-256, architecture, and installation path in the release notes. The models are downloaded separately. See [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

A teammate can verify a binary or archive using:

```powershell
Get-FileHash 'C:\PATH\TO\DOWNLOADED_FILE.zip' -Algorithm SHA256
```

Compare the hash against the published team's manifest or an upstream checksum. A hash calculated only *after* downloading does not independently establish provenance.

## Quick start on Windows

All commands below are **PowerShell**, not Bash. Open the repository's root folder first. Replace paths and network addresses with those from your own computer. **Do not commit your LAN token or recordings.**

### 1. Run mock tests (no models or Pepper required)

```powershell
cd .\backend
py -3 -m unittest discover -s tests -v
```

Start the mock backend in one PowerShell window:

```powershell
py -3 -m pepper_poc.server
```

In another window:

```powershell
cd .\backend
Invoke-RestMethod 'http://127.0.0.1:8765/health'
py -3 test_client.py --text 'Hello Pepper'
```

The health endpoint should report `mode: mock`. Stop the mock server with **Ctrl+C** before starting live mode.

### 2. Start Qwen on the Windows computer

Use the GGUF you have installed. The baseline command is:

```powershell
$Tools = Join-Path $HOME 'PepperTools'
$LlamaExe = (Get-ChildItem "$Tools\llama" -Recurse -File -Filter 'llama-server.exe' |
    Select-Object -First 1).FullName

& $LlamaExe -m "$Tools\models\Qwen_Qwen3-0.6B-Q4_K_M.gguf" `
    -c 2048 --host 127.0.0.1 --port 8080
```

Keep this window running. Verify from a second terminal:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8080/health'
```

**Model upgrade:** You can substitute a supported larger GGUF without changing the Android application. A 9B Q4 model is **memory-intensive on an 8 GB Windows PC**, and should be treated as an experiment until response latency and RAM have been measured. A newer `llama.cpp` build may be required for Qwen3.5. Preserve a working baseline model for rollback.

### 3. Start the live Python backend

In a separate PowerShell window, from `backend/`:

```powershell
$Tools = Join-Path $HOME 'PepperTools'
$WhisperExe = (Get-ChildItem "$Tools\whisper" -Recurse -File -Filter 'whisper-cli.exe' |
    Select-Object -First 1).FullName
$env:PEPPER_POC_TOKEN = [guid]::NewGuid().ToString('N')
Write-Host "Enter this session token into Pepper: $env:PEPPER_POC_TOKEN"

py -3 -m pepper_poc.server --live `
    --host 0.0.0.0 --port 8765 `
    --token "$env:PEPPER_POC_TOKEN" `
    --llama-url 'http://127.0.0.1:8080' `
    --whisper-exe "$WhisperExe" `
    --whisper-model "$Tools\models\ggml-tiny.bin" `
    --vad-model "$Tools\models\ggml-silero-v6.2.0.bin"
```

Keep this window running. **Never open the Qwen server itself to the LAN**; it remains on `127.0.0.1:8080`. Port **8765** is reachable only over the **trusted local lab network** and should be restricted by the Windows Firewall to Pepper's IP, if practical. The POC uses **unencrypted HTTP** and a basic session token; it is **not safe to expose to the public internet**. Health requests do not require the token in this version.

### 4. Test the Windows backend

Open another PowerShell window, navigate to the repository's **`backend` folder** (e.g. `cd 'C:\PATH\TO\pepper-local-ai-poc\backend'`), and run:

```powershell
py -3 test_client.py --token 'PASTE_YOUR_SESSION_TOKEN' --text 'Hello Pepper'
py -3 test_client.py --token 'PASTE_YOUR_SESSION_TOKEN' `
    --wav "$HOME\PepperTools\audio\spoken.wav"
```

The WAV must be **16 kHz, mono, 16-bit PCM**, with a supported short duration. Expected output contains `transcript`, `response_text`, and `tool_calls`. If the backend returns HTTP 502, inspect the server terminal for `[BACKEND ERROR]`. If `response_text` is empty, check the model output / reasoning mode and the backend prompt and parser; don't treat empty text as a successful speech test.

### 5. Build and run the Android app

In **Android Studio Arctic Fox**, open **`android-app/`** (not the repository root). Select the appropriate variant:

- `standaloneDebug`: standalone UI test without QiSDK hardware.
- `pepperDebug`: install on an **authorized QiSDK-compatible Pepper tablet**.

Use **JDK 11**, **Gradle 7.0.2**, and the project's specified Android plugin versions. If a complete wrapper has been committed, from `android-app/` you can use:

```powershell
.\gradlew.bat :app:assemblePepperDebug
```

If the wrapper is still missing, use the explicitly installed Gradle 7.0.2 executable configured for JDK 11. The normal APK output is:

```text
android-app/app/build/outputs/apk/pepper/debug/app-pepper-debug.apk
```

To install directly when Android Studio deployment fails, use the Android SDK's `adb install -r` on the **correct authorized tablet**; for multiple devices, select the target with `adb -s SERIAL`.

**Keep the working fixes** from the lab build: the `tools:replace` declaration for conflicting QiSDK manifest attributes, and Kotlin backticks around the Java package segment `` `object` `` in the QiSDK `BodyLanguageOption` import. The initial starter ZIP predates those fixes.

### 6. Connect Pepper to the backend

1. Ensure Pepper and Windows are on the same **trusted local network**. Find the Windows IPv4 address with `ipconfig`.
2. In the Pepper application, enter `http://WINDOWS_IPV4:8765` (not `127.0.0.1`). Enter the **same session token** printed by the Python backend.
3. Confirm `Pepper robot focus gained` and test **Pepper's own speech** first.
4. Press **Test backend connection** and verify `mode: live`.
5. Send a **typed question**. Confirm that `Assistant text` is nonempty and Pepper audibly speaks it.
6. Try the **experimental 4-second audio** path; confirm transcript and spoken response. The code uses Android `AudioRecord`, and the precise physical microphone source has not been established.

**Physical gestures are not executed.** If the model returns a `gesture/greeting` tool call, the app displays the request only. Do not describe this as robot motion support.

## Quality gates for teammates

Before declaring the setup working on a new computer, record: (1) Python mock unit test results; (2) Qwen `/health` and a nonempty generated response; (3) direct Whisper WAV transcription; (4) `live` backend text and WAV responses; (5) Android `pepperDebug` build and robot focus; and (6) audible robot speech from an AI-generated sentence. Record actual versions, the model filename, latency, RAM consumption, and failures without including tokens or participant recordings.

## Security and research limitations

This is an educational laboratory prototype. It has no TLS, user accounts, production-grade authentication, rate limiting, persistent session-management guarantees, or consent/data-management workflow. The backend uses a temporary file for Whisper input and does not implement a user-data store; still, logs, PowerShell history and external processes can expose operational data. Do not expose it to the internet or process sensitive participant recordings without appropriate authorization and controls. Avoid saving participant audio in Git or public bug reports.

A **Qwen-generated tool request is not a safety authorization**. The current tool parser only permits a narrow demonstration request; actual physical movement must be separately designed and guarded.

## Credit, sources, and licensing

This minimal QiSDK app is **informed by**, but **not a copy or full port of**, the open-source Studerus et al. Pepper framework: [Studerus, Zhong and Vonschallen, *A Framework for Low-Latency, LLM-driven Multimodal Interaction on the Pepper Robot*](https://arxiv.org/abs/2603.21013); [their code](https://github.com/studerus/pepper-android-realtime-chat). If the team later incorporates Studerus source code, follow its applicable MIT attribution and notice requirements.

Other components are provided by their respective owners: [SoftBank/Aldebaran QiSDK](https://qisdk.softbankrobotics.com/), [`llama.cpp`](https://github.com/ggml-org/llama.cpp), [`whisper.cpp`](https://github.com/ggml-org/whisper.cpp), [Silero VAD](https://github.com/snakers4/silero-vad), and [Qwen](https://huggingface.co/Qwen). See their exact repository or model-card license terms before redistributing binaries or weights. In particular, Microsoft runtime DLLs are governed by their own redistribution terms. Do not imply that all assets share the same license.

**Project license:** The group should choose and add its own `LICENSE` file. Until one is added, do not label the entire repository as MIT merely because several upstream components use MIT.

## Contributions

Keep changes small and testable. For issues and pull requests, include the Windows/Python/Android/`llama.cpp`/`whisper.cpp` versions, whether the failure occurs in `mock` or `live` mode, the relevant command and **redacted** logs, and the smallest reproduction that does not contain credentials, private IP addresses, or participant audio.
