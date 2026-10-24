package org.example.pepperpoc

import android.app.Activity
import com.aldebaran.qi.sdk.QiSDK
import com.aldebaran.qi.sdk.RobotLifecycleCallbacks
import com.aldebaran.qi.sdk.builder.SayBuilder
import com.aldebaran.qi.sdk.`object`.conversation.BodyLanguageOption
import com.aldebaran.qi.sdk.QiContext

/** QiSDK integration: minimal official-lifecycle pattern, not a Studerus source port. */
class RobotAdapterImpl : RobotAdapter, RobotLifecycleCallbacks {
    @Volatile private var robotContext: QiContext? = null
    private var report: ((String) -> Unit)? = null

    override fun start(activity: Activity, report: (String) -> Unit) {
        this.report = report
        QiSDK.register(activity, this)
        report("QiSDK lifecycle registered; waiting for robot focus")
    }
    override fun onRobotFocusGained(qiContext: QiContext) {
        robotContext = qiContext
        report?.invoke("Pepper robot focus gained")
    }
    override fun onRobotFocusLost() {
        robotContext = null
        report?.invoke("Pepper robot focus lost")
    }
    override fun onRobotFocusRefused(reason: String) {
        robotContext = null
        report?.invoke("Pepper robot focus refused: $reason")
    }
    override fun speak(text: String, report: (String) -> Unit) {
        val context = robotContext
        if (context == null) {
            report("Cannot speak: QiSDK robot focus not available")
            return
        }
        Thread {
            try {
                // Disable automatic body movements during first hardware trials.
                SayBuilder.with(context).withText(text)
                    .withBodyLanguageOption(BodyLanguageOption.DISABLED).build().run()
                report("QiSDK Say completed")
            } catch (e: Exception) {
                report("QiSDK Say failed: ${e.message}")
            }
        }.start()
    }
    override fun stop(activity: Activity) {
        QiSDK.unregister(activity, this)
        robotContext = null
    }
}
