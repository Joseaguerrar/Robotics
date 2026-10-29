package org.example.pepperpoc

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.ByteArrayOutputStream
import java.util.ArrayDeque
import kotlin.math.max
import kotlin.math.sqrt

/**
 * Opt-in hands-free audio capture. Detects approximate utterance boundaries using
 * short-time audio energy (NOT neural Silero VAD). The completed 16 kHz mono WAV
 * is sent to the EXISTING /audio endpoint, where Whisper uses Silero.
 *
 * The recorder is always stopped and released before the network request,
 * ASR, LLM, and Pepper speech. Therefore Pepper never listens to itself here.
 */
class AudioCaptureManager {
    companion object {
        const val RATE = 16000
        const val FRAME_SAMPLES = 320  // 20 ms
    }

    @Volatile private var recorder: AudioRecord? = null

    fun stop() {
        // Best effort to unblock AudioRecord.read on the capture thread.
        try { recorder?.stop() } catch (_: Exception) {}
    }

    fun awaitUtterance(cancelled: () -> Boolean, status: (String) -> Unit): ByteArray? {
        val minBuffer = AudioRecord.getMinBufferSize(
            RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        require(minBuffer > 0) { "16kHz microphone unavailable" }
        val audio = AudioRecord(MediaRecorder.AudioSource.MIC, RATE,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
            max(minBuffer * 2, FRAME_SAMPLES * 4))
        require(audio.state == AudioRecord.STATE_INITIALIZED) { "AudioRecord initialization failed" }
        recorder = audio
        val detector = EnergySegmenter()
        val buffer = ShortArray(FRAME_SAMPLES)
        status("LISTENING — audio-energy detection active")
        try {
            audio.startRecording()
            while (!cancelled()) {
                // short[] read matches ENCODING_PCM_16BIT, available on API 23.
                val size = audio.read(buffer, 0, buffer.size)
                if (size <= 0) {
                    if (cancelled()) return null
                    throw IllegalStateException("AudioRecord.read returned $size")
                }
                val wasSpeaking = detector.inSpeech
                val pcm = detector.accept(buffer, size)
                if (!wasSpeaking && detector.inSpeech) status("SPEECH DETECTED")
                if (pcm != null) return pcmToWav(pcm)
            }
            return null
        } finally {
            try { audio.stop() } catch (_: Exception) {}
            audio.release()
            if (recorder === audio) recorder = null
        }
    }
}

/** No audio is written to disk; silence/noise tuning is environment-dependent. */
internal class EnergySegmenter {
    private val preRoll = ArrayDeque<ByteArray>()
    private val output = ByteArrayOutputStream()
    var inSpeech = false
        private set
    private var noiseLevel = 160.0
    private var consecutiveLoud = 0
    private var voiced = 0
    private var silent = 0
    private var elapsed = 0

    fun accept(samples: ShortArray, count: Int): ByteArray? {
        if (count <= 0) return null
        var energy = 0.0
        val bytes = ByteArray(count * 2)
        for (i in 0 until count) {
            val s = samples[i].toInt()
            energy += s.toDouble() * s
            bytes[2 * i] = (s and 255).toByte()
            bytes[2 * i + 1] = ((s shr 8) and 255).toByte()
        }
        val rms = sqrt(energy / count)
        val threshold = max(350.0, noiseLevel * 3.0)
        val loud = rms > threshold
        if (!inSpeech) {
            // Keep ~300 ms before speech begins, to avoid cutting first sounds.
            preRoll.addLast(bytes)
            while (preRoll.size > 15) preRoll.removeFirst()
            if (loud) consecutiveLoud++ else consecutiveLoud = 0
            if (!loud) noiseLevel = (noiseLevel * 0.98 + rms * 0.02).coerceAtMost(3000.0)
            if (consecutiveLoud >= 3) {
                inSpeech = true
                for (chunk in preRoll) output.write(chunk)
                preRoll.clear()
                voiced = 3
                elapsed = 3
                silent = 0
            }
            return null
        }
        output.write(bytes)
        elapsed++
        if (loud) {
            voiced++
            silent = 0
        } else {
            silent++
        }
        // 900 ms trailing silence, or ~12 s hard maximum.
        if (silent >= 45 || elapsed >= 600) {
            val result = output.toByteArray()
            if (voiced >= 12) return result
            // Ignore ultra-short noises, resume detecting speech.
            inSpeech = false
            voiced = 0
            silent = 0
            elapsed = 0
            consecutiveLoud = 0
            output.reset()
        }
        return null
    }
}

internal fun pcmToWav(pcm: ByteArray, rate: Int = 16000): ByteArray {
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
