import 'package:flutter/material.dart';
import '../../data/model/voice_alias_model.dart';
import '../../data/services/firebase_realtime_service.dart';

class VoicePage extends StatefulWidget {
  const VoicePage({super.key});

  @override
  State<VoicePage> createState() => _VoicePageState();
}

class _VoicePageState extends State<VoicePage> {
  double _sensitivity = 0.85;
  bool _localKwsEnabled = true;
  final TextEditingController _aliasInputController = TextEditingController();

  @override
  void dispose() {
    _aliasInputController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final fb = FirebaseRealtimeService();

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 1. TIÊU ĐỀ
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Cấu Hình Giọng Nói & KWS',
                      style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        color: isDark ? Colors.white : const Color(0xFF1E293B),
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Quản lý từ khóa nhận diện offline trên SubBox ESP32-S3 và từ đồng nghĩa cho thiết bị',
                      style: TextStyle(
                        fontSize: 13,
                        color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                      ),
                    ),
                  ],
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: const Color(0xFF8B5CF6).withValues(alpha: isDark ? 0.2 : 0.1),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: const Color(0xFF8B5CF6)),
                  ),
                  child: const Row(
                    children: [
                      Icon(Icons.mic_rounded, color: Color(0xFF8B5CF6), size: 16),
                      SizedBox(width: 6),
                      Text(
                        'SubBox KWS Engine: Hoạt động',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF8B5CF6),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),

            const SizedBox(height: 24),

            // 2. THIẾT LẬP THÔNG SỐ SUBBOX
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: isDark ? const Color(0xFF1E293B) : Colors.white,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                  color: isDark ? const Color(0xFF334155) : Colors.grey.shade200,
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'THIẾT LẬP MICRO & ENGINE NHẬN DIỆN (ESP-SR)',
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 0.8,
                      color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Nhận diện Wake Word cục bộ (Local KWS)',
                              style: TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                                color: isDark ? Colors.white : const Color(0xFF1E293B),
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              'Xử lý trực tiếp trên chip ESP32-S3 không cần internet, độ trễ < 250ms.',
                              style: TextStyle(
                                fontSize: 12,
                                color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Switch(
                        value: _localKwsEnabled,
                        activeThumbColor: const Color(0xFF8B5CF6),
                        onChanged: (val) {
                          setState(() => _localKwsEnabled = val);
                        },
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  const Divider(height: 1),
                  const SizedBox(height: 16),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'Độ nhạy Micro & Thu âm',
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w700,
                              color: isDark ? Colors.white : const Color(0xFF1E293B),
                            ),
                          ),
                          Text(
                            '${(_sensitivity * 100).toInt()}%',
                            style: const TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w800,
                              color: Color(0xFF8B5CF6),
                            ),
                          ),
                        ],
                      ),
                      Slider(
                        value: _sensitivity,
                        min: 0.5,
                        max: 1.0,
                        divisions: 10,
                        activeColor: const Color(0xFF8B5CF6),
                        onChanged: (val) {
                          setState(() => _sensitivity = val);
                        },
                      ),
                    ],
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            // 3. DANH SÁCH TỪ ĐỒNG NGHĨA (ALIASES) THEO THIẾT BỊ
            Text(
              'TỪ KHÓA & TỪ ĐỒNG NGHĨA CỦA THIẾT BỊ (VOICE ALIASES)',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w800,
                letterSpacing: 0.8,
                color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
              ),
            ),
            const SizedBox(height: 14),

            ValueListenableBuilder<List<VoiceAliasModel>>(
              valueListenable: fb.voiceAliasesNotifier,
              builder: (context, aliasesList, child) {
                return ListView.separated(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: aliasesList.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 14),
                  itemBuilder: (context, index) {
                    final item = aliasesList[index];
                    return _buildAliasCard(context, item, isDark, fb);
                  },
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAliasCard(
    BuildContext context,
    VoiceAliasModel item,
    bool isDark,
    FirebaseRealtimeService fb,
  ) {
    final cardBg = isDark ? const Color(0xFF1E293B) : Colors.white;
    final borderColor = isDark ? const Color(0xFF334155) : Colors.grey.shade200;

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: const Color(0xFF8B5CF6).withValues(alpha: isDark ? 0.2 : 0.1),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Icon(Icons.mic_none_rounded, color: Color(0xFF8B5CF6), size: 20),
                  ),
                  const SizedBox(width: 12),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.deviceName,
                        style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w800,
                          color: isDark ? Colors.white : const Color(0xFF1E293B),
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${item.roomName} · Kênh ${item.channelKey.toUpperCase()} (${item.boxId})',
                        style: TextStyle(
                          fontSize: 11,
                          color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
              IconButton(
                tooltip: 'Thêm từ đồng nghĩa',
                icon: const Icon(Icons.add_circle_outline_rounded, color: Color(0xFF8B5CF6)),
                onPressed: () => _showAddAliasDialog(context, item, fb),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: item.aliases.map((alias) {
              return Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: isDark ? const Color(0xFF0F172A) : const Color(0xFFF1F5F9),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(
                    color: isDark ? const Color(0xFF334155) : Colors.grey.shade300,
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      '"$alias"',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: isDark ? Colors.grey.shade200 : const Color(0xFF334155),
                      ),
                    ),
                    const SizedBox(width: 6),
                    InkWell(
                      onTap: () {
                        final updated = List<String>.from(item.aliases)..remove(alias);
                        fb.updateVoiceAliases(item.boxId, item.channelKey, updated);
                      },
                      child: Icon(
                        Icons.close_rounded,
                        size: 14,
                        color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                      ),
                    ),
                  ],
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  void _showAddAliasDialog(
    BuildContext context,
    VoiceAliasModel item,
    FirebaseRealtimeService fb,
  ) {
    _aliasInputController.clear();
    showDialog(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          title: Text('Thêm từ gọi cho ${item.deviceName}'),
          content: TextField(
            controller: _aliasInputController,
            autofocus: true,
            decoration: const InputDecoration(
              hintText: 'Ví dụ: "bật đèn phòng khách"',
              border: OutlineInputBorder(),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Hủy'),
            ),
            ElevatedButton(
              onPressed: () {
                final text = _aliasInputController.text.trim();
                if (text.isNotEmpty && !item.aliases.contains(text)) {
                  final updated = List<String>.from(item.aliases)..add(text);
                  fb.updateVoiceAliases(item.boxId, item.channelKey, updated);
                }
                Navigator.pop(ctx);
              },
              child: const Text('Thêm'),
            ),
          ],
        );
      },
    );
  }
}
