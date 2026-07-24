package com.example.dtvenergyhub.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.dtvenergyhub.data.ChatMessage
import com.example.dtvenergyhub.data.EvnTierInfo
import com.example.dtvenergyhub.data.MessageSender
import java.text.DecimalFormat

// WHITE LIQUID GLASS THEME COLORS
val GlassWhiteBg = Color(0xFFF1F5F9)
val GlassCardWhite = Color(0xCCFFFFFF) // 80% Translucent White Glass
val GlassCardBorder = Color(0x80FFFFFF) // Vibrant White Glass Border
val GlassCardBorderSubtle = Color(0x33000000)

val TextPrimary = Color(0xFF0F172A) // Dark Slate Navy
val TextMuted = Color(0xFF64748B)

val LiquidSkyBlue = Color(0xFF0284C7)
val LiquidEmerald = Color(0xFF059669)
val LiquidAmber = Color(0xFFD97706)
val LiquidRose = Color(0xFFE11D48)
val LiquidPurple = Color(0xFF7C3AED)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(viewModel: EnergyViewModel) {
    val state by viewModel.uiState.collectAsState()
    var selectedTab by remember { mutableIntStateOf(0) } // 0: Dashboard, 1: EVN Tier, 2: AI Assistant, 3: Settings
    var isChatOpen by remember { mutableStateOf(false) }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                brush = Brush.linearGradient(
                    colors = listOf(
                        Color(0xFFE0F2FE), // Soft Sky Blue Fluid
                        Color(0xFFF1F5F9), // Pearl White
                        Color(0xFFFCE7F3), // Soft Rose Liquid
                        Color(0xFFECFDF5)  // Soft Emerald Tint
                    )
                )
            )
    ) {
        Scaffold(
            containerColor = Color.Transparent,
            topBar = {
                TopAppBar(
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = GlassCardWhite,
                        titleContentColor = TextPrimary
                    ),
                    modifier = Modifier.shadow(4.dp, shape = RoundedCornerShape(bottomStart = 20.dp, bottomEnd = 20.dp)),
                    title = {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text(
                                text = "DTV Team",
                                fontWeight = FontWeight.Black,
                                fontSize = 20.sp,
                                color = LiquidSkyBlue
                            )
                            Surface(
                                color = LiquidPurple.copy(alpha = 0.12f),
                                shape = RoundedCornerShape(12.dp)
                            ) {
                                Text(
                                    text = "RUST ENGINE",
                                    fontSize = 10.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = LiquidPurple,
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)
                                )
                            }
                        }
                    },
                    actions = {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier
                                .padding(end = 12.dp)
                                .clip(RoundedCornerShape(20.dp))
                                .background(
                                    if (state.isConnected) LiquidEmerald.copy(alpha = 0.12f)
                                    else LiquidRose.copy(alpha = 0.12f)
                                )
                                .border(
                                    width = 1.dp,
                                    color = if (state.isConnected) LiquidEmerald.copy(alpha = 0.4f)
                                    else LiquidRose.copy(alpha = 0.4f),
                                    shape = RoundedCornerShape(20.dp)
                                )
                                .padding(horizontal = 10.dp, vertical = 4.dp)
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(8.dp)
                                    .clip(CircleShape)
                                    .background(if (state.isConnected) LiquidEmerald else LiquidRose)
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = if (state.isConnected) "ONLINE" else "OFFLINE",
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                color = if (state.isConnected) LiquidEmerald else LiquidRose
                            )
                        }
                    }
                )
            },
            bottomBar = {
                NavigationBar(
                    containerColor = GlassCardWhite,
                    contentColor = TextPrimary,
                    modifier = Modifier.shadow(8.dp, shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp))
                ) {
                    NavigationBarItem(
                        selected = selectedTab == 0,
                        onClick = { selectedTab = 0 },
                        label = { Text("Trang Chủ", fontSize = 11.sp, fontWeight = FontWeight.Bold) },
                        icon = { Text("🏠", fontSize = 16.sp) }
                    )
                    NavigationBarItem(
                        selected = selectedTab == 1,
                        onClick = { selectedTab = 1 },
                        label = { Text("Bậc EVN", fontSize = 11.sp, fontWeight = FontWeight.Bold) },
                        icon = { Text("📊", fontSize = 16.sp) }
                    )
                    NavigationBarItem(
                        selected = selectedTab == 2,
                        onClick = { selectedTab = 2 },
                        label = { Text("Thiết Bị", fontSize = 11.sp, fontWeight = FontWeight.Bold) },
                        icon = { Text("🔍", fontSize = 16.sp) }
                    )
                    NavigationBarItem(
                        selected = selectedTab == 3,
                        onClick = { selectedTab = 3 },
                        label = { Text("Cấu Hình", fontSize = 11.sp, fontWeight = FontWeight.Bold) },
                        icon = { Text("⚙️", fontSize = 16.sp) }
                    )
                }
            }
        ) { innerPadding ->
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
            ) {
                when (selectedTab) {
                    0 -> WhiteDashboardTab(state = state, onOpenChat = { isChatOpen = true })
                    1 -> WhiteEvnTab(state = state)
                    2 -> WhiteApplianceTab(state = state, onDetect = { viewModel.detectAppliances() })
                    3 -> WhiteSettingsTab(
                        state = state,
                        onIpChange = { viewModel.updateEspIp(it) },
                        onApiKeyChange = { viewModel.updateApiKey(it) },
                        onBudgetChange = { viewModel.updateBudgetLimit(it) },
                        onReset = { viewModel.resetEnergy() },
                        onSetEnergy = { viewModel.setEnergyValue(it) },
                        onSetBilling = { day, hour -> viewModel.setBilling(day, hour) },
                        onPushWatchNotification = { ctx ->
                            val msg = "⚡ Công suất: ${state.energyData.power}W | Dòng: ${state.energyData.current}A | Áp: ${state.energyData.voltage}V | Tạm tính: ${state.energyData.money}đ"
                            viewModel.sendWatchNotification(ctx, "⌚ DTV Energy Watch Status", msg)
                        }
                    )
                }

                // Floating AI Chat Button & Separate Floating Glass Window
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(16.dp),
                    contentAlignment = Alignment.BottomEnd
                ) {
                    if (!isChatOpen) {
                        FloatingActionButton(
                            onClick = { isChatOpen = true },
                            containerColor = LiquidSkyBlue,
                            contentColor = Color.White,
                            shape = CircleShape,
                            modifier = Modifier.shadow(12.dp, CircleShape)
                        ) {
                            Text(text = "🤖 AI", fontWeight = FontWeight.Black, fontSize = 14.sp)
                        }
                    } else {
                        val context = androidx.compose.ui.platform.LocalContext.current
                        FloatingWhiteGlassChatWindow(
                            state = state,
                            onClose = { isChatOpen = false },
                            onSend = { viewModel.sendAiPrompt(it, context) },
                            onSpeak = { text -> viewModel.speakText(context, text) }
                        )
                    }
                }
            }
        }
    }
}

// ----------------------------------------------------------------
//  TAB 0: WHITE LIQUID GLASS DASHBOARD
// ----------------------------------------------------------------
@Composable
fun WhiteDashboardTab(state: EnergyUiState, onOpenChat: () -> Unit) {
    val data = state.energyData
    val powerVal = data.power.toFloatOrNull() ?: 0f

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Offline Alert Banner (Zero Fake Data)
        item {
            if (!state.isConnected) {
                Surface(
                    color = LiquidRose.copy(alpha = 0.1f),
                    border = androidx.compose.foundation.BorderStroke(1.dp, LiquidRose.copy(alpha = 0.4f)),
                    shape = RoundedCornerShape(20.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(text = "⚠️ Chưa Kết Nối Thiết Bị ESP32", fontWeight = FontWeight.Bold, color = LiquidRose, fontSize = 13.sp)
                            Text(text = "App không tự bịa số liệu. Hãy kiểm tra IP trong Cấu Hình.", color = TextMuted, fontSize = 11.sp)
                        }
                    }
                }
            }
        }

        // 4 White Glass Gauges
        item {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    WhiteGaugeCard(
                        title = "Điện Áp",
                        value = "${data.voltage} V",
                        valueColor = LiquidSkyBlue,
                        modifier = Modifier.weight(1f)
                    )
                    WhiteGaugeCard(
                        title = "Dòng Điện",
                        value = "${data.current} A",
                        valueColor = LiquidAmber,
                        modifier = Modifier.weight(1f)
                    )
                }
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    WhiteGaugeCard(
                        title = "Công Suất Tức Thời",
                        value = "${data.power} W",
                        valueColor = if (powerVal > 2000f) LiquidRose else if (powerVal > 800f) LiquidAmber else LiquidEmerald,
                        modifier = Modifier.weight(1f)
                    )
                    WhiteGaugeCard(
                        title = "Tổng Điện Năng",
                        value = "${data.energy} kWh",
                        valueColor = TextPrimary,
                        modifier = Modifier.weight(1f)
                    )
                }
            }
        }

        // Liquid Glass Oscilloscope Waveform Canvas
        item {
            Surface(
                color = GlassCardWhite,
                border = androidx.compose.foundation.BorderStroke(1.dp, GlassCardBorder),
                shape = RoundedCornerShape(24.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .shadow(10.dp, shape = RoundedCornerShape(24.dp))
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "📈 LIQUID GLASS WAVEFORM",
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Black,
                            color = LiquidSkyBlue
                        )
                        Text(
                            text = if (powerVal > 2000f) "[ HIGH LOAD ]" else if (powerVal > 800f) "[ MEDIUM LOAD ]" else "[ NORMAL LOAD ]",
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            color = if (powerVal > 2000f) LiquidRose else if (powerVal > 800f) LiquidAmber else LiquidEmerald
                        )
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    Canvas(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(120.dp)
                            .clip(RoundedCornerShape(16.dp))
                            .background(Color(0xFF0F172A)) // Deep Contrast Background for Glass Glow
                    ) {
                        val width = size.width
                        val height = size.height

                        val gridStepY = height / 3
                        for (i in 1..2) {
                            drawLine(
                                color = Color.White.copy(alpha = 0.06f),
                                start = Offset(0f, gridStepY * i),
                                end = Offset(width, gridStepY * i),
                                strokeWidth = 1f
                            )
                        }

                        val samples = state.powerHistory
                        if (samples.size > 1) {
                            val stepX = width / (samples.size - 1)
                            val path = Path()

                            for (i in samples.indices) {
                                val v = samples[i].coerceIn(0f, 3500f)
                                val y = height - (v / 3500f * (height - 24f) + 12f)
                                val x = i * stepX

                                if (i == 0) path.moveTo(x, y)
                                else path.lineTo(x, y)
                            }

                            drawPath(
                                path = path,
                                color = LiquidSkyBlue,
                                style = Stroke(width = 3.5.dp.toPx())
                            )
                        }
                    }
                }
            }
        }
    }
}

// ----------------------------------------------------------------
//  TAB 1: EVN TARIFF TAB
// ----------------------------------------------------------------
@Composable
fun WhiteEvnTab(state: EnergyUiState) {
    val formatter = DecimalFormat("#,###")
    val evnCostFormatted = formatter.format(state.evnTotalCostVnd.toInt())

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        item {
            Surface(
                color = GlassCardWhite,
                border = androidx.compose.foundation.BorderStroke(1.dp, GlassCardBorder),
                shape = RoundedCornerShape(24.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .shadow(10.dp, shape = RoundedCornerShape(24.dp))
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Text(text = "🇻🇳 TIỀN ĐIỆN BẬC THANG EVN (VAT 8%)", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = LiquidAmber)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(text = "$evnCostFormatted VNĐ", fontSize = 34.sp, fontWeight = FontWeight.Black, color = LiquidAmber)
                    Text(text = "Số kWh tháng này: ${state.energyData.month} kWh", fontSize = 12.sp, color = TextMuted)
                }
            }
        }

        item {
            Surface(
                color = GlassCardWhite,
                border = androidx.compose.foundation.BorderStroke(1.dp, GlassCardBorder),
                shape = RoundedCornerShape(24.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .shadow(10.dp, shape = RoundedCornerShape(24.dp))
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Text(text = "📊 Chi Tiết 6 Bậc Điện EVN", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = TextPrimary)
                    Spacer(modifier = Modifier.height(12.dp))
                    state.evnTiers.forEach { tier ->
                        WhiteEvnTierItem(tier)
                        Spacer(modifier = Modifier.height(10.dp))
                    }
                }
            }
        }
    }
}

@Composable
fun WhiteEvnTierItem(tier: EvnTierInfo) {
    val progress = (tier.currentKwhInTier / tier.maxKwhInTier).coerceIn(0f, 1f)
    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                text = tier.tierName,
                fontSize = 12.sp,
                fontWeight = if (tier.isCurrentTier) FontWeight.Bold else FontWeight.Normal,
                color = if (tier.isCurrentTier) LiquidSkyBlue else TextMuted
            )
            Text(
                text = "${tier.currentKwhInTier.toInt()} kWh (${tier.pricePerKwh.toInt()}đ)",
                fontSize = 12.sp,
                fontWeight = FontWeight.Bold,
                color = if (tier.isCurrentTier) LiquidSkyBlue else TextPrimary
            )
        }
        Spacer(modifier = Modifier.height(4.dp))
        LinearProgressIndicator(
            progress = { progress },
            modifier = Modifier
                .fillMaxWidth()
                .height(6.dp)
                .clip(RoundedCornerShape(3.dp)),
            color = if (tier.isCurrentTier) LiquidSkyBlue else Color.LightGray.copy(alpha = 0.5f),
            trackColor = Color.LightGray.copy(alpha = 0.2f)
        )
    }
}

// ----------------------------------------------------------------
//  TAB 2: APPLIANCE DETECTOR
// ----------------------------------------------------------------
@Composable
fun WhiteApplianceTab(state: EnergyUiState, onDetect: () -> Unit) {
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        item {
            Surface(
                color = GlassCardWhite,
                border = androidx.compose.foundation.BorderStroke(1.dp, GlassCardBorder),
                shape = RoundedCornerShape(24.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .shadow(10.dp, shape = RoundedCornerShape(24.dp))
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Text(text = "🔍 Dấu Chân Điện Thiết Bị (AI Rust)", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = LiquidSkyBlue)
                    Spacer(modifier = Modifier.height(6.dp))
                    Text(text = "Phân tích công suất ${state.energyData.power}W và dòng điện ${state.energyData.current}A để suy đoán thiết bị đang bật.", fontSize = 12.sp, color = TextMuted)
                    Spacer(modifier = Modifier.height(14.dp))
                    Button(
                        onClick = onDetect,
                        colors = ButtonDefaults.buttonColors(containerColor = LiquidSkyBlue),
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(text = "BẮT ĐẦU PHÂN TÍCH AI", fontWeight = FontWeight.Bold, color = Color.White)
                    }
                }
            }
        }
    }
}

// ----------------------------------------------------------------
//  TAB 3: SETTINGS
// ----------------------------------------------------------------
@Composable
fun WhiteSettingsTab(
    state: EnergyUiState,
    onIpChange: (String) -> Unit,
    onApiKeyChange: (String) -> Unit,
    onBudgetChange: (Float) -> Unit,
    onReset: () -> Unit,
    onSetEnergy: (String) -> Unit,
    onSetBilling: (String, String) -> Unit,
    onPushWatchNotification: (android.content.Context) -> Unit
) {
    var ipVal by remember(state.espIp) { mutableStateOf(state.espIp) }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        item {
            Surface(
                color = GlassCardWhite,
                border = androidx.compose.foundation.BorderStroke(1.dp, GlassCardBorder),
                shape = RoundedCornerShape(24.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .shadow(10.dp, shape = RoundedCornerShape(24.dp))
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Text(text = "⚙️ Cấu Hình Địa Chỉ IP ESP32", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = LiquidSkyBlue)
                    Spacer(modifier = Modifier.height(8.dp))
                    OutlinedTextField(
                        value = ipVal,
                        onValueChange = { ipVal = it; onIpChange(it) },
                        label = { Text("IP ESP32 (Mặc định: 192.168.4.1)", fontWeight = FontWeight.SemiBold) },
                        textStyle = androidx.compose.ui.text.TextStyle(color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 15.sp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = TextPrimary,
                            unfocusedTextColor = TextPrimary,
                            focusedContainerColor = Color.White,
                            unfocusedContainerColor = Color(0xFFF8FAFC),
                            focusedBorderColor = LiquidSkyBlue,
                            unfocusedBorderColor = Color(0xFFCBD5E1),
                            focusedLabelColor = LiquidSkyBlue,
                            unfocusedLabelColor = TextMuted
                        ),
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            }
        }

        item {
            val context = androidx.compose.ui.platform.LocalContext.current
            Surface(
                color = GlassCardWhite,
                border = androidx.compose.foundation.BorderStroke(1.dp, GlassCardBorder),
                shape = RoundedCornerShape(24.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .shadow(10.dp, shape = RoundedCornerShape(24.dp))
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Text(text = "⌚ ĐỒNG HỒ THÔNG MINH HARMONYOS", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = LiquidSkyBlue)
                    Spacer(modifier = Modifier.height(6.dp))
                    Text(text = "Đẩy thông báo chỉ số điện năng & cảnh báo sang đồng hồ HarmonyOS (Huawei Watch GT/3/4/Fit) qua Huawei Health.", fontSize = 12.sp, color = TextMuted)
                    Spacer(modifier = Modifier.height(14.dp))
                    Button(
                        onClick = {
                            onPushWatchNotification(context)
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = LiquidEmerald),
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(text = "🔔 ĐẨY THÔNG BÁO SANG ĐỒNG HỒ", fontWeight = FontWeight.Bold, color = Color.White)
                    }
                }
            }
        }
    }
}

// ----------------------------------------------------------------
//  FLOATING SEPARATE WHITE GLASS AI CHAT WINDOW (Independent Scroll & Voice)
// ----------------------------------------------------------------
@Composable
fun FloatingWhiteGlassChatWindow(
    state: EnergyUiState,
    onClose: () -> Unit,
    onSend: (String) -> Unit,
    onSpeak: (String) -> Unit
) {
    var inputText by remember { mutableStateOf("") }
    val context = androidx.compose.ui.platform.LocalContext.current

    // Speech-To-Text Launcher
    val speechLauncher = androidx.activity.compose.rememberLauncherForActivityResult(
        contract = androidx.activity.result.contract.ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == android.app.Activity.RESULT_OK) {
            val spokenText = result.data?.getStringArrayListExtra(android.speech.RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()
            if (!spokenText.isNullOrBlank()) {
                inputText = spokenText
                onSend(spokenText)
            }
        }
    }

    Surface(
        color = Color(0xFDF8FAFC),
        border = androidx.compose.foundation.BorderStroke(1.5.dp, LiquidSkyBlue.copy(alpha = 0.5f)),
        shape = RoundedCornerShape(24.dp),
        modifier = Modifier
            .width(340.dp)
            .height(450.dp)
            .shadow(20.dp, shape = RoundedCornerShape(24.dp))
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            // Header
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(LiquidSkyBlue.copy(alpha = 0.1f))
                    .padding(horizontal = 14.dp, vertical = 10.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(text = "🤖 Trợ Lý Gemini AI Voice", fontWeight = FontWeight.Bold, color = LiquidSkyBlue, fontSize = 13.sp)
                Text(text = "✖️", modifier = Modifier.clickable { onClose() }, fontSize = 14.sp, color = TextMuted)
            }

            // INDEPENDENT SCROLLING CHAT LIST
            LazyColumn(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(state.chatMessages) { msg ->
                    WhiteChatBubble(msg, onSpeak = { onSpeak(it) })
                }
            }

            // Input Bar with Mic Button
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(10.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Mic Voice Command Button
                var isListening by remember { mutableStateOf(false) }

                IconButton(
                    onClick = {
                        val intent = android.content.Intent(android.speech.RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                            putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE_MODEL, android.speech.RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                            putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE, "vi-VN")
                            putExtra(android.speech.RecognizerIntent.EXTRA_PROMPT, "Nói câu hỏi về điện năng...")
                        }

                        try {
                            speechLauncher.launch(intent)
                        } catch (e: Exception) {
                            // Fallback: Direct SpeechRecognizer Service
                            if (android.speech.SpeechRecognizer.isRecognitionAvailable(context)) {
                                try {
                                    val recognizer = android.speech.SpeechRecognizer.createSpeechRecognizer(context)
                                    isListening = true
                                    recognizer.setRecognitionListener(object : android.speech.RecognitionListener {
                                        override fun onReadyForSpeech(params: android.os.Bundle?) {}
                                        override fun onBeginningOfSpeech() {}
                                        override fun onRmsChanged(rmsdB: Float) {}
                                        override fun onBufferReceived(buffer: ByteArray?) {}
                                        override fun onEndOfSpeech() { isListening = false }
                                        override fun onError(error: Int) {
                                            isListening = false
                                            android.widget.Toast.makeText(context, "Thử lại hoặc bật Google Voice Typing trong Cài đặt bàn phím", android.widget.Toast.LENGTH_LONG).show()
                                            recognizer.destroy()
                                        }
                                        override fun onResults(results: android.os.Bundle?) {
                                            isListening = false
                                            val matches = results?.getStringArrayList(android.speech.SpeechRecognizer.RESULTS_RECOGNITION)
                                            val text = matches?.firstOrNull()
                                            if (!text.isNullOrBlank()) {
                                                inputText = text
                                                onSend(text)
                                            }
                                            recognizer.destroy()
                                        }
                                        override fun onPartialResults(partialResults: android.os.Bundle?) {}
                                        override fun onEvent(eventType: Int, params: android.os.Bundle?) {}
                                    })
                                    recognizer.startListening(intent)
                                } catch (ex: Exception) {
                                    android.widget.Toast.makeText(context, "Vui lòng bật 'Google Voice Typing' hoặc 'Nhập giọng nói' trong Cài Đặt Bàn Phím", android.widget.Toast.LENGTH_LONG).show()
                                }
                            } else {
                                android.widget.Toast.makeText(context, "Máy chưa bật Nhập giọng nói. Vui lòng bật 'Google Voice Typing' trong Cài Đặt Bàn Phím", android.widget.Toast.LENGTH_LONG).show()
                            }
                        }
                    },
                    modifier = Modifier
                        .size(42.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .background(if (isListening) LiquidRose.copy(alpha = 0.2f) else LiquidPurple.copy(alpha = 0.12f))
                        .border(1.dp, if (isListening) LiquidRose else LiquidPurple.copy(alpha = 0.4f), RoundedCornerShape(12.dp))
                ) {
                    Text(text = if (isListening) "🎙️..." else "🎙️", fontSize = 16.sp)
                }

                OutlinedTextField(
                    value = inputText,
                    onValueChange = { inputText = it },
                    placeholder = { Text("Hỏi AI...", fontSize = 12.sp, color = TextMuted, fontWeight = FontWeight.SemiBold) },
                    textStyle = androidx.compose.ui.text.TextStyle(color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 14.sp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = TextPrimary,
                        unfocusedTextColor = TextPrimary,
                        focusedContainerColor = Color.White,
                        unfocusedContainerColor = Color(0xFFF8FAFC),
                        focusedBorderColor = LiquidSkyBlue,
                        unfocusedBorderColor = Color(0xFFCBD5E1)
                    ),
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(12.dp)
                )
                Button(
                    onClick = {
                        if (inputText.isNotBlank()) {
                            onSend(inputText)
                            inputText = ""
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = LiquidSkyBlue),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Text(text = "Gửi", color = Color.White, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

private fun String.isNull_or_empty(): Boolean = this.trim().isEmpty()

@Composable
fun WhiteGaugeCard(title: String, value: String, valueColor: Color, modifier: Modifier = Modifier) {
    Surface(
        color = GlassCardWhite,
        border = androidx.compose.foundation.BorderStroke(1.dp, GlassCardBorder),
        shape = RoundedCornerShape(20.dp),
        modifier = modifier.shadow(8.dp, shape = RoundedCornerShape(20.dp))
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(text = title.uppercase(), fontSize = 10.sp, fontWeight = FontWeight.Bold, color = TextMuted)
            Spacer(modifier = Modifier.height(4.dp))
            Text(text = value, fontSize = 24.sp, fontWeight = FontWeight.Black, color = valueColor)
        }
    }
}

@Composable
fun WhiteChatBubble(msg: ChatMessage, onSpeak: (String) -> Unit) {
    val isUser = msg.sender == MessageSender.USER
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start
    ) {
        Surface(
            color = if (isUser) LiquidSkyBlue.copy(alpha = 0.15f) else Color.White,
            border = androidx.compose.foundation.BorderStroke(
                1.dp,
                if (isUser) LiquidSkyBlue.copy(alpha = 0.3f) else Color.LightGray.copy(alpha = 0.4f)
            ),
            shape = RoundedCornerShape(14.dp),
            modifier = Modifier.widthIn(max = 260.dp)
        ) {
            Column(modifier = Modifier.padding(10.dp)) {
                Text(
                    text = msg.text,
                    color = TextPrimary,
                    fontSize = 12.sp
                )
                if (!isUser) {
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "🔊 NÓI TIẾNG VIỆT",
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold,
                        color = LiquidSkyBlue,
                        modifier = Modifier
                            .clip(RoundedCornerShape(6.dp))
                            .clickable { onSpeak(msg.text) }
                            .padding(2.dp)
                    )
                }
            }
        }
    }
}
