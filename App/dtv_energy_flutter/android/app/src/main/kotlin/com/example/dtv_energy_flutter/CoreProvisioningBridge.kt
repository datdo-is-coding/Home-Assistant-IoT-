package com.example.dtv_energy_flutter

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import com.espressif.provisioning.Session
import com.espressif.provisioning.listeners.ResponseListener
import com.espressif.provisioning.security.Security1
import com.espressif.provisioning.transport.Transport
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class CoreProvisioningBridge(private val activity: Activity, messenger: BinaryMessenger) {
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val busy = AtomicBoolean(false)

    init {
        MethodChannel(messenger, "home_competition/provisioning").setMethodCallHandler { call, result ->
            if (call.method == "wifiSettings") {
                activity.startActivity(Intent(Settings.ACTION_WIFI_SETTINGS))
                result.success(null)
            } else if (call.method == "exchange") {
                val pop = call.argument<String>("pop")
                val endpoint = call.argument<String>("endpoint")
                val data = call.argument<ByteArray>("payload")
                if (pop.isNullOrEmpty() || pop.length > 128 || endpoint !in listOf("hc-info", "hc-config", "hc-status") || data == null || data.size > 1024) {
                    result.error("INVALID_INPUT", "Invalid commissioning request", null)
                } else if (!busy.compareAndSet(false, true)) {
                    result.error("BUSY", "A secure exchange is already running", null)
                } else {
                    exchange(pop, endpoint!!, data, result)
                }
            } else result.notImplemented()
        }
    }

    private fun exchange(pop: String, endpoint: String, data: ByteArray, result: MethodChannel.Result) {
        val finished = AtomicBoolean(false)
        fun complete(bytes: ByteArray?) {
            if (!finished.compareAndSet(false, true)) return
            busy.set(false)
            main.post {
                if (bytes != null) result.success(bytes)
                else result.error("SECURE_SESSION_FAILED", "Secure device exchange failed", null)
            }
        }
        main.postDelayed({ complete(null) }, 18000)
        val connectivity = activity.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = connectivity.allNetworks.firstOrNull {
            connectivity.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true
        }
        if (network == null) { complete(null); return }
        var cookie: String? = null
        val transport = object : Transport {
            override fun sendConfigData(path: String, payload: ByteArray, listener: ResponseListener) {
                worker.execute {
                    if (finished.get()) return@execute
                    var connection: HttpURLConnection? = null
                    try {
                        require(path in listOf("prov-session", "hc-info", "hc-config", "hc-status"))
                        connection = network.openConnection(URL("http://192.168.4.1/$path")) as HttpURLConnection
                        connection.requestMethod = "POST"
                        connection.doOutput = true
                        connection.instanceFollowRedirects = false
                        connection.connectTimeout = 4000
                        connection.readTimeout = 4000
                        connection.setRequestProperty("Content-Type", "application/octet-stream")
                        cookie?.let { connection.setRequestProperty("Cookie", it) }
                        connection.outputStream.use { it.write(payload) }
                        check(connection.responseCode == 200)
                        connection.getHeaderField("Set-Cookie")?.let { cookie = it.substringBefore(';') }
                        val response = ByteArrayOutputStream()
                        connection.inputStream.use { input ->
                            val buffer = ByteArray(1024)
                            while (true) {
                                val count = input.read(buffer)
                                if (count < 0) break
                                check(response.size() + count <= 4096)
                                response.write(buffer, 0, count)
                            }
                        }
                        if (!finished.get()) listener.onSuccess(response.toByteArray())
                    } catch (_: Exception) {
                        if (!finished.get()) listener.onFailure(Exception("Secure device transport failed"))
                    } finally { connection?.disconnect() }
                }
            }
        }
        try {
            val session = Session(transport, Security1(pop))
            session.init(null, object : Session.SessionListener {
                override fun OnSessionEstablished() {
                    if (finished.get()) return
                    try {
                        session.sendDataToDevice(endpoint, data, object : ResponseListener {
                            override fun onSuccess(returnData: ByteArray) = complete(returnData)
                            override fun onFailure(e: Exception) = complete(null)
                        })
                    } catch (_: Exception) { complete(null) }
                }
                override fun OnSessionEstablishFailed(e: Exception) = complete(null)
            })
        } catch (_: Exception) { complete(null) }
    }
}
