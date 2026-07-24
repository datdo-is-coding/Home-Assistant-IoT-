package com.example.dtvenergyhub.ui

import android.app.NotificationManager
import android.content.Context
import android.speech.tts.TextToSpeech
import androidx.core.app.NotificationCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.dtvenergyhub.data.ChatMessage
import com.example.dtvenergyhub.data.EnergyData
import com.example.dtvenergyhub.data.EnergyRepository
import com.example.dtvenergyhub.data.EvnTierInfo
import com.example.dtvenergyhub.data.GeminiRepository
import com.example.dtvenergyhub.data.MessageSender
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.Locale

data class EnergyUiState(
    val espIp: String = "192.168.4.1",
    val isConnected: Boolean = false,
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    val energyData: EnergyData = EnergyData(),
    val powerHistory: List<Float> = List(30) { 0f },
    val apiKey: String = "AIzaSyAC9PKO176Zs6ax3uhq9avfpgOUS215kko",
    val budgetLimitVnd: Float = 1000000f,
    val evnTotalCostVnd: Float = 0f,
    val evnTiers: List<EvnTierInfo> = emptyList(),
    val aiAnomalyAlert: String? = null,
    val chatMessages: List<ChatMessage> = listOf(
        ChatMessage(MessageSender.AI, "Xin chào! Tôi là Trợ Lý Năng Lượng AI DTV. Bấm mic 🎙️ hoặc nhắn tin để tôi trả lời bằng giọng nói nhé!")
    ),
    val isAiThinking: Boolean = false,
    val isTtsSpeaking: Boolean = false
)

class EnergyViewModel : ViewModel() {

    private val energyRepo = EnergyRepository()
    private val geminiRepo = GeminiRepository()

    private val _uiState = MutableStateFlow(EnergyUiState())
    val uiState: StateFlow<EnergyUiState> = _uiState.asStateFlow()

    private var ttsEngine: TextToSpeech? = null
    private var lastAnomalyAlertTime = 0L

    init {
        startPolling()
    }

    fun initTts(context: Context) {
        if (ttsEngine == null) {
            ttsEngine = TextToSpeech(context.applicationContext) { status ->
                if (status == TextToSpeech.SUCCESS) {
                    ttsEngine?.language = Locale("vi", "VN")
                }
            }
        }
    }

    fun speakText(context: Context, text: String) {
        initTts(context)
        val cleanText = text.replace(Regex("[*#_~`]"), "")
        ttsEngine?.speak(cleanText, TextToSpeech.QUEUE_FLUSH, null, "dtv_tts_${System.currentTimeMillis()}")
    }

    fun stopTts() {
        ttsEngine?.stop()
    }

    override fun onCleared() {
        super.onCleared()
        ttsEngine?.stop()
        ttsEngine?.shutdown()
    }

    fun updateEspIp(newIp: String) {
        _uiState.update { it.copy(espIp = newIp) }
    }

    fun updateApiKey(newKey: String) {
        _uiState.update { it.copy(apiKey = newKey) }
    }

    fun updateBudgetLimit(limitVnd: Float) {
        _uiState.update { it.copy(budgetLimitVnd = limitVnd) }
    }

    private fun startPolling() {
        viewModelScope.launch {
            while (true) {
                val currentIp = _uiState.value.espIp
                if (currentIp.isNotBlank()) {
                    val result = energyRepo.fetchEnergyData(currentIp)
                    result.onSuccess { data ->
                        val pVal = data.power.toFloatOrNull() ?: 0f
                        val monthKwh = data.month.toFloatOrNull() ?: 0f

                        val newHistory = _uiState.value.powerHistory.toMutableList().apply {
                            removeAt(0)
                            add(pVal)
                        }

                        val evnCalc = calculateEvnTiers(monthKwh)

                        _uiState.update {
                            it.copy(
                                isConnected = true,
                                energyData = data,
                                powerHistory = newHistory,
                                evnTotalCostVnd = evnCalc.first,
                                evnTiers = evnCalc.second,
                                errorMessage = null
                            )
                        }

                        if (pVal > 1500f && (System.currentTimeMillis() - lastAnomalyAlertTime > 60000)) {
                            lastAnomalyAlertTime = System.currentTimeMillis()
                            triggerAiAnomalyAnalysis(pVal)
                        }

                    }.onFailure { err ->
                        _uiState.update {
                            it.copy(
                                isConnected = false,
                                errorMessage = err.message
                            )
                        }
                    }
                }
                delay(1500)
            }
        }
    }

    fun sendWatchNotification(context: Context, title: String, message: String) {
        try {
            val notificationManager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val notification = NotificationCompat.Builder(context, "dtv_energy_channel")
                .setSmallIcon(android.R.drawable.ic_dialog_alert)
                .setContentTitle(title)
                .setContentText(message)
                .setStyle(NotificationCompat.BigTextStyle().bigText(message))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setDefaults(NotificationCompat.DEFAULT_ALL)
                .setAutoCancel(true)
                .build()

            notificationManager.notify((System.currentTimeMillis() % 10000).toInt(), notification)
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun triggerAiAnomalyAnalysis(powerW: Float) {
        viewModelScope.launch {
            val prompt = "CẢNH BÁO TẢI CAO: Công suất tức thời vừa tăng đột biến lên ${powerW}W! Hãy phân tích ngắn gọn và đưa ra khuyến nghị an toàn gấp!"
            val result = geminiRepo.generateAiResponse(prompt, _uiState.value.energyData, _uiState.value.apiKey)
            result.onSuccess { aiText ->
                _uiState.update {
                    it.copy(
                        aiAnomalyAlert = aiText,
                        chatMessages = it.chatMessages + ChatMessage(MessageSender.AI, "🚨 CẢNH BÁO TẢI CAO (${powerW}W):\n$aiText")
                    )
                }
            }
        }
    }

    fun dismissAnomalyAlert() {
        _uiState.update { it.copy(aiAnomalyAlert = null) }
    }

    fun detectAppliances(context: Context? = null) {
        val userMsg = ChatMessage(MessageSender.USER, "🔍 Phân tích các thiết bị điện đang bật...")
        _uiState.update {
            it.copy(
                chatMessages = it.chatMessages + userMsg,
                isAiThinking = true
            )
        }

        viewModelScope.launch {
            val result = geminiRepo.analyzeAppliances(_uiState.value.energyData, _uiState.value.apiKey)
            result.onSuccess { aiText ->
                _uiState.update {
                    it.copy(
                        chatMessages = it.chatMessages + ChatMessage(MessageSender.AI, aiText),
                        isAiThinking = false
                    )
                }
                context?.let { speakText(it, aiText) }
            }.onFailure { err ->
                _uiState.update {
                    it.copy(
                        chatMessages = it.chatMessages + ChatMessage(MessageSender.AI, "⚠️ Lỗi: ${err.message}"),
                        isAiThinking = false
                    )
                }
            }
        }
    }

    fun resetEnergy() {
        viewModelScope.launch {
            energyRepo.sendCommand(_uiState.value.espIp, "reset")
        }
    }

    fun setEnergyValue(value: String) {
        if (value.isBlank()) return
        viewModelScope.launch {
            energyRepo.sendCommand(_uiState.value.espIp, "set?value=$value")
        }
    }

    fun setBilling(day: String, hour: String) {
        if (day.isBlank() || hour.isBlank()) return
        viewModelScope.launch {
            energyRepo.sendCommand(_uiState.value.espIp, "billing?day=$day&hour=$hour")
        }
    }

    fun sendAiPrompt(promptText: String, context: Context? = null) {
        if (promptText.isBlank()) return
        val userMsg = ChatMessage(MessageSender.USER, promptText)
        _uiState.update {
            it.copy(
                chatMessages = it.chatMessages + userMsg,
                isAiThinking = true
            )
        }

        viewModelScope.launch {
            val result = geminiRepo.generateAiResponse(
                prompt = promptText,
                currentData = _uiState.value.energyData,
                apiKey = _uiState.value.apiKey
            )
            result.onSuccess { aiText ->
                _uiState.update {
                    it.copy(
                        chatMessages = it.chatMessages + ChatMessage(MessageSender.AI, aiText),
                        isAiThinking = false
                    )
                }
                context?.let { speakText(it, aiText) }
            }.onFailure { err ->
                _uiState.update {
                    it.copy(
                        chatMessages = it.chatMessages + ChatMessage(MessageSender.AI, "⚠️ Lỗi: ${err.message}"),
                        isAiThinking = false
                    )
                }
            }
        }
    }

    private fun calculateEvnTiers(totalKwh: Float): Pair<Float, List<EvnTierInfo>> {
        var remaining = totalKwh
        var totalCost = 0f

        val tier1Use = remaining.coerceAtMost(50f)
        val cost1 = tier1Use * 1893f
        totalCost += cost1
        remaining = (remaining - tier1Use).coerceAtLeast(0f)

        val tier2Use = remaining.coerceAtMost(50f)
        val cost2 = tier2Use * 1956f
        totalCost += cost2
        remaining = (remaining - tier2Use).coerceAtLeast(0f)

        val tier3Use = remaining.coerceAtMost(100f)
        val cost3 = tier3Use * 2271f
        totalCost += cost3
        remaining = (remaining - tier3Use).coerceAtLeast(0f)

        val tier4Use = remaining.coerceAtMost(100f)
        val cost4 = tier4Use * 2860f
        totalCost += cost4
        remaining = (remaining - tier4Use).coerceAtLeast(0f)

        val tier5Use = remaining.coerceAtMost(100f)
        val cost5 = tier5Use * 3197f
        totalCost += cost5
        remaining = (remaining - tier5Use).coerceAtLeast(0f)

        val tier6Use = remaining
        val cost6 = tier6Use * 3302f
        totalCost += cost6

        val vatCost = totalCost * 1.08f

        val tiers = listOf(
            EvnTierInfo("Bậc 1 (0-50 kWh)", tier1Use, 50f, 1893f, totalKwh <= 50f),
            EvnTierInfo("Bậc 2 (51-100 kWh)", tier2Use, 50f, 1956f, totalKwh > 50f && totalKwh <= 100f),
            EvnTierInfo("Bậc 3 (101-200 kWh)", tier3Use, 100f, 2271f, totalKwh > 100f && totalKwh <= 200f),
            EvnTierInfo("Bậc 4 (201-300 kWh)", tier4Use, 100f, 2860f, totalKwh > 200f && totalKwh <= 300f),
            EvnTierInfo("Bậc 5 (301-400 kWh)", tier5Use, 100f, 3197f, totalKwh > 300f && totalKwh <= 400f),
            EvnTierInfo("Bậc 6 (>400 kWh)", tier6Use, 999f, 3302f, totalKwh > 400f)
        )

        return Pair(vatCost, tiers)
    }
}
