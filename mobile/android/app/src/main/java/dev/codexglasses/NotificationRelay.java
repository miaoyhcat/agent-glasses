package dev.codexglasses;
import android.service.notification.*;
import android.content.Context;
import java.util.*;

/** Explicit opt-in, per-package allowlist. No network access is used here. */
public class NotificationRelay extends NotificationListenerService {
    public void onNotificationPosted(StatusBarNotification event){
        android.content.SharedPreferences prefs=getSharedPreferences("settings",Context.MODE_PRIVATE);
        Set<String> allow=prefs.getStringSet("notification_packages",Collections.emptySet());
        if(!allow.contains(event.getPackageName()))return;
        android.app.Notification n=event.getNotification();
        if(n.visibility==android.app.Notification.VISIBILITY_SECRET)return;
        CharSequence title=n.extras.getCharSequence(android.app.Notification.EXTRA_TITLE,"");
        // Only app and title. Body/OTP/password text is deliberately not retained.
        String summary=event.getPackageName()+" · "+title;
        prefs.edit().putString("latest_notification",summary.substring(0,Math.min(120,summary.length()))).apply();
    }
}
