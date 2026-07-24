package com.example.dtvenergyhub.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class GeminiRepository {

    private val availableModels = listOf(
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-flash-latest"
    )

    suspend fun generateAiResponse(
        prompt: String,
        currentData: EnergyData,
        apiKey: String
    ): Result<String> = withContext(Dispatchers.IO) {
        val activeKey = apiKey.ifBlank { "AIzaSyAC9PKO176Zs6ax3uhq9avfpgOUS215kko" }

        val systemContext = """
            Bạn là DTV Energy AI - Trợ lý Năng Lượng Thông Minh dành cho hệ thống Giám sát Điện năng ESP32.
            Dữ liệu đo thời gian thực từ thiết bị PZEM hiện tại:
            - Điện áp: ${currentData.voltage} V
            - Dòng điện: ${currentData.current} A
            - Công suất tức thời: ${currentData.power} W
            - Tổng điện năng tích lũy: ${currentData.energy} kWh
            - Tiêu thụ Hôm nay: ${currentData.today} kWh
            - Tiêu thụ Tháng này: ${currentData.month} kWh
            - Tiền điện tạm tính tháng này: ${currentData.money} VNĐ
            - Tiền điện tháng trước: ${currentData.lastmoney} VNĐ
            
            Nhiệm vụ của bạn: Trả lời ngắn gọn, súc tích, bằng tiếng Việt chuẩn xác, đưa ra phân tích thông minh, tư vấn tiết kiệm điện và cảnh báo nếu có bất thường.
        """.trimIndent()

        val fullPrompt = "$systemContext\n\nCâu hỏi của người dùng: $prompt"

        var lastErrorMsg = ""

        // Try candidate models sequentially to guarantee response
        for (modelName in availableModels) {
            try {
                val url = URL("https://generativelanguage.googleapis.com/v1beta/models/$modelName:generateContent?key=$activeKey")
                val conn = (url.openConnection() as HttpURLConnection).apply {
                    connectTimeout = 8000
                    readTimeout = 8000
                    requestMethod = "POST"
                    setRequestProperty("Content-Type", "application/json")
                    doOutput = true
                }

                val requestJson = JSONObject().apply {
                    val contents = JSONArray().apply {
                        val contentObj = JSONObject().apply {
                            val parts = JSONArray().apply {
                                put(JSONObject().put("text", fullPrompt))
                            }
                            put("parts", parts)
                        }
                        put(contentObj)
                    }
                    put("contents", contents)
                }

                conn.outputStream.use { os ->
                    os.write(requestJson.toString().toByteArray())
                }

                val responseCode = conn.responseCode
                if (responseCode == 200) {
                    val responseText = conn.inputStream.bufferedReader().use { it.readText() }
                    val root = JSONObject(responseText)
                    val candidates = root.optJSONArray("candidates")
                    if (candidates != null && candidates.length() > 0) {
                        val firstCandidate = candidates.getJSONObject(0)
                        val content = firstCandidate.getJSONObject("content")
                        val parts = content.getJSONArray("parts")
                        if (parts.length() > 0) {
                            val text = parts.getJSONObject(0).getString("text")
                            return@withContext Result.success(text)
                        }
                    }
                } else if (responseCode == 429) {
                    lastErrorMsg = "⚠️ Quá giới hạn tần suất yêu cầu (Rate Limit 429). Vui lòng đợi vài giây và thử lại!"
                } else {
                    val errText = conn.errorStream?.bufferedReader()?.use { it.readText() } ?: ""
                    lastErrorMsg = "Lỗi Gemini API ($responseCode): $errText"
                }
            } catch (e: Exception) {
                lastErrorMsg = e.message ?: "Lỗi kết nối API"
            }
        }

        Result.failure(Exception(lastErrorMsg.ifBlank { "Không thể lấy phản hồi từ Gemini API." }))
    }

    suspend fun analyzeAppliances(
        currentData: EnergyData,
        apiKey: String
    ): Result<String> = generateAiResponse(
        prompt = "Dựa trên công suất hiện tại là ${currentData.power}W và dòng điện ${currentData.current}A, hãy suy đoán xem những thiết bị gia đình nào (ví dụ: Tủ lạnh, Bếp từ, Máy lạnh, Bình đun nước, Đèn, Quạt) có khả năng cao nhất đang bật? Hãy ước tính chi phí duy trì thiết bị này nếu chạy liên tục 1 giờ.",
        currentData = currentData,
        apiKey = apiKey
    )
}
