package com.example.dtvenergyhub.data

import kotlinx.serialization.Serializable

@Serializable
data class EnergyData(
    val voltage: String = "0.0",
    val current: String = "0.00",
    val power: String = "0",
    val energy: String = "0.0",
    val today: String = "0.00",
    val yesterday: String = "0.00",
    val month: String = "0.00",
    val lastmonth: String = "0.00",
    val money: String = "0",
    val lastmoney: String = "0"
)

data class ChatMessage(
    val sender: MessageSender,
    val text: String,
    val timestamp: Long = System.currentTimeMillis()
)

enum class MessageSender {
    USER, AI
}

data class EvnTierInfo(
    val tierName: String,
    val currentKwhInTier: Float,
    val maxKwhInTier: Float,
    val pricePerKwh: Float,
    val isCurrentTier: Boolean
)

data class AppliancePrediction(
    val name: String,
    val estimatedWatt: Int,
    val icon: String,
    val likelihoodPercentage: Int
)
