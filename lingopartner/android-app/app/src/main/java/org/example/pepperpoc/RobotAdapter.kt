package org.example.pepperpoc

import android.app.Activity

/** The only hardware-specific interface used by the shared Android UI. */
interface RobotAdapter {
    fun start(activity: Activity, report: (String) -> Unit)
    fun speak(text: String, report: (String) -> Unit)
    fun stop(activity: Activity)
}
