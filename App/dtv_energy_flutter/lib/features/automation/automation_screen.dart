import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/app_theme.dart';
import '../../models/automation.dart';
import '../../providers/smart_home_providers.dart';
import '../../widgets/automation_card.dart';
import '../../widgets/scene_card.dart';

class AutomationScreen extends ConsumerWidget {
  const AutomationScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final scenesAsync = ref.watch(scenesStreamProvider);
    final automationsAsync = ref.watch(automationsStreamProvider);
    final devicesAsync = ref.watch(devicesStreamProvider);

    final scenes = scenesAsync.value ?? [];
    final automations = automationsAsync.value ?? [];
    final devices = devicesAsync.value ?? [];

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      body: SafeArea(
        child: CustomScrollView(
          physics: const BouncingScrollPhysics(),
          slivers: [
            // Header
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
              sliver: SliverToBoxAdapter(
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Tự động hóa',
                            style: TextStyle(
                              fontSize: 26,
                              fontWeight: FontWeight.w800,
                              letterSpacing: -0.5,
                              color: theme.colorScheme.onSurface,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            'Ngữ cảnh & luật điều khiển thông minh',
                            style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w500,
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      decoration: BoxDecoration(
                        color: isDark ? const Color(0xFF1E242B) : Colors.white,
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                        ),
                      ),
                      child: IconButton(
                        icon: const Icon(Icons.add_rounded, size: 22),
                        tooltip: 'Tạo tự động hóa mới',
                        onPressed: () => _showCreateAutomationSheet(context, ref, devices.length),
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // SCENES SECTION
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 14, 20, 8),
              sliver: SliverToBoxAdapter(
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Text(
                        'Ngữ cảnh một chạm',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: theme.colorScheme.onSurface,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      '${scenes.length} ngữ cảnh',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Scenes Grid or Empty State
            if (scenes.isEmpty)
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
                        Icon(Icons.palette_outlined, size: 36, color: theme.colorScheme.onSurfaceVariant),
                        const SizedBox(height: 10),
                        const Text(
                          'Chưa có ngữ cảnh nào',
                          style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Khi kết nối ActionBox với các thiết bị, các ngữ cảnh nhanh (Tắt tất cả, Đi ngủ, Buổi sáng) sẽ tự động sinh.',
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
                sliver: SliverGrid(
                  gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                    maxCrossAxisExtent: 220,
                    mainAxisExtent: 148,
                    crossAxisSpacing: 10,
                    mainAxisSpacing: 10,
                  ),
                  delegate: SliverChildBuilderDelegate(
                    (context, index) {
                      final scene = scenes[index];
                      return SceneCard(
                        scene: scene,
                        onActivate: () {
                          HapticFeedback.heavyImpact();
                          ref.read(sceneRepositoryProvider).activateScene(scene.id);
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Row(
                                children: [
                                  Icon(scene.icon, color: Colors.white, size: 18),
                                  const SizedBox(width: 10),
                                  Text('Đã kích hoạt ngữ cảnh "${scene.name}"'),
                                ],
                              ),
                              behavior: SnackBarBehavior.floating,
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                              duration: const Duration(seconds: 2),
                            ),
                          );
                        },
                      );
                    },
                    childCount: scenes.length,
                  ),
                ),
              ),

            // MY AUTOMATIONS HEADER
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 10),
              sliver: SliverToBoxAdapter(
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Text(
                        'Tự động hóa của tôi',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: theme.colorScheme.onSurface,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      '${automations.where((a) => a.enabled).length} đang bật',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // AUTOMATION LIST or Empty State
            if (automations.isEmpty)
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
                        Icon(Icons.auto_mode_rounded, size: 36, color: theme.colorScheme.onSurfaceVariant),
                        const SizedBox(height: 10),
                        const Text(
                          'Chưa có kịch bản tự động hóa',
                          style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Nhấn nút "+" ở trên hoặc chọn gợi ý bên dưới để thêm lịch trình tự động.',
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
                      final automation = automations[index];
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 10),
                        child: AutomationCard(
                          automation: automation,
                          onToggle: (enabled) {
                            ref.read(automationRepositoryProvider).toggleAutomation(automation.id, enabled);
                          },
                          onTap: () {
                            _showEditAutomationSheet(context, ref, automation);
                          },
                        ),
                      );
                    },
                    childCount: automations.length,
                  ),
                ),
              ),

            // SUGGESTED AUTOMATIONS
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 10),
              sliver: SliverToBoxAdapter(
                child: Text(
                  'Gợi ý hữu ích',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: theme.colorScheme.onSurface,
                  ),
                ),
              ),
            ),

            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              sliver: SliverToBoxAdapter(
                child: Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: isDark ? const Color(0xFF1E242B) : Colors.white,
                    borderRadius: BorderRadius.circular(AppTheme.cardRadius),
                    border: Border.all(
                      color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                    ),
                  ),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: const Color(0xFF00897B).withOpacity(0.12),
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: const Icon(
                          Icons.lightbulb_outline_rounded,
                          color: Color(0xFF00897B),
                          size: 26,
                        ),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Tiết kiệm điện khi vắng nhà',
                              style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
                            ),
                            const SizedBox(height: 3),
                            Text(
                              'Tự động ngắt các thiết bị công suất cao khi không có người ở nhà.',
                              style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurfaceVariant),
                            ),
                          ],
                        ),
                      ),
                      TextButton(
                        onPressed: () {
                          HapticFeedback.lightImpact();
                          final newAuto = Automation(
                            id: 'auto_${DateTime.now().millisecondsSinceEpoch}',
                            name: 'Tiết kiệm khi vắng nhà',
                            icon: Icons.energy_savings_leaf_rounded,
                            triggerText: 'Khi vắng nhà sau 30 phút',
                            deviceCount: devices.isNotEmpty ? devices.length : 1,
                            enabled: true,
                          );
                          ref.read(automationRepositoryProvider).addAutomation(newAuto);
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text('Đã thêm tự động hóa "Tiết kiệm khi vắng nhà"'),
                              behavior: SnackBarBehavior.floating,
                            ),
                          );
                        },
                        child: const Text('Thêm', style: TextStyle(fontWeight: FontWeight.w700)),
                      ),
                    ],
                  ),
                ),
              ),
            ),

            const SliverToBoxAdapter(
              child: SizedBox(height: 48),
            ),
          ],
        ),
      ),
    );
  }

  void _showCreateAutomationSheet(BuildContext context, WidgetRef ref, int deviceCount) {
    final nameCtrl = TextEditingController();
    final triggerCtrl = TextEditingController(text: 'Mỗi ngày lúc 22:30');

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) {
        final theme = Theme.of(ctx);
        final isDark = theme.brightness == Brightness.dark;

        return Container(
          padding: EdgeInsets.fromLTRB(20, 20, 20, MediaQuery.of(ctx).viewInsets.bottom + 20),
          decoration: BoxDecoration(
            color: isDark ? const Color(0xFF161A22) : Colors.white,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  decoration: BoxDecoration(
                    color: isDark ? Colors.white24 : Colors.black12,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 18),
              const Text(
                'Thêm tự động hóa mới',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: nameCtrl,
                decoration: InputDecoration(
                  labelText: 'Tên tự động hóa (Ví dụ: Chế độ ban đêm)',
                  filled: true,
                  fillColor: isDark ? const Color(0xFF1E242B) : const Color(0xFFF6F8FA),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: triggerCtrl,
                decoration: InputDecoration(
                  labelText: 'Điều kiện kích hoạt (Trigger)',
                  filled: true,
                  fillColor: isDark ? const Color(0xFF1E242B) : const Color(0xFFF6F8FA),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
                ),
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: theme.colorScheme.primary,
                    foregroundColor: theme.colorScheme.onPrimary,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
                  ),
                  onPressed: () {
                    if (nameCtrl.text.trim().isNotEmpty) {
                      final newAuto = Automation(
                        id: 'auto_${DateTime.now().millisecondsSinceEpoch}',
                        name: nameCtrl.text.trim(),
                        icon: Icons.alarm_rounded,
                        triggerText: triggerCtrl.text.trim(),
                        deviceCount: deviceCount > 0 ? deviceCount : 1,
                        enabled: true,
                      );
                      ref.read(automationRepositoryProvider).addAutomation(newAuto);
                      Navigator.pop(ctx);
                    }
                  },
                  child: const Text('Lưu kịch bản', style: TextStyle(fontWeight: FontWeight.w700)),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  void _showEditAutomationSheet(BuildContext context, WidgetRef ref, Automation automation) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) {
        final theme = Theme.of(ctx);
        final isDark = theme.brightness == Brightness.dark;

        return Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: isDark ? const Color(0xFF161A22) : Colors.white,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                automation.name,
                style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 8),
              Text(
                'Điều kiện: ${automation.triggerText}',
                style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
              ),
              const SizedBox(height: 20),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.delete_outline_rounded, color: Colors.red),
                title: const Text('Xóa tự động hóa này', style: TextStyle(color: Colors.red, fontWeight: FontWeight.w600)),
                onTap: () {
                  HapticFeedback.mediumImpact();
                  ref.read(automationRepositoryProvider).deleteAutomation(automation.id);
                  Navigator.pop(ctx);
                },
              ),
            ],
          ),
        );
      },
    );
  }
}
