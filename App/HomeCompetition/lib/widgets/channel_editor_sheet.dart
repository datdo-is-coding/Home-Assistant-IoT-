import 'package:flutter/material.dart';
import '../models/device.dart';

class ChannelEditorSheet extends StatefulWidget {
  final String channelLabel;
  final String initialName;
  final DeviceType initialType;
  final List<String> initialAliases;
  final Future<void> Function(
      String name, DeviceType type, List<String> aliases) onSave;

  const ChannelEditorSheet(
      {super.key,
      required this.channelLabel,
      required this.initialName,
      required this.initialType,
      this.initialAliases = const [],
      required this.onSave});

  @override
  State<ChannelEditorSheet> createState() => _ChannelEditorSheetState();
}

class _ChannelEditorSheetState extends State<ChannelEditorSheet> {
  late final name = TextEditingController(text: widget.initialName);
  late final aliases = TextEditingController(
      text: widget.initialAliases.isEmpty
          ? widget.initialName
          : widget.initialAliases.join(', '));
  late DeviceType type = widget.initialType;
  late bool followsName = widget.initialAliases.isEmpty ||
      (widget.initialAliases.length == 1 &&
          widget.initialAliases.single.trim().toLowerCase() ==
              widget.initialName.trim().toLowerCase());
  bool saving = false;
  String? error;

  @override
  void dispose() {
    name.dispose();
    aliases.dispose();
    super.dispose();
  }

  Future<void> save() async {
    final label = name.text.trim();
    final spoken = aliases.text
        .split(',')
        .map((a) => a.trim())
        .where((a) => a.isNotEmpty)
        .toSet()
        .toList();
    if (label.isEmpty ||
        label.length > 120 ||
        spoken.length > 8 ||
        spoken.any((a) => a.length > 120)) {
      setState(() => error =
          'Nhập tên tối đa 120 ký tự và không quá 8 tên gọi giọng nói.');
      return;
    }
    setState(() {
      saving = true;
      error = null;
    });
    try {
      await widget.onSave(label, type, spoken.isEmpty ? [label] : spoken);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Đã lưu tên, loại thiết bị và tên gọi giọng nói.')));
      Navigator.pop(context);
    } catch (e) {
      if (mounted)
        setState(() => error =
            'Chưa lưu được cấu hình. ${e.toString().replaceFirst('Exception: ', '')}');
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
        canPop: !saving,
        child: SingleChildScrollView(
          padding: EdgeInsets.fromLTRB(
              20, 20, 20, MediaQuery.of(context).viewInsets.bottom + 24),
          child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('Cấu hình ${widget.channelLabel}',
                          style: const TextStyle(
                              fontSize: 18, fontWeight: FontWeight.w800)),
                      IconButton(
                          onPressed:
                              saving ? null : () => Navigator.pop(context),
                          icon: const Icon(Icons.close)),
                    ]),
                const SizedBox(height: 16),
                TextField(
                    key: const Key('channel-name'),
                    controller: name,
                    enabled: !saving,
                    decoration: const InputDecoration(
                        labelText: 'Tên thiết bị',
                        border: OutlineInputBorder()),
                    onChanged: (value) {
                      if (followsName) aliases.text = value;
                    }),
                const SizedBox(height: 14),
                DropdownButtonFormField<DeviceType>(
                    value: type,
                    decoration: const InputDecoration(
                        labelText: 'Loại thiết bị',
                        border: OutlineInputBorder()),
                    items: const [
                      DropdownMenuItem(
                          value: DeviceType.light,
                          child: Text('💡 Đèn chiếu sáng')),
                      DropdownMenuItem(
                          value: DeviceType.fan,
                          child: Text('💨 Quạt làm mát')),
                      DropdownMenuItem(
                          value: DeviceType.socket,
                          child: Text('⚡ Ổ cắm điện')),
                      DropdownMenuItem(
                          value: DeviceType.airConditioner,
                          child: Text('❄️ Điều hòa nhiệt độ')),
                      DropdownMenuItem(
                          value: DeviceType.custom,
                          child: Text('🔌 Tải tùy chỉnh')),
                    ],
                    onChanged: saving
                        ? null
                        : (value) => setState(() => type = value!)),
                const SizedBox(height: 14),
                TextField(
                    key: const Key('channel-aliases'),
                    controller: aliases,
                    enabled: !saving,
                    decoration: const InputDecoration(
                        labelText: 'Tên gọi giọng nói',
                        helperText:
                            'Tự điền theo tên thiết bị. Có thể sửa riêng; nhiều tên cách nhau bằng dấu phẩy.',
                        helperMaxLines: 2,
                        border: OutlineInputBorder()),
                    onChanged: (value) => followsName = value.trim().isEmpty ||
                        value.trim().toLowerCase() ==
                            name.text.trim().toLowerCase()),
                if (error != null)
                  Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: Text(error!,
                          key: const Key('channel-save-error'),
                          style: TextStyle(
                              color: Theme.of(context).colorScheme.error))),
                const SizedBox(height: 20),
                SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                        onPressed: saving ? null : save,
                        style: FilledButton.styleFrom(
                            padding: const EdgeInsets.symmetric(vertical: 14)),
                        child: saving
                            ? const Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                    SizedBox(
                                        width: 16,
                                        height: 16,
                                        child: CircularProgressIndicator(
                                            strokeWidth: 2)),
                                    SizedBox(width: 10),
                                    Text('Đang lưu và đồng bộ…'),
                                  ])
                            : const Text('Lưu thay đổi & Đồng bộ'))),
              ]),
        ),
      );
}
