package com.example.dtv_energy_flutter

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.wifi.WifiNetworkSpecifier
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import com.espressif.provisioning.Session
import com.espressif.provisioning.listeners.ResponseListener
import com.espressif.provisioning.security.Security1
import com.espressif.provisioning.transport.Transport
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class CoreProvisioningBridge(private val activity: Activity, messenger: BinaryMessenger) : MethodChannel.MethodCallHandler {
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val busy = AtomicBoolean(false)
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    private var boundNetwork: Network? = null

    init {
        MethodChannel(messenger, "sic/provisioning").setMethodCallHandler(this)
        MethodChannel(messenger, "home_competition/provisioning").setMethodCallHandler(this)
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "connectSetupNetwork" -> {
                val ssid = call.argument<String>("ssid")
                val password = call.argument<String>("password")
                if (ssid.isNullOrEmpty() || password == null) {
                    result.error("INVALID_INPUT", "SSID and password are required", null)
                } else {
                    connectSetupNetwork(ssid, password, result)
                }
            }
            "provisionSubBox" -> {
                provisionSubBox(call, result)
            }
            "cancelProvisioning" -> {
                cancelProvisioning(result)
            }
            "wifiSettings" -> {
                activity.startActivity(Intent(Settings.ACTION_WIFI_SETTINGS))
                result.success(null)
            }
            "exchange" -> {
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
            }
            else -> result.notImplemented()
        }
    }

    private fun cleanUpNetwork(connectivity: ConnectivityManager) {
        networkCallback?.let {
            try {
                connectivity.unregisterNetworkCallback(it)
            } catch (_: Exception) {}
            networkCallback = null
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            try {
                connectivity.bindProcessToNetwork(null)
            } catch (_: Exception) {}
        }
        boundNetwork = null
    }

    private fun connectSetupNetwork(ssid: String, password: String, result: MethodChannel.Result) {
        val connectivity = activity.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            try {
                cleanUpNetwork(connectivity)

                val specifier = WifiNetworkSpecifier.Builder()
                    .setSsid(ssid)
                    .setWpa2Passphrase(password)
                    .build()

                val request = NetworkRequest.Builder()
                    .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
                    .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    .setNetworkSpecifier(specifier)
                    .build()

                val finished = AtomicBoolean(false)
                val timeoutRunnable = Runnable {
                    if (finished.compareAndSet(false, true)) {
                        cleanUpNetwork(connectivity)
                        result.error("SETUP_NETWORK_TIMEOUT", "Timeout connecting to SoftAP: $ssid", null)
                    }
                }
                main.postDelayed(timeoutRunnable, 30000)

                val callback = object : ConnectivityManager.NetworkCallback() {
                    override fun onAvailable(network: Network) {
                        if (finished.compareAndSet(false, true)) {
                            main.removeCallbacks(timeoutRunnable)
                            boundNetwork = network
                            connectivity.bindProcessToNetwork(network)
                            main.post { result.success(true) }
                        }
                    }

                    override fun onUnavailable() {
                        if (finished.compareAndSet(false, true)) {
                            main.removeCallbacks(timeoutRunnable)
                            cleanUpNetwork(connectivity)
                            main.post { result.error("SETUP_NETWORK_TIMEOUT", "SoftAP unavailable: $ssid", null) }
                        }
                    }

                    override fun onLost(network: Network) {
                        if (boundNetwork == network) {
                            boundNetwork = null
                        }
                    }
                }
                networkCallback = callback
                connectivity.requestNetwork(request, callback)
            } catch (e: SecurityException) {
                result.error("PERMISSION_DENIED", "Permission denied: ${e.message}", null)
            } catch (e: Exception) {
                result.error("PROVISIONING_FAILED", "Failed to connect to setup network: ${e.message}", null)
            }
        } else {
            result.success(true)
        }
    }

    private fun cancelProvisioning(result: MethodChannel.Result) {
        val connectivity = activity.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        cleanUpNetwork(connectivity)
        busy.set(false)
        result.success(null)
    }

    private fun provisionSubBox(call: MethodCall, result: MethodChannel.Result) {
        val ssid = call.argument<String>("ssid")
        val password = call.argument<String>("password") ?: ""
        val gatewayHost = call.argument<String>("gateway_host")
        val gatewayPort = call.argument<Int>("gateway_port") ?: 8883
        val pop = call.argument<String>("pop")
        val roomName = call.argument<String>("room_name") ?: "Phòng khách"
        val roomType = call.argument<Int>("room_type") ?: 1

        if (ssid.isNullOrEmpty() || gatewayHost.isNullOrEmpty() || pop.isNullOrEmpty()) {
            result.error("INVALID_INPUT", "SSID, gateway_host, and pop are required", null)
            return
        }

        if (!busy.compareAndSet(false, true)) {
            result.error("PROVISIONING_FAILED", "A provisioning session is already running", null)
            return
        }

        val connectivity = activity.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = boundNetwork ?: connectivity.allNetworks.firstOrNull {
            connectivity.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true
        }

        if (network == null) {
            busy.set(false)
            result.error("WIFI_DISCONNECTED", "Not connected to SubBox setup network", null)
            return
        }

        val finished = AtomicBoolean(false)
        fun complete(data: Map<String, Any>?, errorCode: String? = null, errorMessage: String? = null) {
            if (!finished.compareAndSet(false, true)) return
            busy.set(false)
            main.post {
                if (data != null) {
                    result.success(data)
                } else {
                    result.error(errorCode ?: "PROVISIONING_FAILED", errorMessage ?: "Provisioning failed", null)
                }
            }
        }

        val timeoutRunnable = Runnable {
            complete(null, "SETUP_NETWORK_TIMEOUT", "SubBox provisioning timed out")
        }
        main.postDelayed(timeoutRunnable, 30000)

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
                        connection.connectTimeout = 5000
                        connection.readTimeout = 5000
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
                    } catch (e: Exception) {
                        if (!finished.get()) listener.onFailure(e)
                    } finally {
                        connection?.disconnect()
                    }
                }
            }
        }

        try {
            val session = Session(transport, Security1(pop))
            session.init(null, object : Session.SessionListener {
                override fun OnSessionEstablished() {
                    if (finished.get()) return
                    try {
                        val configJson = JSONObject().apply {
                            put("ssid", ssid)
                            put("password", password)
                            put("gateway_host", gatewayHost)
                            put("gateway_port", gatewayPort)
                            put("pop", pop)
                            put("room_name", roomName)
                            put("room_type", roomType)
                        }.toString().toByteArray(Charsets.UTF_8)

                        session.sendDataToDevice("hc-config", configJson, object : ResponseListener {
                            override fun onSuccess(returnData: ByteArray) {
                                if (finished.get()) return
                                session.sendDataToDevice("hc-status", ByteArray(0), object : ResponseListener {
                                    override fun onSuccess(statusData: ByteArray) {
                                        main.removeCallbacks(timeoutRunnable)
                                        val resultMap = mapOf(
                                            "status" to "SUCCESS",
                                            "ssid" to ssid,
                                            "gateway_host" to gatewayHost,
                                            "room_name" to roomName
                                        )
                                        complete(resultMap)
                                    }

                                    override fun onFailure(e: Exception) {
                                        main.removeCallbacks(timeoutRunnable)
                                        val resultMap = mapOf(
                                            "status" to "SUCCESS",
                                            "ssid" to ssid,
                                            "gateway_host" to gatewayHost,
                                            "room_name" to roomName
                                        )
                                        complete(resultMap)
                                    }
                                })
                            }

                            override fun onFailure(e: Exception) {
                                main.removeCallbacks(timeoutRunnable)
                                complete(null, "PROVISIONING_FAILED", "Failed to send configuration: ${e.message}")
                            }
                        })
                    } catch (e: Exception) {
                        main.removeCallbacks(timeoutRunnable)
                        complete(null, "PROVISIONING_FAILED", e.message)
                    }
                }

                override fun OnSessionEstablishFailed(e: Exception) {
                    main.removeCallbacks(timeoutRunnable)
                    complete(null, "PROOF_REJECTED", "Device rejected setup proof / POP")
                }
            })
        } catch (e: SecurityException) {
            main.removeCallbacks(timeoutRunnable)
            complete(null, "PERMISSION_DENIED", e.message)
        } catch (e: Exception) {
            main.removeCallbacks(timeoutRunnable)
            complete(null, "PROVISIONING_FAILED", e.message)
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
        val network = boundNetwork ?: connectivity.allNetworks.firstOrNull {
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

