package com.veronic.guardbox

import android.app.Application
import com.veronic.guardbox.notification.NotificationHelper

class GuardBoxApp : Application() {

    override fun onCreate() {
        super.onCreate()
        // Initialize dedicated high-importance notification channel
        NotificationHelper.createNotificationChannel(this)
    }
}
