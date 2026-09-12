package com.billaresdonmiguel.billares_don_miguel

import android.Manifest
import android.bluetooth.BluetoothManager
import android.content.pm.PackageManager
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import androidx.annotation.NonNull
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
  private val channelName = "billaresdonmiguel/network"
  private val bluetoothPermissionRequestCode = 4901
  private var pendingBluetoothResult: MethodChannel.Result? = null
  private var multicastLock: WifiManager.MulticastLock? = null

  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    requestBluetoothPermissionsIfNeeded()
  }

  private fun requestBluetoothPermissionsIfNeeded() {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return
    val missing = mutableListOf<String>()
    if (checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED) {
      missing.add(Manifest.permission.BLUETOOTH_SCAN)
    }
    if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
      missing.add(Manifest.permission.BLUETOOTH_CONNECT)
    }
    if (missing.isNotEmpty()) {
      requestPermissions(missing.toTypedArray(), bluetoothPermissionRequestCode)
    }
  }

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
    if (grantResults.isNotEmpty() && grantResults.all { it == PackageManager.PERMISSION_GRANTED }) {
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