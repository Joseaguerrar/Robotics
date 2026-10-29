package org.example.pepperpoc

import android.app.Activity

/** Simulator: no physical speech or QiSDK access. */
class RobotAdapterImpl : RobotAdapter {
    override fun start(activity: Activity, report: (String) -> Unit) {
        report("STANDALONE simulator ready")
    }
    override fun speak(text: String, report: (String) -> Unit,
                       onComplete: (Boolean) -> Unit) {
        report("SIMULATED SPEECH: $text")
        onComplete(true)
    }
    override fun stop(activity: Activity) {}
}
