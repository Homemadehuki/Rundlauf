import re, pathlib
root = pathlib.Path('android/app/src/main')
mf = root / 'AndroidManifest.xml'
s = mf.read_text()
perms = ['ACCESS_FINE_LOCATION','ACCESS_COARSE_LOCATION','POST_NOTIFICATIONS','FOREGROUND_SERVICE','FOREGROUND_SERVICE_LOCATION','WAKE_LOCK','INTERNET']
add = ''.join(f'    <uses-permission android:name="android.permission.{p}" />\n' for p in perms)
if 'xmlns:tools' not in s:
    s = s.replace('<manifest xmlns:android="http://schemas.android.com/apk/res/android"', '<manifest xmlns:android="http://schemas.android.com/apk/res/android" xmlns:tools="http://schemas.android.com/tools"', 1)
s = s.replace('<application', add + '    <application', 1) if 'FOREGROUND_SERVICE_LOCATION' not in s else s
svc = '        <service android:name="com.equimaps.capacitor_background_geolocation.BackgroundGeolocationService" android:foregroundServiceType="location" android:exported="false" tools:node="merge" />\n'
if 'BackgroundGeolocationService' not in s:
    s = s.replace('</application>', svc + '    </application>', 1)
mf.write_text(s)
sx = root / 'res/values/strings.xml'
t = sx.read_text()
if 'capacitor_background_geolocation_notification_channel_name' not in t:
    t = t.replace('</resources>', '    <string name="capacitor_background_geolocation_notification_channel_name">Rundlauf Navigation</string>\n</resources>')
    sx.write_text(t)
print(mf.read_text())
