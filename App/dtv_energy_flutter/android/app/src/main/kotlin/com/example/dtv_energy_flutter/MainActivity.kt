package com.example.dtv_energy_flutter

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class MainActivity : FlutterActivity() {
    private val alias = "sic-home-session"

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
