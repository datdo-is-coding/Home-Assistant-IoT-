package com.homecompetition.app

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.embedding.android.FlutterSurfaceView
import android.view.Surface
import android.view.SurfaceHolder
import io.flutter.plugin.common.MethodChannel
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.os.Build
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class MainActivity : FlutterActivity() {
    private val alias = "sic-home-session"
    private var renderSurface: Surface? = null
    private var appUpdates: AppUpdateBridge? = null

    override fun onDestroy() {
        appUpdates?.close()
        super.onDestroy()
    }

    override fun onResume() {
        super.onResume()
        requestHighRefreshRate()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) requestHighRefreshRate()
    }

    @Suppress("DEPRECATION")
    private fun requestHighRefreshRate() {
        val screen = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) display else windowManager.defaultDisplay
        val current = screen?.mode ?: return
        val preferred = screen.supportedModes
            .filter { it.physicalWidth == current.physicalWidth &&
                it.physicalHeight == current.physicalHeight && it.refreshRate <= 120.5f }
            .maxByOrNull { it.refreshRate } ?: return
        val params = window.attributes
        if (params.preferredDisplayModeId != preferred.modeId || params.preferredRefreshRate != preferred.refreshRate) {
            params.preferredDisplayModeId = preferred.modeId
            params.preferredRefreshRate = preferred.refreshRate
            window.attributes = params
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            renderSurface?.takeIf { it.isValid }?.setFrameRate(
                preferred.refreshRate, Surface.FRAME_RATE_COMPATIBILITY_DEFAULT)
        }
    }

    override fun onFlutterSurfaceViewCreated(flutterSurfaceView: FlutterSurfaceView) {
        super.onFlutterSurfaceViewCreated(flutterSurfaceView)
        flutterSurfaceView.holder.addCallback(object : SurfaceHolder.Callback {
            override fun surfaceCreated(holder: SurfaceHolder) {
                renderSurface = holder.surface
                requestHighRefreshRate()
            }
            override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
                renderSurface = holder.surface
                requestHighRefreshRate()
            }
            override fun surfaceDestroyed(holder: SurfaceHolder) { renderSurface = null }
        })
    }

    private fun sessionKey(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build())
        }.generateKey()
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        CoreProvisioningBridge(this, flutterEngine.dartExecutor.binaryMessenger)
        appUpdates = AppUpdateBridge(this, flutterEngine.dartExecutor.binaryMessenger)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "sic/session").setMethodCallHandler { call, result ->
            val prefs = getSharedPreferences("sic_session", MODE_PRIVATE)
            try {
                when (call.method) {
                    "read" -> {
                        val saved = prefs.getString("ciphertext", null)
                        if (saved == null) {
                            result.success(null)
                        } else {
                            val bytes = Base64.decode(saved, Base64.NO_WRAP)
                            require(bytes.size > 28)
                            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                            cipher.init(Cipher.DECRYPT_MODE, sessionKey(), GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
                            result.success(String(cipher.doFinal(bytes.copyOfRange(12, bytes.size)), Charsets.UTF_8))
                        }
                    }
                    "write" -> {
                        val value = call.arguments as String
                        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                        cipher.init(Cipher.ENCRYPT_MODE, sessionKey())
                        val encrypted = cipher.iv + cipher.doFinal(value.toByteArray(Charsets.UTF_8))
                        check(prefs.edit().putString("ciphertext", Base64.encodeToString(encrypted, Base64.NO_WRAP)).commit())
                        result.success(null)
                    }
                    "delete" -> {
                        check(prefs.edit().clear().commit())
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            } catch (_: Exception) {
                result.error("SESSION_STORAGE", "Unable to access secure session storage", null)
            }
        }
    }
}
