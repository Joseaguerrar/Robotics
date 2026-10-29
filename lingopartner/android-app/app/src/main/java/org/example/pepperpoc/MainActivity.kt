package org.example.pepperpoc

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Pepper Local AI v2: session memory + opt-in hands-free turns.
 * Uses the existing /text and /audio HTTP endpoints, without a WebSocket.
 * Automatic speech segmentation is simple AUDIO ENERGY, not a wake word.
 * No automatic camera or motors. Tested compilation on Pepper still required.
 */
class MainActivity : Activity() {
    private val robot: RobotAdapter = RobotAdapterImpl()
    private lateinit var host: EditText
    private lateinit var token: EditText
    private lateinit var question: EditText
    private lateinit var logArea: TextView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private val manualBusy = AtomicBoolean(false)
    private val microphone = AudioCaptureManager()
    @Volatile private var listeningEnabled = false
    @Volatile private var destroyed = false
    @Volatile private var autoThread: Thread? = null
    private lateinit var sessionId: String

    private data class NetworkConfig(val base: String, val token: String,
                                     val sessionId: String)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        sessionId = getPreferences(MODE_PRIVATE).getString("session_id", null)
            ?: UUID.randomUUID().toString().replace("-", "").also {
                getPreferences(MODE_PRIVATE).edit().putString("session_id", it).apply()
            }
        val scroll = ScrollView(this)
        val layout = LinearLayout(this)
        layout.orientation = LinearLayout.VERTICAL
        val pad = (14 * resources.displayMetrics.density).toInt()
        layout.setPadding(pad, pad, pad, pad)
        scroll.addView(layout)
        setContentView(scroll)

        val heading = TextView(this)
        heading.text = "Pepper Local AI — Conversational POC"
        heading.textSize = 21f
        layout.addView(heading)
        val instructions = TextView(this)
        instructions.text = "1) Enter Windows LAN IP + token. 2) Test speech and backend. " +
            "3) Start listening with permission. Stop before leaving. " +
            "Audio is not stored; text memory is stored only if Windows backend uses --db-path."
        layout.addView(instructions)
        host = field(layout, "http://192.168.1.10:8765", "Backend URL")
        token = field(layout, "", "LAN session token")
        token.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        question = field(layout, "Hello Pepper!", "Typed question")

        addButton(layout, "1. Check app / QiSDK robot focus") { log("App UI responding") }
        addButton(layout, "2. Test Pepper speech") {
            if (listeningEnabled) { log("Stop listening first"); return@addButton }
            robot.speak("Hello human. This is a robot speech test.", ::log) { success ->
                log("Fixed speech finished: $success")
            }
        }
        addButton(layout, "3. Test backend connection") {
            val cfg = currentConfig()
            runManual { log("Health: ${call(cfg, "/health", null, "application/json")}") }
        }
        addButton(layout, "4. Send typed question") {
            val cfg = currentConfig()
            val utterance = question.text.toString()
            runManual { processReply(call(cfg, "/text", JSONObject().put("text", utterance)
                .toString().toByteArray(Charsets.UTF_8), "application/json")) }
        }
        addButton(layout, "5. Manual 4-second WAV test") {
            if (listeningEnabled) { log("Stop listening first"); return@addButton }
            if (!hasMicPermission()) {
                requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 19)
            } else manualAudio()
        }
        startButton = addButton(layout, "6. Start hands-free listening (energy VAD)") {
            if (!hasMicPermission()) {
                requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 20)
            } else startListening()
        }
        stopButton = addButton(layout, "7. Stop hands-free listening") { stopListening() }
        stopButton.isEnabled = false
        addButton(layout, "8. Reset this conversation's memory") {
            if (listeningEnabled || manualBusy.get()) {
                log("Stop listening and wait for current request to finish before resetting")
                return@addButton
            }
            val cfg = currentConfig()
            runManual {
                val response = call(cfg, "/session/reset", "{}".toByteArray(), "application/json")
                log("Memory reset: $response")
            }
        }
        logArea = TextView(this)
        logArea.textSize = 14f
        logArea.setPadding(0, pad, 0, pad)
        logArea.text = "Test log (session ${sessionId.take(8)}…):\n"
        layout.addView(logArea)
        robot.start(this, ::log)
    }

    private fun field(layout: LinearLayout, sample: String, hint: String): EditText {
        val input = EditText(this)
        input.hint = hint
        input.setSingleLine(true)
        input.setText(sample)
        input.inputType = InputType.TYPE_CLASS_TEXT
        layout.addView(input)
        return input
    }

    private fun addButton(layout: LinearLayout, label: String, callback: () -> Unit): Button {
        val button = Button(this)
        button.text = label
        button.setOnClickListener { callback() }
        layout.addView(button)
        return button
    }

    private fun hasMicPermission(): Boolean = Build.VERSION.SDK_INT < 23 ||
        checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun log(message: String) {
        if (!destroyed) runOnUiThread {
            if (!destroyed && ::logArea.isInitialized) logArea.append("\n" + message)
        }
    }

    private fun currentConfig(): NetworkConfig {
        // Snapshot UI state on the UI thread. Worker threads never read EditText.
        val base = host.text.toString().trim().trimEnd('/')
        require(base.startsWith("http://")) { "Enter http://WINDOWS_IP:8765" }
        return NetworkConfig(base, token.text.toString(), sessionId)
    }

    private fun call(cfg: NetworkConfig, path: String, data: ByteArray?, contentType: String): JSONObject {
        val connection = URL(cfg.base + path).openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 6000
            connection.readTimeout = 140000
            connection.setRequestProperty("X-Session-Token", cfg.token)
            connection.setRequestProperty("X-Session-Id", cfg.sessionId)
            connection.setRequestProperty("Cache-Control", "no-store")
            if (data != null) {
                connection.requestMethod = "POST"
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", contentType)
                connection.outputStream.use { it.write(data) }
            }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val payload = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
            if (code !in 200..299) error("HTTP $code: $payload")
            return JSONObject(payload)
        } finally {
            connection.disconnect()
        }
    }

    private fun runManual(action: () -> Unit) {
        if (listeningEnabled) { log("Stop hands-free listening before running manual tests"); return }
        if (!manualBusy.compareAndSet(false, true)) { log("Another test is running"); return }
        Thread {
            try { action() }
            catch (e: Exception) { log("ERROR: ${e.javaClass.simpleName}: ${e.message}") }
            finally { manualBusy.set(false) }
        }.start()
    }

    private fun manualAudio() {
        val cfg = currentConfig()
        runManual {
            log("Recording 4 seconds with Android AudioRecord")
            val wav = captureFixedFourSeconds()
            processReply(call(cfg, "/audio", wav, "audio/wav"))
        }
    }

    private fun processReply(result: JSONObject) {
        log("Transcript: ${result.optString("transcript", "")}")
        log("Memory turns: ${result.optInt("history_turns", -1)}")
        val spoken = result.optString("response_text", "").trim()
        log("Assistant text: $spoken")
        val calls = result.optJSONArray("tool_calls")
        if (calls != null && calls.length() > 0) log("Tool requests displayed only: $calls")
        if (spoken.isEmpty()) error("Empty response_text; cannot speak")
        val latch = CountDownLatch(1)
        var success = false
        robot.speak(spoken, ::log) { ok -> success = ok; latch.countDown() }
        // If speech never completes, NEVER automatically reopen mic.
        if (!latch.await(90, TimeUnit.SECONDS)) error("QiSDK speech completion timeout; hands-free stopped")
        if (!success) error("QiSDK speech failed or robot focus unavailable")
    }

    private fun startListening() {
        if (listeningEnabled) return
        if (manualBusy.get() || autoThread?.isAlive == true) {
            log("Another operation is still running")
            return
        }
        if (!hasMicPermission()) { log("Microphone permission required"); return }
        val cfg = currentConfig()
        listeningEnabled = true
        startButton.isEnabled = false
        stopButton.isEnabled = true
        log("Hands-free ON; speak near the tablet. No wake-word filtering. Stop when not in use.")
        autoThread = Thread {
            try {
                while (listeningEnabled && !destroyed) {
                    val wav = microphone.awaitUtterance(
                        { !listeningEnabled || destroyed }, ::log)
                    if (!listeningEnabled || destroyed) break
                    if (wav == null) continue
                    log("PROCESSING (${wav.size} WAV bytes); mic CLOSED")
                    val reply = call(cfg, "/audio", wav, "audio/wav")
                    if (!listeningEnabled || destroyed) break
                    log("SPEAKING; mic CLOSED")
                    processReply(reply) // blocks until QiSDK speech callback
                    if (listeningEnabled && !destroyed) log("Turn finished; resuming listening")
                }
            } catch (e: Exception) {
                if (!destroyed && listeningEnabled)
                    log("Hands-free stopped after error: ${e.javaClass.simpleName}: ${e.message}")
            } finally {
                listeningEnabled = false
                microphone.stop()
                runOnUiThread {
                    if (!destroyed) {
                        startButton.isEnabled = true
                        stopButton.isEnabled = false
                        log("Hands-free OFF")
                    }
                }
            }
        }.also { it.start() }
    }

    private fun stopListening() {
        listeningEnabled = false
        microphone.stop()
        // Does not interrupt speech that is already in progress; no new
        // microphone capture will begin after the current operation finishes.
        log("Stop requested; waiting for capture/request/speech to settle")
    }

    private fun captureFixedFourSeconds(): ByteArray {
        val rate = 16000
        val minSize = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT)
        require(minSize > 0) { "16kHz microphone unavailable" }
        val recorder = AudioRecord(MediaRecorder.AudioSource.MIC, rate,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, minSize * 2)
        require(recorder.state == AudioRecord.STATE_INITIALIZED) { "AudioRecord init failed" }
        val output = ByteArrayOutputStream()
        val chunk = ByteArray(minSize)
        try {
            recorder.startRecording()
            var remaining = rate * 2 * 4
            while (remaining > 0) {
                val count = recorder.read(chunk, 0, minOf(chunk.size, remaining))
                if (count <= 0) error("AudioRecord read error: $count")
                output.write(chunk, 0, count)
                remaining -= count
            }
        } finally {
            try { recorder.stop() } catch (_: Exception) {}
            recorder.release()
        }
        return pcmToWav(output.toByteArray(), rate)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>,
                                            grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (grantResults.firstOrNull() != PackageManager.PERMISSION_GRANTED) {
            log("Microphone permission denied")
            return
        }
        if (requestCode == 19) manualAudio()
        if (requestCode == 20) startListening()
    }

    override fun onPause() {
        stopListening() // No covert listening in the background.
        super.onPause()
    }

    override fun onDestroy() {
        destroyed = true
        stopListening()
        robot.stop(this)
        super.onDestroy()
    }
}
