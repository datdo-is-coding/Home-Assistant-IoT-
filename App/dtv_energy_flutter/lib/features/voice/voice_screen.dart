import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import '../../models/voice_alias.dart';
import '../../providers/smart_home_providers.dart';

class VoiceScreen extends ConsumerStatefulWidget {
  const VoiceScreen({super.key});

  @override
  ConsumerState<VoiceScreen> createState() => _VoiceScreenState();
}

class _VoiceScreenState extends ConsumerState<VoiceScreen> {
  bool _localProcessing = true;
  double _sensitivity = 0.85;
  String _language = 'vi-VN';
  bool _showAdvanced = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final vocabularyAsync = ref.watch(voiceVocabularyStreamProvider);
    final vocabulary = vocabularyAsync.value ?? [];
    final totalAliases = vocabulary.fold<int>(0, (sum, item) => sum + item.aliases.length);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: Padding(
          padding: const EdgeInsets.only(left: 12),
          child: IconButton(
            icon: Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: isDark ? const Color(0xFF1E242B) : Colors.white,
                shape: BoxShape.circle,
                border: Border.all(
                  color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                ),
              ),
              child: Icon(
                Icons.arrow_back_ios_new_rounded,
                size: 16,
                color: theme.colorScheme.onSurface,
              ),
            ),
            onPressed: () => context.pop(),
          ),
        ),
      ),
      body: SafeArea(
        child: CustomScrollView(
          physics: const BouncingScrollPhysics(),
          slivers: [
            // Header
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
              sliver: SliverToBoxAdapter(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: const Color(0xFF00897B).withOpacity(0.12),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: const Icon(
                            Icons.keyboard_voice_rounded,
                            size: 28,
                            color: Color(0xFF00897B),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Điều khiển giọng nói',
                                style: TextStyle(
                                  fontSize: 24,
                                  fontWeight: FontWeight.w800,
                                  letterSpacing: -0.5,
                                  color: theme.colorScheme.onSurface,
                                ),
                              ),
                              Text(
                                '${vocabulary.length} thiết bị · $totalAliases khẩu lệnh đã học',
                                style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w500,
                                  color: theme.colorScheme.onSurfaceVariant,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),

                    // Privacy & On-device Engine Banner
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: isDark ? const Color(0xFF161A22) : Colors.white,
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                        ),
                      ),
                      child: Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: const Color(0xFF43A047).withOpacity(0.12),
                              shape: BoxShape.circle,
                            ),
                            child: const Icon(Icons.shield_rounded, size: 20, color: Color(0xFF43A047)),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Xử lý ngoại tuyến an toàn',
                                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  'Từ vựng được tự động cập nhật khi đổi tên thiết bị. Giọng nói được nhận diện trực tiếp trên phần cứng (Sherpa-ONNX).',
                                  style: TextStyle(
                                    fontSize: 12,
                                    height: 1.35,
                                    color: theme.colorScheme.onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Devices and Aliases List
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 8),
              sliver: SliverToBoxAdapter(
                child: Text(
                  'Từ vựng thiết bị đã nhận diện',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: theme.colorScheme.onSurface,
                  ),
                ),
              ),
            ),

            if (vocabulary.isEmpty)
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                sliver: SliverToBoxAdapter(
                  child: Container(
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      color: isDark ? const Color(0xFF1E242B) : Colors.white,
                      borderRadius: BorderRadius.circular(AppTheme.cardRadius),
                      border: Border.all(
                        color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                      ),
                    ),
                    child: Column(
                      children: [
                        Icon(Icons.mic_none_rounded, size: 36, color: theme.colorScheme.onSurfaceVariant),
                        const SizedBox(height: 10),
                        const Text(
                          'Chưa có thiết bị nào',
                          style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Từ vựng nhận diện giọng nói được tự động sinh khi thêm thiết bị mới vào Gateway.',
                          textAlign: TextAlign.center,
                          style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurfaceVariant),
                        ),
                      ],
                    ),
                  ),
                ),
              )
            else
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                sliver: SliverList(
                  delegate: SliverChildBuilderDelegate(
                    (context, index) {
                      final item = vocabulary[index];
                      return _VocabularyCard(
                        item: item,
                        onAddAlias: () => _showAddAliasDialog(context, item.deviceId, item.deviceName),
                        onRemoveAlias: (alias) async {
                          HapticFeedback.lightImpact();
                          debugPrint('[VOCAB][APP] User removed: $alias (deviceId: ${item.deviceId})');
                          try {
                            await ref.read(voiceRepositoryProvider).removeAlias(item.deviceId, alias);
                          } catch (e) {
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(content: Text('Không thể xóa khẩu lệnh: $e')),
                              );
                            }
                          }
                        },
                      );
                    },
                    childCount: vocabulary.length,
                  ),
                ),
              ),

            // Advanced Voice Settings
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 8),
              sliver: SliverToBoxAdapter(
                child: InkWell(
                  borderRadius: BorderRadius.circular(16),
                  onTap: () => setState(() => _showAdvanced = !_showAdvanced),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          'Cài đặt nâng cao nhận diện',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: theme.colorScheme.onSurface,
                          ),
                        ),
                        Icon(
                          _showAdvanced ? Icons.keyboard_arrow_up_rounded : Icons.keyboard_arrow_down_rounded,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),

            if (_showAdvanced)
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                sliver: SliverToBoxAdapter(
                  child: Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: isDark ? const Color(0xFF1E242B) : Colors.white,
                      borderRadius: BorderRadius.circular(22),
                      border: Border.all(
                        color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                      ),
                    ),
                    child: Column(
                      children: [
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Nhận diện cục bộ trên thiết bị', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                          subtitle: const Text('Không gửi âm thanh lên đám mây, bảo mật tuyệt đối', style: TextStyle(fontSize: 12)),
                          value: _localProcessing,
                          onChanged: (val) {
                            HapticFeedback.lightImpact();
                            setState(() => _localProcessing = val);
                          },
                        ),
                        const Divider(height: 24),
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Ngôn ngữ nhận diện', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                          trailing: DropdownButton<String>(
                            value: _language,
                            underline: const SizedBox(),
                            borderRadius: BorderRadius.circular(16),
                            items: const [
                              DropdownMenuItem(value: 'vi-VN', child: Text('Tiếng Việt (Việt Nam)')),
                              DropdownMenuItem(value: 'en-US', child: Text('English (US)')),
                            ],
                            onChanged: (val) {
                              if (val != null) setState(() => _language = val);
                            },
                          ),
                        ),
                        const Divider(height: 24),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Text('Độ nhạy từ kích hoạt (Hotword)', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                                Text('${(_sensitivity * 100).toInt()}%', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
                              ],
                            ),
                            Slider(
                              value: _sensitivity,
                              min: 0.5,
                              max: 1.0,
                              divisions: 10,
                              onChanged: (val) => setState(() => _sensitivity = val),
                            ),
                          ],
                        ),
                        const Divider(height: 24),
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: theme.colorScheme.primary.withOpacity(0.1),
                              shape: BoxShape.circle,
                            ),
                            child: Icon(Icons.analytics_outlined, size: 20, color: theme.colorScheme.primary),
                          ),
                          title: const Text('Chẩn đoán nhận diện Gateway', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                          subtitle: const Text('Kiểm tra từ vựng STT và hotwords đang hoạt động', style: TextStyle(fontSize: 12)),
                          trailing: const Icon(Icons.arrow_forward_ios_rounded, size: 14),
                          onTap: () => _showDiagnosticsDialog(context),
                        ),
                      ],
                    ),
                  ),
                ),
              ),

            const SliverToBoxAdapter(child: SizedBox(height: 48)),
          ],
        ),
      ),
    );
  }

  void _showAddAliasDialog(BuildContext context, String deviceId, String deviceName) {
    final textCtrl = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
          title: Text('Thêm khẩu lệnh cho "$deviceName"', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
          content: TextField(
            controller: textCtrl,
            autofocus: true,
            decoration: InputDecoration(
              hintText: 'Ví dụ: đèn góc phòng',
              filled: true,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Hủy'),
            ),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
              ),
              onPressed: () async {
                final alias = textCtrl.text.trim();
                if (alias.isNotEmpty) {
                  debugPrint('[VOCAB][APP] User added: $alias (deviceId: $deviceId)');
                  Navigator.pop(ctx);
                  try {
                    await ref.read(voiceRepositoryProvider).addAlias(deviceId, alias);
                  } catch (e) {
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text('Không thể thêm khẩu lệnh: $e')),
                      );
                    }
                  }
                }
              },
              child: const Text('Thêm'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _showDiagnosticsDialog(BuildContext context) async {
    showDialog(
      context: context,
      builder: (ctx) {
        return FutureBuilder<Map<String, dynamic>>(
          future: ref.read(gatewayClientProvider).getVoiceVocabularyDiagnostics(),
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const AlertDialog(
                content: SizedBox(
                  height: 100,
                  child: Center(child: CircularProgressIndicator()),
                ),
              );
            }
            if (snapshot.hasError) {
              return AlertDialog(
                title: const Text('Lỗi kiểm tra chẩn đoán'),
                content: Text('${snapshot.error}'),
                actions: [
                  TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Đóng')),
                ],
              );
            }
            final data = snapshot.data ?? {};
            final stt = data['stt_engine'] as Map<String, dynamic>? ?? {};
            final hotwords = (stt['hotwords'] as List<dynamic>?)?.map((e) => e.toString()).toList() ?? [];

            return AlertDialog(
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
              title: const Row(
                children: [
                  Icon(Icons.check_circle_outline_rounded, color: Colors.green, size: 22),
                  SizedBox(width: 8),
                  Text('Chẩn đoán STT Gateway', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                ],
              ),
              content: SizedBox(
                width: double.maxFinite,
                child: ListView(
                  shrinkWrap: true,
                  children: [
                    Text('• Kết nối Gateway: ${data['gateway_connected'] == true ? "Đã kết nối" : "Mất kết nối"}'),
                    Text('• Động cơ STT Sherpa-ONNX: ${stt['initialized'] == true ? "Hoạt động" : "Chờ khởi động"}'),
                    Text('• Tổng hotwords kích hoạt: ${data['total_active_hotwords'] ?? hotwords.length}'),
                    Text('• Tổng thiết bị có khẩu lệnh: ${data['total_stored_items'] ?? 0}'),
                    const SizedBox(height: 12),
                    const Text('Hotwords nhận diện gần nhất:', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
                    const SizedBox(height: 6),
                    Wrap(
                      spacing: 6,
                      runSpacing: 4,
                      children: hotwords.take(15).map((w) => Chip(
                        label: Text(w, style: const TextStyle(fontSize: 10)),
                        padding: EdgeInsets.zero,
                        visualDensity: VisualDensity.compact,
                      )).toList(),
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Đóng')),
              ],
            );
          },
        );
      },
    );
  }
}

class _VocabularyCard extends StatelessWidget {
  final VoiceVocabularyItem item;
  final VoidCallback onAddAlias;
  final ValueChanged<String> onRemoveAlias;

  const _VocabularyCard({
    required this.item,
    required this.onAddAlias,
    required this.onRemoveAlias,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1E242B) : Colors.white,
        borderRadius: BorderRadius.circular(AppTheme.cardRadius),
        border: Border.all(
          color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                item.deviceName,
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                ),
              ),
              IconButton(
                visualDensity: VisualDensity.compact,
                icon: const Icon(Icons.add_circle_outline_rounded, size: 20),
                tooltip: 'Thêm khẩu lệnh',
                onPressed: onAddAlias,
              ),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: [
              for (final alias in item.aliases)
                Chip(
                  label: Text(alias, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500)),
                  deleteIcon: const Icon(Icons.close_rounded, size: 14),
                  onDeleted: () => onRemoveAlias(alias),
                  backgroundColor: theme.colorScheme.primary.withOpacity(0.08),
                  side: BorderSide.none,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
            ],
          ),
        ],
      ),
    );
  }
}
