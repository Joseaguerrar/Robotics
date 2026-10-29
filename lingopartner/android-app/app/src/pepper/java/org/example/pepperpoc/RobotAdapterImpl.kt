package org.example.pepperpoc

import android.app.Activity
import com.aldebaran.qi.sdk.QiSDK
import com.aldebaran.qi.sdk.RobotLifecycleCallbacks
import com.aldebaran.qi.sdk.builder.SayBuilder
import com.aldebaran.qi.sdk.`object`.conversation.BodyLanguageOption
import com.aldebaran.qi.sdk.QiContext

/** Minimal QiSDK adapter. No physical gesture commands in this POC. */
class RobotAdapterImpl : RobotAdapter, RobotLifecycleCallbacks {
    @Volatile private var robotContext: QiContext? = null
    private var reporter: ((String) -> Unit)? = null

    override fun start(activity: Activity, report: (String) -> Unit) {
        reporter = report
        QiSDK.register(activity, this)
        report("QiSDK lifecycle registered; waiting for robot focus")
    }

    override fun onRobotFocusGained(qiContext: QiContext) {
        robotContext = qiContext
        reporter?.invoke("Pepper robot focus gained")
    }
    override fun onRobotFocusLost() {
        robotContext = null
        reporter?.invoke("Pepper robot focus lost")
    }
    override fun onRobotFocusRefused(reason: String) {
        robotContext = null
        reporter?.invoke("Pepper robot focus refused: $reason")
    }

    override fun speak(text: String, report: (String) -> Unit,
                       onComplete: (Boolean) -> Unit) {
        val qiContext = robotContext
        if (qiContext == null) {
            report("Cannot speak: QiSDK robot focus unavailable")
            onComplete(false)
            return
        }
        Thread {
            var success = false
            try {
                SayBuilder.with(qiContext).withText(text)
                    .withBodyLanguageOption(BodyLanguageOption.DISABLED).build().run()
                report("QiSDK Say completed")
                success = true
            } catch (e: Exception) {
                report("QiSDK Say failed: ${e.message}")
            } finally {
                // Do not reopen microphone until speech has actually completed.
                onComplete(success)
            }
        }.start()
    }

    override fun stop(activity: Activity) {
        QiSDK.unregister(activity, this)
        robotContext = null
    }
}
