from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    raise SystemExit(f'ERROR: no se encontro {label}.')


main = Path('lib/main.dart')
s = main.read_text()
helper = '''  Future<List<BluetoothInfo>> loadThermalPrinters() async {
    try {
      final List<BluetoothInfo> printers =
          await PrintBluetoothThermal.pairedBluetooths;
      if (printers.isNotEmpty) return printers;
    } catch (_) {}
    try {
      final List<dynamic> native =
          await const MethodChannel('billaresdonmiguel/network')
                  .invokeMethod<List<dynamic>>('getBondedBluetoothDevices') ??
              <dynamic>[];
      return native.map((dynamic item) {
        final Map<dynamic, dynamic> data = Map<dynamic, dynamic>.from(item as Map);
        return BluetoothInfo(
          name: (data['name'] as String?) ?? '',
          macAdress: (data['macAdress'] as String?) ?? '',
        );
      }).where((BluetoothInfo item) => item.macAdress.isNotEmpty).toList();
    } catch (_) {
      return <BluetoothInfo>[];
    }
  }

'''
marker = '  Future<bool> configureThermalPrinter() async {'
if 'Future<List<BluetoothInfo>> loadThermalPrinters() async {' not in s:
    s = replace_once(s, marker, helper + marker, 'configureThermalPrinter()')
direct = 'final List<BluetoothInfo> printers =\n          await PrintBluetoothThermal.pairedBluetooths;'
s = s.replace(direct, 'final List<BluetoothInfo> printers = await loadThermalPrinters();')
start = s.find(marker)
end = s.find('Future<String?> printReceipt', start)
if start < 0 or end < 0:
    raise SystemExit('ERROR: no se pudo delimitar configureThermalPrinter().')
block = s[start:end]
if 'PrintBluetoothThermal.bluetoothEnabled' in block:
    raise SystemExit('ERROR: permanece el bloqueo bluetoothEnabled.')
if 'loadThermalPrinters()' not in block:
    raise SystemExit('ERROR: configureThermalPrinter no usa loadThermalPrinters().')
main.write_text(s)

# Android files are generated here so the release build always receives the same native bridge.
android = Path('android')
if not (android / 'app' / 'build.gradle.kts').exists():
    raise SystemExit('ERROR: la plataforma Android no fue inicializada.')

gradle = android / 'app' / 'build.gradle.kts'
s = gradle.read_text()
s = s.replace('compileSdk = flutter.compileSdkVersion', 'compileSdk = 36')
s = s.replace('ndkVersion = flutter.ndkVersion', 'ndkVersion = "27.0.12077973"')
s = s.replace('minSdk = flutter.minSdkVersion', 'minSdk = 23')
if 'namespace = "com.billaresdonmiguel.billares_don_miguel"' not in s:
    s = s.replace('android {', 'android {\n    namespace = "com.billaresdonmiguel.billares_don_miguel"', 1)
if 'applicationId = "com.billaresdonmiguel.billares_don_miguel"' not in s:
    s = s.replace('defaultConfig {', 'defaultConfig {\n        applicationId = "com.billaresdonmiguel.billares_don_miguel"', 1)
gradle.write_text(s)

manifest = android / 'app' / 'src' / 'main' / 'AndroidManifest.xml'
s = manifest.read_text()
marker = '<uses-permission android:name="android.permission.INTERNET" />'
if marker not in s:
    s = s.replace('<manifest xmlns:android="http://schemas.android.com/apk/res/android">', '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n    <uses-permission android:name="android.permission.INTERNET" />\n    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />\n    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />\n    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_CONNECTED_DEVICE" />')
bt = '''    <uses-permission android:name="android.permission.BLUETOOTH" />
    <uses-permission android:name="android.permission.BLUETOOTH_ADMIN" />
    <uses-permission android:name="android.permission.BLUETOOTH_SCAN" android:usesPermissionFlags="neverForLocation" />
    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />'''
if 'android.permission.BLUETOOTH_CONNECT' not in s:
    s = s.replace(marker, marker + '\n' + bt)
if 'android:usesCleartextTraffic=' not in s:
    s = s.replace('<application', '<application android:usesCleartextTraffic="true"', 1)
s = s.replace('android:foregroundServiceType="specialUse"', 'android:foregroundServiceType="connectedDevice"')
s = s.replace('<uses-permission android:name="android.permission.FOREGROUND_SERVICE_SPECIAL_USE" />\n', '')
manifest.write_text(s)

kotlin = android / 'app' / 'src' / 'main' / 'kotlin' / 'com' / 'billaresdonmiguel' / 'billares_don_miguel' / 'MainActivity.kt'
kotlin.parent.mkdir(parents=True, exist_ok=True)
kotlin.write_text('''package com.billaresdonmiguel.billares_don_miguel

import android.Manifest
import android.bluetooth.BluetoothManager
import android.content.pm.PackageManager
import android.net.wifi.WifiManager
import android.os.Build
import androidx.annotation.NonNull
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
  private val channelName = "billaresdonmiguel/network"
  private val bluetoothPermissionRequestCode = 4901
  private var pendingBluetoothResult: MethodChannel.Result? = null
  private var multicastLock: WifiManager.MulticastLock? = null

  override fun configureFlutterEngine(@NonNull flutterEngine: FlutterEngine) {
    super.configureFlutterEngine(flutterEngine)
    MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName).setMethodCallHandler { call, result ->
      when (call.method) {
        "acquireMulticastLock" -> {
          try {
            val wifi = applicationContext.getSystemService(WIFI_SERVICE) as WifiManager
            if (multicastLock == null) {
              multicastLock = wifi.createMulticastLock("BillaresDonMiguel")
              multicastLock?.setReferenceCounted(false)
            }
            if (multicastLock?.isHeld != true) multicastLock?.acquire()
          } catch (_: Exception) {}
          result.success(null)
        }
        "getBondedBluetoothDevices" -> getBondedBluetoothDevices(result)
        else -> result.notImplemented()
      }
    }
  }

  private fun getBondedBluetoothDevices(result: MethodChannel.Result) {
    try {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S &&
          checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
        pendingBluetoothResult = result
        requestPermissions(arrayOf(Manifest.permission.BLUETOOTH_CONNECT), bluetoothPermissionRequestCode)
        return
      }
      result.success(readBondedBluetoothDevices())
    } catch (e: SecurityException) {
      result.error("BLUETOOTH_PERMISSION", "No se obtuvo permiso para leer dispositivos Bluetooth emparejados.", null)
    } catch (e: Exception) {
      result.error("BLUETOOTH_READ", e.message, null)
    }
  }

  private fun readBondedBluetoothDevices(): List<Map<String, String>> {
    val manager = getSystemService(BluetoothManager::class.java)
    val adapter = manager?.adapter ?: return emptyList()
    if (!adapter.isEnabled) return emptyList()
    return adapter.bondedDevices.mapNotNull { device ->
      try {
        mapOf("name" to (device.name ?: ""), "macAdress" to device.address)
      } catch (_: SecurityException) { null }
    }
  }

  override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
    super.onRequestPermissionsResult(requestCode, permissions, grantResults)
    if (requestCode != bluetoothPermissionRequestCode) return
    val result = pendingBluetoothResult ?: return
    pendingBluetoothResult = null
    if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
      result.success(readBondedBluetoothDevices())
    } else {
      result.error("BLUETOOTH_PERMISSION", "Permiso Bluetooth no concedido.", null)
    }
  }

  override fun onDestroy() {
    try { multicastLock?.let { if (it.isHeld) it.release() } } catch (_: Exception) {}
    multicastLock = null
    super.onDestroy()
  }
}
''')
print('PERMANENT_PRINTER_INTEGRATION=OK')
