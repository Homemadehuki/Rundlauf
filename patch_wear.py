import pathlib, re

PKG = 'de.rundlauf.app'
android = pathlib.Path('android')
java_root = android / 'app/src/main/java'
main = list(java_root.rglob('MainActivity.java'))[0]
pkg = re.search(r'^package\s+([\w.]+);', main.read_text(), re.M).group(1)
assert pkg == PKG, pkg

# ---------------- Handy-Seite: Plugin + Empfaenger-Service ----------------
PHONE_PLUGIN = '''package %PKG%;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "RundlaufWatch")
public class RundlaufWatchPlugin extends Plugin {
    static volatile RundlaufWatchPlugin instance;
    static volatile int lastBpm = -1;
    static volatile long lastT = 0;

    @Override
    public void load() {
        instance = this;
    }

    static void push(int bpm) {
        lastBpm = bpm;
        lastT = System.currentTimeMillis();
        RundlaufWatchPlugin p = instance;
        if (p != null) {
            JSObject o = new JSObject();
            o.put("bpm", bpm);
            o.put("t", lastT);
            p.notifyListeners("hr", o);
        }
    }

    @PluginMethod
    public void last(PluginCall call) {
        JSObject o = new JSObject();
        o.put("bpm", lastBpm);
        o.put("t", lastT);
        call.resolve(o);
    }
}
'''

PHONE_SERVICE = '''package %PKG%;

import com.google.android.gms.wearable.MessageEvent;
import com.google.android.gms.wearable.WearableListenerService;

public class RundlaufWatchService extends WearableListenerService {
    @Override
    public void onMessageReceived(MessageEvent ev) {
        if ("/rundlauf/hr".equals(ev.getPath())) {
            try {
                String s = new String(ev.getData(), "UTF-8");
                int bpm = Integer.parseInt(s.trim());
                RundlaufWatchPlugin.push(bpm);
            } catch (Exception ignored) {
            }
        }
    }
}
'''
d = main.parent
(d / 'RundlaufWatchPlugin.java').write_text(PHONE_PLUGIN.replace('%PKG%', pkg))
(d / 'RundlaufWatchService.java').write_text(PHONE_SERVICE.replace('%PKG%', pkg))

m = main.read_text()
if 'RundlaufWatchPlugin' not in m:
    m = m.replace('registerPlugin(RundlaufSmsPlugin.class);', 'registerPlugin(RundlaufSmsPlugin.class);\n        registerPlugin(RundlaufWatchPlugin.class);', 1)
    main.write_text(m)

mf = android / 'app/src/main/AndroidManifest.xml'
s = mf.read_text()
if 'RundlaufWatchService' not in s:
    svc = ('        <service android:name="%s.RundlaufWatchService" android:exported="true">\n'
           '            <intent-filter>\n'
           '                <action android:name="com.google.android.gms.wearable.MESSAGE_RECEIVED" />\n'
           '                <data android:scheme="wear" android:host="*" android:pathPrefix="/rundlauf" />\n'
           '            </intent-filter>\n'
           '        </service>\n') % pkg
    s = s.replace('</application>', svc + '    </application>', 1)
    mf.write_text(s)

g = android / 'app/build.gradle'
t = g.read_text()
if 'play-services-wearable' not in t:
    assert '\ndependencies {\n' in t
    t = t.replace('\ndependencies {\n', "\ndependencies {\n    implementation 'com.google.android.gms:play-services-wearable:18.2.0'\n", 1)
    g.write_text(t)

# ---------------- Uhren-Modul ----------------
wear = android / 'wear'
(wear / 'src/main/java' / pkg.replace('.', '/') / 'wear').mkdir(parents=True, exist_ok=True)

(wear / 'build.gradle').write_text('''apply plugin: 'com.android.application'

android {
    namespace "%PKG%.wear"
    compileSdk rootProject.ext.compileSdkVersion
    defaultConfig {
        applicationId "%PKG%"
        minSdk 30
        targetSdk 34
        versionCode 1
        versionName "1.0"
    }
    signingConfigs {
        debug {
            storeFile file('../../rundlauf.keystore')
            storePassword 'rundlauf'
            keyAlias 'rundlauf'
            keyPassword 'rundlauf'
        }
    }
    buildTypes {
        debug {
            signingConfig signingConfigs.debug
        }
    }
    compileOptions {
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }
}

dependencies {
    implementation 'com.google.android.gms:play-services-wearable:18.2.0'
}
'''.replace('%PKG%', pkg))

(wear / 'src/main/AndroidManifest.xml').write_text('''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-feature android:name="android.hardware.type.watch" />
    <uses-permission android:name="android.permission.BODY_SENSORS" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_HEALTH" />
    <uses-permission android:name="android.permission.WAKE_LOCK" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
    <application
        android:label="Rundlauf Puls"
        android:allowBackup="false"
        android:theme="@android:style/Theme.DeviceDefault">
        <uses-library android:name="com.google.android.wearable" android:required="false" />
        <meta-data android:name="com.google.android.wearable.standalone" android:value="false" />
        <activity android:name="%PKG%.wear.WearMainActivity" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
        <service android:name="%PKG%.wear.HrService" android:exported="false" android:foregroundServiceType="health" />
    </application>
</manifest>
'''.replace('%PKG%', pkg))

jd = wear / 'src/main/java' / pkg.replace('.', '/') / 'wear'

(jd / 'HrService.java').write_text('''package %PKG%.wear;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import com.google.android.gms.tasks.Tasks;
import com.google.android.gms.wearable.Node;
import com.google.android.gms.wearable.Wearable;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class HrService extends Service implements SensorEventListener {
    interface Listener { void onState(int bpm, String status); }
    static volatile Listener listener;
    static volatile boolean running = false;
    static volatile int lastBpm = 0;
    static volatile String lastStatus = "Gestoppt";

    private SensorManager sm;
    private PowerManager.WakeLock wl;
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private long lastSend = 0;
    private final Handler main = new Handler(Looper.getMainLooper());

    static void publish(int bpm, String status) {
        lastBpm = bpm;
        lastStatus = status;
        final Listener l = listener;
        if (l != null) {
            new Handler(Looper.getMainLooper()).post(new Runnable() {
                public void run() { l.onState(lastBpm, lastStatus); }
            });
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && "STOP".equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }
        if (running) return START_STICKY;
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        nm.createNotificationChannel(new NotificationChannel("hr", "Puls", NotificationManager.IMPORTANCE_LOW));
        Notification n = new Notification.Builder(this, "hr")
            .setContentTitle("Rundlauf Puls")
            .setContentText("Puls wird ans Handy gesendet")
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setOngoing(true)
            .build();
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(21, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH);
        } else {
            startForeground(21, n);
        }
        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "rundlauf:hr");
        wl.acquire(4 * 60 * 60 * 1000L);
        sm = (SensorManager) getSystemService(Context.SENSOR_SERVICE);
        Sensor hr = sm.getDefaultSensor(Sensor.TYPE_HEART_RATE);
        if (hr == null) {
            publish(0, "Kein Pulssensor gefunden");
            stopSelf();
            return START_NOT_STICKY;
        }
        boolean ok = sm.registerListener(this, hr, SensorManager.SENSOR_DELAY_NORMAL);
        running = ok;
        publish(0, ok ? "Messe Puls ..." : "Sensor nicht startbar (Berechtigung?)");
        if (!ok) stopSelf();
        return START_STICKY;
    }

    @Override
    public void onSensorChanged(SensorEvent e) {
        if (e.values == null || e.values.length == 0) return;
        final int bpm = Math.round(e.values[0]);
        if (bpm <= 0) {
            publish(0, "Kein Signal, Uhr eng anlegen");
            return;
        }
        long now = System.currentTimeMillis();
        publish(bpm, "Gesendet");
        if (now - lastSend < 2000) return;
        lastSend = now;
        final byte[] data = String.valueOf(bpm).getBytes();
        final Context ctx = getApplicationContext();
        io.execute(new Runnable() {
            public void run() {
                try {
                    List<Node> nodes = Tasks.await(Wearable.getNodeClient(ctx).getConnectedNodes());
                    if (nodes.isEmpty()) { publish(bpm, "Handy nicht verbunden"); return; }
                    for (Node nd : nodes) {
                        Tasks.await(Wearable.getMessageClient(ctx).sendMessage(nd.getId(), "/rundlauf/hr", data));
                    }
                    publish(bpm, "Gesendet");
                } catch (Exception ex) {
                    publish(bpm, "Senden fehlgeschlagen");
                }
            }
        });
    }

    @Override
    public void onAccuracyChanged(Sensor s, int a) { }

    @Override
    public void onDestroy() {
        running = false;
        try { if (sm != null) sm.unregisterListener(this); } catch (Exception ignored) { }
        try { if (wl != null && wl.isHeld()) wl.release(); } catch (Exception ignored) { }
        io.shutdown();
        publish(0, "Gestoppt");
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent i) { return null; }
}
'''.replace('%PKG%', pkg))

(jd / 'WearMainActivity.java').write_text('''package %PKG%.wear;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public class WearMainActivity extends Activity {
    private TextView bpmView, statusView;
    private Button btn;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setBackgroundColor(Color.BLACK);
        root.setPadding(24, 24, 24, 24);
        bpmView = new TextView(this);
        bpmView.setTextColor(Color.WHITE);
        bpmView.setTextSize(44);
        bpmView.setGravity(Gravity.CENTER);
        bpmView.setText("--");
        statusView = new TextView(this);
        statusView.setTextColor(Color.LTGRAY);
        statusView.setTextSize(13);
        statusView.setGravity(Gravity.CENTER);
        btn = new Button(this);
        btn.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { toggle(); }
        });
        root.addView(bpmView);
        root.addView(statusView);
        root.addView(btn);
        setContentView(root);
        refresh();
    }

    private void toggle() {
        if (HrService.running) {
            startService(new Intent(this, HrService.class).setAction("STOP"));
            return;
        }
        if (checkSelfPermission(Manifest.permission.BODY_SENSORS) != PackageManager.PERMISSION_GRANTED) {
            if (Build.VERSION.SDK_INT >= 33) {
                requestPermissions(new String[]{Manifest.permission.BODY_SENSORS, Manifest.permission.POST_NOTIFICATIONS}, 7);
            } else {
                requestPermissions(new String[]{Manifest.permission.BODY_SENSORS}, 7);
            }
            return;
        }
        startForegroundService(new Intent(this, HrService.class));
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] p, int[] r) {
        if (checkSelfPermission(Manifest.permission.BODY_SENSORS) == PackageManager.PERMISSION_GRANTED) {
            startForegroundService(new Intent(this, HrService.class));
        } else {
            statusView.setText("Berechtigung Körpersensoren fehlt");
        }
    }

    private void refresh() {
        bpmView.setText(HrService.lastBpm > 0 ? String.valueOf(HrService.lastBpm) : "--");
        statusView.setText(HrService.lastStatus);
        btn.setText(HrService.running ? "Stop" : "Start");
    }

    @Override
    protected void onResume() {
        super.onResume();
        HrService.listener = new HrService.Listener() {
            public void onState(int bpm, String status) { refresh(); }
        };
        refresh();
    }

    @Override
    protected void onPause() {
        HrService.listener = null;
        super.onPause();
    }
}
'''.replace('%PKG%', pkg))

st = android / 'settings.gradle'
x = st.read_text()
if "include ':wear'" not in x:
    st.write_text(x + "\ninclude ':wear'\n")
print('Uhren-Modul und Handy-Empfaenger eingebaut')
