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
import com.google.android.gms.wearable.Node;
import com.google.android.gms.wearable.Wearable;
import java.util.List;

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
    public void send(final PluginCall call) {
        final String path = call.getString("path");
        final String data = call.getString("data");
        if (path == null || data == null) {
            call.reject("path/data fehlt");
            return;
        }
        Wearable.getNodeClient(getContext()).getConnectedNodes()
            .addOnSuccessListener(new com.google.android.gms.tasks.OnSuccessListener<List<Node>>() {
                @Override
                public void onSuccess(List<Node> nodes) {
                    for (Node n : nodes) {
                        Wearable.getMessageClient(getContext()).sendMessage(n.getId(), path, data.getBytes());
                    }
                    call.resolve();
                }
            })
            .addOnFailureListener(new com.google.android.gms.tasks.OnFailureListener() {
                @Override
                public void onFailure(Exception e) {
                    call.reject("Senden fehlgeschlagen");
                }
            });
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
    <uses-permission android:name="android.permission.VIBRATE" />
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
        <service android:name="%PKG%.wear.WatchListenerService" android:exported="true">
            <intent-filter>
                <action android:name="com.google.android.gms.wearable.MESSAGE_RECEIVED" />
                <data android:scheme="wear" android:host="*" android:pathPrefix="/rundlauf" />
            </intent-filter>
        </service>
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
        if (now - lastSend < WearState.intervalMs) return;
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

(jd / 'WearState.java').write_text('''package %PKG%.wear;

import android.os.Handler;
import android.os.Looper;

final class WearState {
    interface Listener { void onChange(); }
    static volatile Listener listener;
    static volatile long t = 0;
    static volatile boolean guide = false, hasArrow = false, ended = false;
    static volatile int arrow = 0, dist = -1, vibId = -1;
    static volatile String text = "", done = "-", rest = "-", time = "-";
    static volatile int z0 = 100, z1 = 130, z2 = 160;
    static volatile long intervalMs = 5000;

    static void changed() {
        final Listener l = listener;
        if (l != null) {
            new Handler(Looper.getMainLooper()).post(new Runnable() {
                public void run() { l.onChange(); }
            });
        }
    }
}
'''.replace('%PKG%', pkg))

(jd / 'WatchListenerService.java').write_text('''package %PKG%.wear;

import android.content.Context;
import android.os.VibrationEffect;
import android.os.Vibrator;
import com.google.android.gms.wearable.MessageEvent;
import com.google.android.gms.wearable.WearableListenerService;
import org.json.JSONArray;
import org.json.JSONObject;

public class WatchListenerService extends WearableListenerService {
    @Override
    public void onMessageReceived(MessageEvent ev) {
        if (!"/rundlauf/nav".equals(ev.getPath())) return;
        try {
            JSONObject j = new JSONObject(new String(ev.getData(), "UTF-8"));
            WearState.guide = j.optInt("g", 0) == 1;
            WearState.ended = j.optInt("end", 0) == 1;
            WearState.hasArrow = j.has("ar") && !j.isNull("ar");
            WearState.arrow = j.optInt("ar", 0);
            WearState.dist = j.has("d") ? j.optInt("d", -1) : -1;
            WearState.text = j.optString("tx", "");
            WearState.done = j.optString("done", "-");
            WearState.rest = j.optString("rest", "-");
            WearState.time = j.optString("tm", "-");
            JSONArray z = j.optJSONArray("z");
            if (z != null && z.length() == 3) {
                WearState.z0 = z.optInt(0, 100);
                WearState.z1 = z.optInt(1, 130);
                WearState.z2 = z.optInt(2, 160);
            }
            int iv = j.optInt("iv", 5);
            WearState.intervalMs = Math.max(1, Math.min(30, iv)) * 1000L;
            int vib = j.optInt("vib", 0);
            if (WearState.vibId >= 0 && vib > 0 && vib != WearState.vibId) {
                vibrate(j.optString("vk", ""));
            }
            WearState.vibId = vib;
            WearState.t = System.currentTimeMillis();
            WearState.changed();
        } catch (Exception ignored) {
        }
    }

    private void vibrate(String kind) {
        try {
            Vibrator v = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
            if (v == null) return;
            long[] pat;
            if ("L".equals(kind)) pat = new long[] { 0, 120, 100, 120 };
            else if ("R".equals(kind)) pat = new long[] { 0, 450 };
            else pat = new long[] { 0, 250, 120, 250, 120, 250 };
            v.vibrate(VibrationEffect.createWaveform(pat, -1));
        } catch (Exception ignored) {
        }
    }
}
'''.replace('%PKG%', pkg))

(jd / 'ArrowView.java').write_text('''package %PKG%.wear;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.view.View;

public class ArrowView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();
    private float angle = 0;
    private boolean show = false;

    public ArrowView(Context c) {
        super(c);
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(Color.WHITE);
    }

    public void set(boolean show, float angle) {
        this.show = show;
        this.angle = angle;
        invalidate();
    }

    @Override
    protected void onDraw(Canvas c) {
        if (!show) return;
        float w = getWidth(), h = getHeight(), s = Math.min(w, h), cx = w / 2, cy = h / 2;
        c.save();
        c.rotate(angle, cx, cy);
        path.reset();
        path.moveTo(cx, cy - s * 0.48f);
        path.lineTo(cx + s * 0.40f, cy - s * 0.02f);
        path.lineTo(cx + s * 0.16f, cy - s * 0.02f);
        path.lineTo(cx + s * 0.16f, cy + s * 0.48f);
        path.lineTo(cx - s * 0.16f, cy + s * 0.48f);
        path.lineTo(cx - s * 0.16f, cy - s * 0.02f);
        path.lineTo(cx - s * 0.40f, cy - s * 0.02f);
        path.close();
        c.drawPath(path, paint);
        c.restore();
    }
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
import android.os.Handler;
import android.os.Looper;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

public class WearMainActivity extends Activity {
    private TextView bpmView, infoView, statsView, statusView;
    private ArrowView arrow;
    private Button btn;
    private final Handler h = new Handler(Looper.getMainLooper());
    private final Runnable tick = new Runnable() {
        public void run() { refresh(); h.postDelayed(this, 2000); }
    };

    private int dp(float v) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics()));
    }

    private TextView tv(float sp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setTextSize(sp);
        t.setTextColor(color);
        t.setGravity(Gravity.CENTER);
        if (bold) t.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        t.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return t;
    }

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(Color.BLACK);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(dp(26), dp(52), dp(26), dp(40));
        arrow = new ArrowView(this);
        arrow.setLayoutParams(new LinearLayout.LayoutParams(dp(60), dp(60)));
        infoView = tv(15, Color.WHITE, true);
        bpmView = tv(48, Color.WHITE, true);
        statsView = tv(13, Color.LTGRAY, false);
        statusView = tv(10, Color.GRAY, false);
        btn = new Button(this);
        btn.setTextSize(13);
        btn.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { toggle(); }
        });
        root.addView(arrow);
        root.addView(infoView);
        root.addView(bpmView);
        root.addView(statsView);
        root.addView(statusView);
        root.addView(btn, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(40)));
        sv.addView(root);
        setContentView(sv);
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
            statusView.setText("Berechtigung Koerpersensoren fehlt");
        }
    }

    private int pulseColor(int bpm) {
        if (bpm <= 0) return Color.GRAY;
        if (bpm >= WearState.z2) return Color.rgb(255, 59, 48);
        if (bpm >= WearState.z1) return Color.rgb(61, 220, 132);
        if (bpm >= WearState.z0) return Color.rgb(255, 152, 0);
        return Color.WHITE;
    }

    private void refresh() {
        int bpm = HrService.lastBpm;
        bpmView.setText(bpm > 0 ? String.valueOf(bpm) : "--");
        bpmView.setTextColor(pulseColor(bpm));
        boolean fresh = WearState.t > 0 && System.currentTimeMillis() - WearState.t < 20000 && !WearState.ended;
        if (fresh && WearState.guide) {
            arrow.set(WearState.hasArrow, WearState.arrow);
            String d = WearState.dist >= 0 ? WearState.dist + " m  " : "";
            infoView.setText(d + WearState.text);
            statsView.setText(WearState.time + "   " + WearState.done + " km\\nRest " + WearState.rest + " km");
        } else if (fresh) {
            arrow.set(false, 0);
            infoView.setText("Tracking laeuft");
            statsView.setText(WearState.time + "   " + WearState.done + " km");
        } else {
            arrow.set(false, 0);
            infoView.setText(WearState.ended ? "Navigation beendet" : "Warte auf Handy");
            statsView.setText("");
        }
        statusView.setText(HrService.lastStatus);
        btn.setText(HrService.running ? "Stop" : "Start");
    }

    @Override
    protected void onResume() {
        super.onResume();
        HrService.listener = new HrService.Listener() {
            public void onState(int bpm, String status) { refresh(); }
        };
        WearState.listener = new WearState.Listener() {
            public void onChange() { refresh(); }
        };
        h.post(tick);
    }

    @Override
    protected void onPause() {
        HrService.listener = null;
        WearState.listener = null;
        h.removeCallbacks(tick);
        super.onPause();
    }
}
'''.replace('%PKG%', pkg))

st = android / 'settings.gradle'
x = st.read_text()
if "include ':wear'" not in x:
    st.write_text(x + "\ninclude ':wear'\n")
print('Uhren-Modul und Handy-Empfaenger eingebaut')
