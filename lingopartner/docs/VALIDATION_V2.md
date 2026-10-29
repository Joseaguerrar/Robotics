# Validation report — generated upgrade, 2026-10-26

## Executed

- Python `unittest discover -s tests -q`: **11/11 PASS** in the authoring Linux container.
- Test coverage: model parser's gesture allowlist, WAV format, HTTP mock text/audio,
  session memory, isolation, reset, simulated naming follow-ups, SQLite reopen,
  aggregate learner progress, HTTP progress APIs, invalid session IDs, rejection
  of empty model results, and token authentication.
- Synthetic audio-energy VAD test: **PASS** (silent frames → simulated voice → 900 ms silence produced a valid RIFF WAV buffer), using JVM Android API stubs. This is not a real-microphone test.
- Kotlin syntax check: `kotlinc` 1.9 compiled the *Pepper-flavored* Kotlin sources
  against small **locally written interface stubs** for Android and QiSDK. This catches
  ordinary Kotlin syntax errors; it does **not** check real Android/QiSDK binary
  compatibility or substitute for an Arctic Fox build.

## Not executed

- Actual Android Studio Arctic Fox + JDK 11 + QiSDK 1.7.5 Gradle build.
- Install/run on a Pepper tablet, QiSDK robot focus and SayBuilder completion callbacks.
- Continuous microphone behavior with a real mic, thresholds for quiet/noisy rooms.
- Actual Windows `llama-server` (Qwen 0.6B or 9B), whisper-cli, Silero VAD and the
  full end-to-end hands-free integration.
- Production authentication, encryption, concurrent robots or privacy audit.

**Do not mark Android/hardware milestones as passed until validated on the actual robot.**
