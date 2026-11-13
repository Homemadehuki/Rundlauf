import re, pathlib, os

PLUGIN_SRC = r'''package de.rundlauf.app;

import android.Manifest;
import android.app.Activity;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.telephony.SmsManager;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import java.util.ArrayList;

@CapacitorPlugin(
    name = "RundlaufSms",
    permissions = { @Permission(strings = { Manifest.permission.SEND_SMS }, alias = "sms") }
)
public class RundlaufSmsPlugin extends Plugin {

    @PluginMethod
    public void send(PluginCall call) {
        if (getPermissionState("sms") != PermissionState.GRANTED) {
            requestPermissionForAlias("sms", call, "smsPermissionCallback");
            return;
        }
        doSend(call);
    }

    @PermissionCallback
    private void smsPermissionCallback(PluginCall call) {
        if (getPermissionState("sms") == PermissionState.GRANTED) {
            doSend(call);
        } else {
            call.reject("Keine SMS-Berechtigung");
        }
    }

    private void doSend(final PluginCall call) {
        final String to = call.getString("to");
        final String text = call.getString("text");
        if (to == null || text == null || to.isEmpty()) {
            call.reject("Empfaenger oder Text fehlt");
            return;
        }
        final Context ctx = getContext();
        try {
            SmsManager sm;
            if (Build.VERSION.SDK_INT >= 31) {
                sm = ctx.getSystemService(SmsManager.class);
            } else {
                sm = SmsManager.getDefault();
            }
            final ArrayList<String> parts = sm.divideMessage(text);
            final int n = parts.size();
            final String action = "de.rundlauf.app.SMS_SENT_" + System.nanoTime();
            final int[] done = new int[] { 0 };
            final boolean[] failed = new boolean[] { false };
            final boolean[] finished = new boolean[] { false };
            final Handler handler = new Handler(Looper.getMainLooper());
            final Runnable[] timeoutHolder = new Runnable[1];
            final BroadcastReceiver[] recHolder = new BroadcastReceiver[1];

            BroadcastReceiver rec = new BroadcastReceiver() {
                @Override
                public void onReceive(Context c, Intent i) {
                    int code = getResultCode();
                    if (code != Activity.RESULT_OK) {
                        failed[0] = true;
                    }
                    done[0]++;
                    if (done[0] >= n) {
                        handler.removeCallbacks(timeoutHolder[0]);
                        complete(ctx, recHolder[0], call, finished, failed[0] ? "SMS-Versand fehlgeschlagen (Code " + code + ")" : null);
                    }
                }
            };
            recHolder[0] = rec;
            timeoutHolder[0] = new Runnable() {
                @Override
                public void run() {
                    complete(ctx, recHolder[0], call, finished, "Zeitueberschreitung beim SMS-Versand");
                }
            };

            IntentFilter filter = new IntentFilter(action);
            if (Build.VERSION.SDK_INT >= 33) {
                ctx.registerReceiver(rec, filter, Context.RECEIVER_NOT_EXPORTED);
            } else {
                ctx.registerReceiver(rec, filter);
            }
            ArrayList<PendingIntent> sent = new ArrayList<PendingIntent>();
            for (int k = 0; k < n; k++) {
                Intent it = new Intent(action);
                it.setPackage(ctx.getPackageName());
                sent.add(PendingIntent.getBroadcast(ctx, k, it, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
            }
            handler.postDelayed(timeoutHolder[0], 90000);
            sm.sendMultipartTextMessage(to, null, parts, sent, null);
        } catch (Exception e) {
            call.reject("SMS-Fehler: " + e.getMessage());
        }
    }

    private void complete(Context ctx, BroadcastReceiver rec, PluginCall call, boolean[] finished, String error) {
        if (finished[0]) {
            return;
        }
        finished[0] = true;
        try {
            ctx.unregisterReceiver(rec);
        } catch (Exception ignored) {
        }
        if (error != null) {
            call.reject(error);
        } else {
            JSObject r = new JSObject();
            r.put("sent", true);
            call.resolve(r);
        }
    }
}
'''
STEP_SRC = r'''package de.rundlauf.app;

import android.Manifest;
import android.content.Context;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.os.Build;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

@CapacitorPlugin(
    name = "RundlaufSteps",
    permissions = { @Permission(strings = { Manifest.permission.ACTIVITY_RECOGNITION }, alias = "activity") }
)
public class RundlaufStepsPlugin extends Plugin implements SensorEventListener {

    private SensorManager sm;
    private Sensor sensor;
    private volatile float steps = -1;
    private boolean registered = false;

    @PluginMethod
    public void start(PluginCall call) {
        if (Build.VERSION.SDK_INT >= 29 && getPermissionState("activity") != PermissionState.GRANTED) {
            requestPermissionForAlias("activity", call, "stepPermCallback");
            return;
        }
        doStart(call);
    }

    @PermissionCallback
    private void stepPermCallback(PluginCall call) {
        if (Build.VERSION.SDK_INT >= 29 && getPermissionState("activity") != PermissionState.GRANTED) {
            call.reject("Keine Berechtigung fuer Schrittzaehler");
        } else {
            doStart(call);
        }
    }

    private void doStart(PluginCall call) {
        try {
            if (sm == null) {
                sm = (SensorManager) getContext().getSystemService(Context.SENSOR_SERVICE);
            }
            sensor = sm.getDefaultSensor(Sensor.TYPE_STEP_COUNTER);
            if (sensor == null) {
                call.reject("Kein Schrittzaehler im Geraet");
                return;
            }
            if (!registered) {
                registered = sm.registerListener(this, sensor, SensorManager.SENSOR_DELAY_NORMAL, 5000000);
            }
            JSObject r = new JSObject();
            r.put("started", registered);
            call.resolve(r);
        } catch (Exception e) {
            call.reject("Schrittzaehler-Fehler: " + e.getMessage());
        }
    }

    @PluginMethod
    public void get(PluginCall call) {
        JSObject r = new JSObject();
        r.put("available", registered && steps >= 0);
        r.put("steps", (double) steps);
        call.resolve(r);
    }

    @Override
    public void onSensorChanged(SensorEvent event) {
        if (event.values != null && event.values.length > 0) {
            steps = event.values[0];
        }
    }

    @Override
    public void onAccuracyChanged(Sensor sensor, int accuracy) {
    }
}
'''
root = pathlib.Path('android/app/src/main')
mf = root / 'AndroidManifest.xml'
s = mf.read_text()
perms = ['ACCESS_FINE_LOCATION','ACCESS_COARSE_LOCATION','POST_NOTIFICATIONS','FOREGROUND_SERVICE','FOREGROUND_SERVICE_LOCATION','WAKE_LOCK','SEND_SMS','ACTIVITY_RECOGNITION']
add = ''.join(f'    <uses-permission android:name="android.permission.{p}" />\n' for p in perms)
add += '    <uses-feature android:name="android.hardware.sensor.stepcounter" android:required="false" />\n'
add += '    <uses-feature android:name="android.hardware.telephony" android:required="false" />\n'
add += '    <queries>\n        <intent>\n            <action android:name="android.intent.action.TTS_SERVICE" />\n        </intent>\n    </queries>\n'
if 'xmlns:tools' not in s:
    s = s.replace('<manifest xmlns:android="http://schemas.android.com/apk/res/android"', '<manifest xmlns:android="http://schemas.android.com/apk/res/android" xmlns:tools="http://schemas.android.com/tools"', 1)
s = s.replace('<application', add + '    <application', 1) if 'FOREGROUND_SERVICE_LOCATION' not in s else s
svc = '        <service android:name="com.equimaps.capacitor_background_geolocation.BackgroundGeolocationService" android:foregroundServiceType="location" tools:replace="android:foregroundServiceType" />\n'
if 'BackgroundGeolocationService' not in s:
    s = s.replace('</application>', svc + '    </application>', 1)
mf.write_text(s)
sx = root / 'res/values/strings.xml'
t = sx.read_text()
if 'capacitor_background_geolocation_notification_channel_name' not in t:
    t = t.replace('</resources>', '    <string name="capacitor_background_geolocation_notification_channel_name">Rundlauf Navigation</string>\n</resources>')
    sx.write_text(t)
# feste Signatur, damit Updates ohne Deinstallation moeglich sind
if os.path.exists('rundlauf.keystore'):
    bg = pathlib.Path('android/app/build.gradle')
    g = bg.read_text()
    if 'rundlauf.keystore' not in g:
        sign = "\nandroid {\n    signingConfigs {\n        debug {\n            storeFile file('../../rundlauf.keystore')\n            storePassword 'rundlauf'\n            keyAlias 'rundlauf'\n            keyPassword 'rundlauf'\n        }\n    }\n"
        assert '\nandroid {\n' in g
        g = g.replace('\nandroid {\n', sign, 1)
        bg.write_text(g)
        print('signing patched')
print(mf.read_text())

# ---- eigenes SMS-Plugin (automatisches Senden im Hintergrund)
java_root = pathlib.Path('android/app/src/main/java')
mains = list(java_root.rglob('MainActivity.java'))
assert mains, 'MainActivity.java nicht gefunden'
main = mains[0]
pkg = re.search(r'^package\s+([\w.]+);', main.read_text(), re.M).group(1)
plugin_src = PLUGIN_SRC.replace('package de.rundlauf.app;', 'package ' + pkg + ';')
(main.parent / 'RundlaufSmsPlugin.java').write_text(plugin_src)
(main.parent / 'RundlaufStepsPlugin.java').write_text(STEP_SRC.replace('package de.rundlauf.app;', 'package ' + pkg + ';'))
main.write_text('package ' + pkg + ';\n\nimport android.os.Bundle;\nimport com.getcapacitor.BridgeActivity;\n\npublic class MainActivity extends BridgeActivity {\n    @Override\n    public void onCreate(Bundle savedInstanceState) {\n        registerPlugin(RundlaufSmsPlugin.class);\n        registerPlugin(RundlaufStepsPlugin.class);\n        super.onCreate(savedInstanceState);\n    }\n}\n')
print('SMS-Plugin eingebaut in', pkg)
