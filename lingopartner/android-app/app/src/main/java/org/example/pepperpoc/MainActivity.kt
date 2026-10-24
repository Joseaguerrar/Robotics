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
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

/**
 * First-day POC. Two build flavors: Pepper QiSDK and simulator.
 * No streaming; audio recording is experimental and uses Android AudioRecord.
 */
class MainActivity : Activity() {
    private val robot: RobotAdapter = RobotAdapterImpl()
    private lateinit var host: EditText
    private lateinit var token: EditText
    private lateinit var question: EditText
    private lateinit var logArea: TextView
    private var isBusy = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val scroll = ScrollView(this)
        val layout = LinearLayout(this)
        layout.orientation = LinearLayout.VERTICAL
        val pad = (14 * resources.displayMetrics.density).toInt()
        layout.setPadding(pad, pad, pad, pad)
        scroll.addView(layout)
        setContentView(scroll)

        val heading = TextView(this)
        heading.text = "Pepper Arctic Fox POC — independent tests first"
        heading.textSize = 21f
        layout.addView(heading)
        val help = TextView(this)
        help.text = "Local backend URL uses the COMPUTER IP (not 127.0.0.1 on the robot). " +
            "Speech uses QiSDK only after robot focus is gained."
        layout.addView(help)

        host = field(layout, "http://192.168.1.10:8765", "Backend address")
        token = field(layout, "", "LAN session token (enter on each run)")
        question = field(layout, "Hello Pepper!", "Typed test question")
        addButton(layout, "1. Check app / robot focus") { log("App UI responding") }
        addButton(layout, "2. Test Pepper's own speech") {
            robot.speak("Hello human. This is a robot speech test.") { log(it) }
        }
        addButton(layout, "3. Test backend connection") { runAsync { getHealth() } }
        addButton(layout, "4. Send typed question to AI") { runAsync { askText() } }
        addButton(layout, "5. Record 4 seconds and send WAV (EXPERIMENTAL)") {
            if (Build.VERSION.SDK_INT >= 23 && checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 19)
            } else runAsync { askAudio() }
        }
        logArea = TextView(this)
        logArea.textSize = 14f
        logArea.setPadding(0, pad, 0, pad)
        logArea.text = "Test log:\n"
        layout.addView(logArea)
        robot.start(this) { log(it) }
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
    private fun addButton(layout: LinearLayout, label: String, callback: () -> Unit) {
        val button = Button(this)
        button.text = label
        button.setOnClickListener { callback() }
        layout.addView(button)
    }
    private fun log(text: String) {
        runOnUiThread {
            if (::logArea.isInitialized) logArea.append("\n" + text)
        }
    }
    private fun runAsync(block: () -> Unit) {
        if (isBusy) { log("A test is already running"); return }
        isBusy = true
        Thread {
            try { block() }
            catch (e: Exception) { log("ERROR: ${e.javaClass.simpleName}: ${e.message}") }
            finally { isBusy = false }
        }.start()
    }
    private fun url(path: String): String {
        val base = host.text.toString().trim().trimEnd('/')
        require(base.startsWith("http://")) { "For this local POC enter http://COMPUTER_IP:8765" }
        return base + path
    }
    private fun call(path: String, data: ByteArray?, contentType: String): JSONObject {
        val connection = URL(url(path)).openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 6000
            connection.readTimeout = 120000
            connection.setRequestProperty("X-Session-Token", token.text.toString())
            if (data != null) {
                connection.requestMethod = "POST"
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", contentType)
                connection.outputStream.use { it.write(data) }
            }
            val stream = if (connection.responseCode in 200..299)
                connection.inputStream else connection.errorStream
            val payload = stream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            if (connection.responseCode !in 200..299) error("HTTP ${connection.responseCode}: $payload")
            return JSONObject(payload)
        } finally { connection.disconnect() }
    }
    private fun getHealth() {
        val health = call("/health", null, "application/json")
        log("Backend health: $health")
    }
    private fun askText() {
        val text = question.text.toString()
        val reply = call("/text", JSONObject().put("text", text).toString().toByteArray(Charsets.UTF_8), "application/json")
        processReply(reply)
    }
    private fun askAudio() {
        log("Recording 4 seconds using Android tablet AudioRecord (robot head microphones NOT verified)")
        val wav = captureWav()
        val reply = call("/audio", wav, "audio/wav")
        processReply(reply)
    }
    private fun processReply(result: JSONObject) {
        log("Transcript: " + result.optString("transcript", ""))
        val spoken = result.optString("response_text", "")
        log("Assistant text: $spoken")
        val calls = result.optJSONArray("tool_calls")
        if (calls != null && calls.length() > 0) {
            log("Tool request(s): $calls — DISPLAYED ONLY, no motor actions implemented")
        }
        if (spoken.isNotBlank()) robot.speak(spoken) { log(it) }
    }

    private fun captureWav(): ByteArray {
        val rate = 16000
        val minSize = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT)
        require(minSize > 0) { "Android AudioRecord 16 kHz mono unavailable" }
        val recorder = AudioRecord(MediaRecorder.AudioSource.MIC, rate,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, minSize * 2)
        require(recorder.state == AudioRecord.STATE_INITIALIZED) { "AudioRecord failed to initialize" }
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
    private fun pcmToWav(pcm: ByteArray, rate: Int): ByteArray {
        val out = ByteArrayOutputStream()
        fun ascii(s: String) { out.write(s.toByteArray(Charsets.US_ASCII)) }
        fun shortLE(n: Int) { out.write(n and 255); out.write((n shr 8) and 255) }
        fun intLE(n: Int) { for (i in 0..3) out.write((n shr (8 * i)) and 255) }
        ascii("RIFF"); intLE(pcm.size + 36); ascii("WAVE")
        ascii("fmt "); intLE(16); shortLE(1); shortLE(1)
        intLE(rate); intLE(rate * 2); shortLE(2); shortLE(16)
        ascii("data"); intLE(pcm.size); out.write(pcm)
        return out.toByteArray()
    }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 19 && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            runAsync { askAudio() }
        } else log("Audio permission denied")
    }
    override fun onDestroy() { robot.stop(this); super.onDestroy() }
}
