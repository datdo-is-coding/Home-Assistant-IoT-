package com.example.dtvenergyhub.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class EnergyRepository {

    suspend fun fetchEnergyData(espIp: String): Result<EnergyData> = withContext(Dispatchers.IO) {
        try {
            val cleanIp = espIp.trim().removePrefix("http://").removeSuffix("/")
            val endpoint = if (cleanIp.contains(":8080") || cleanIp.contains("/api")) {
                "http://$cleanIp/api/data"
            } else {
                "http://$cleanIp/data"
            }

            val url = URL(endpoint)
            val conn = (url.openConnection() as HttpURLConnection).apply {
                connectTimeout = 3000
                readTimeout = 3000
                requestMethod = "GET"
            }

            if (conn.responseCode == 200) {
                val jsonString = conn.inputStream.bufferedReader().use { it.readText() }
                val obj = JSONObject(jsonString)
                val data = EnergyData(
                    voltage = obj.optString("voltage", "0.0"),
                    current = obj.optString("current", "0.00"),
                    power = obj.optString("power", "0"),
                    energy = obj.optString("energy", "0.0"),
                    today = obj.optString("today", "0.00"),
                    yesterday = obj.optString("yesterday", "0.00"),
                    month = obj.optString("month", "0.00"),
                    lastmonth = obj.optString("lastmonth", "0.00"),
                    money = obj.optString("money", "0"),
                    lastmoney = obj.optString("lastmoney", "0")
                )
                Result.success(data)
            } else {
                Result.failure(Exception("HTTP Error: ${conn.responseCode}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun sendCommand(espIp: String, path: String): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            val cleanIp = espIp.trim().removePrefix("http://").removeSuffix("/")
            val url = URL("http://$cleanIp/$path")
            val conn = (url.openConnection() as HttpURLConnection).apply {
                connectTimeout = 3000
                readTimeout = 3000
                requestMethod = "GET"
            }
            Result.success(conn.responseCode == 200)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
