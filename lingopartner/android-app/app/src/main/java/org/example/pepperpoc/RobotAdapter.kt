package org.example.pepperpoc

import android.app.Activity

/** Hardware-specific bridge. Completion is essential for safe half-duplex listening. */
interface RobotAdapter {
    fun start(activity: Activity, report: (String) -> Unit)
    fun speak(text: String, report: (String) -> Unit, onComplete: (Boolean) -> Unit)
    fun stop(activity: Activity)
}
