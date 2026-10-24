package org.example.pepperpoc

import android.app.Activity

/** Simulates robot actions to validate UI & networking without a Pepper. */
class RobotAdapterImpl : RobotAdapter {
    override fun start(activity: Activity, report: (String) -> Unit) {
        report("STANDALONE simulator ready (no robot SDK/hardware)")
    }
    override fun speak(text: String, report: (String) -> Unit) {
        report("SIMULATED SPEECH: $text")
    }
    override fun stop(activity: Activity) {}
}
