package app.orbit.dial

import android.service.notification.NotificationListenerService

/** Exists only so MediaSessionManager.getActiveSessions() lets us reach the real
 *  music player (forwarding play/pause/next while Orbit owns the media buttons). */
class OrbitNotificationListener : NotificationListenerService()
