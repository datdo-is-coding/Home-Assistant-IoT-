import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/smart_home_providers.dart';
import '../../widgets/flagship_backdrop.dart';
import '../../widgets/home_connection_name.dart';
import '../../widgets/soft_3d_decorations.dart';

String _requestKey() =>
    'ir_${DateTime.now().microsecondsSinceEpoch}_${Random.secure().nextInt(1 << 30)}';
List<Map<String, dynamic>> _rows(dynamic value) => value is List
    ? value.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList()
    : [];
String _caption(String key, String original) =>
    const {
      'off': 'Tắt',
      'on': 'Bật',
      'power_off': 'Tắt',
      'power_on': 'Bật',
      'power': 'Nguồn',
      'pwr_sw': 'Nguồn',
      'on_off': 'Nguồn',
      'vol_up': 'Âm lượng +',
      'vol_down': 'Âm lượng −',
      'vol_plus': 'Âm lượng +',
      'vol_minus': 'Âm lượng −',
      'mute': 'Tắt tiếng',
      'up': 'Lên',
      'down': 'Xuống',
      'left': 'Trái',
      'right': 'Phải',
      'ok': 'OK',
      'menu': 'Menu',
      'back': 'Quay lại',
      'input': 'Nguồn vào',
      'tmp_up': 'Tăng 1°',
      'tmp_dn': 'Giảm 1°',
    }[key] ??
    original;

class InfraredScreen extends ConsumerStatefulWidget {
  const InfraredScreen({super.key});
  @override
  ConsumerState<InfraredScreen> createState() => _InfraredScreenState();
}

class _InfraredScreenState extends ConsumerState<InfraredScreen> {
  Map<String, dynamic>? data, selected;
  Map<String, dynamic> draft = {};
  bool loading = true, busy = false;
  String? error, notice;

  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    try {
      final result =
          await ref.read(gatewayClientProvider).request('/api/v1/ir/bootstrap');
      if (mounted)
        setState(() {
          data = result;
          loading = false;
          error = null;
        });
    } catch (e) {
      if (mounted)
        setState(() {
          error = '$e';
          loading = false;
        });
    }
  }

  void choose(Map<String, dynamic> remote) => setState(() {
        selected = remote;
        draft =
            Map<String, dynamic>.from(remote['requested_state'] as Map? ?? {});
        final temperatures = (remote['temperatures'] as List? ?? [])
            .whereType<num>()
            .map((v) => v.toInt())
            .toList();
        if (remote['full_climate'] == false &&
            temperatures.isNotEmpty &&
            !temperatures.contains(draft['temperature']))
          draft['temperature'] = temperatures.first;
        error = null;
        notice = null;
      });

  Future<void> send(Map<String, dynamic> body) async {
    if (busy || selected == null) return;
    HapticFeedback.lightImpact();
    setState(() {
      busy = true;
      error = null;
      notice = null;
    });
    try {
      final result = await ref.read(gatewayClientProvider).request(
          '/api/v1/ir/remotes/${selected!['remote_id']}/send',
          method: 'POST',
          body: {...body, 'idempotency_key': _requestKey()});
      if (mounted)
        setState(
            () => notice = result['message']?.toString() ?? 'Đã phát lệnh.');
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> add() async {
    final result = await showModalBottomSheet<Map<String, dynamic>>(
        context: context,
        isScrollControlled: true,
        useSafeArea: true,
        builder: (_) => _AddRemoteSheet(data: data!));
    if (!mounted || result == null) return;
    choose(result);
    await load();
  }

  Future<void> learn() async {
    var text = '', command = 'off', temperature = 26;
    final capture = await showDialog<Map<String, String>>(
        context: context,
        builder: (ctx) => StatefulBuilder(
            builder: (ctx, update) => AlertDialog(
                  title: const Text('Học từ remote gốc'),
                  content: SingleChildScrollView(
                      child: Column(mainAxisSize: MainAxisSize.min, children: [
                    DropdownButtonFormField<String>(
                        initialValue: command,
                        decoration:
                            const InputDecoration(labelText: 'Lệnh cần học'),
                        items: const [
                          DropdownMenuItem(value: 'on', child: Text('Bật')),
                          DropdownMenuItem(value: 'off', child: Text('Tắt')),
                          DropdownMenuItem(
                              value: 'temperature',
                              child: Text('Đặt nhiệt độ')),
                          DropdownMenuItem(
                              value: 'custom', child: Text('Nút khác')),
                        ],
                        onChanged: (v) => update(() => command = v!)),
                    const SizedBox(height: 16),
                    if (command == 'temperature') ...[
                      DropdownButtonFormField<int>(
                          initialValue: temperature,
                          decoration: const InputDecoration(
                              labelText: 'Nhiệt độ trên remote'),
                          items: [
                            for (var t = 16; t <= 30; t++)
                              DropdownMenuItem(value: t, child: Text('$t°C'))
                          ],
                          onChanged: (v) => update(() => temperature = v!)),
                      const SizedBox(height: 12),
                      const Text(
                          'Bật điều hòa trên remote, chọn đúng nhiệt độ rồi phát lệnh. Mã phải chứa mức nhiệt độ; nút +/− tương đối không thay thế được.'),
                    ],
                    if (command == 'custom')
                      TextField(
                          onChanged: (value) => text = value,
                          autofocus: true,
                          maxLength: 100,
                          decoration: const InputDecoration(
                              labelText: 'Tên lệnh',
                              hintText: 'Ví dụ: Đảo gió')),
                  ])),
                  actions: [
                    TextButton(
                        onPressed: () => Navigator.pop(ctx),
                        child: const Text('Hủy')),
                    FilledButton(
                        onPressed: () {
                          if (command == 'custom' && text.trim().isEmpty)
                            return;
                          Navigator.pop(ctx, {
                            'key': command == 'temperature'
                                ? 'temp_$temperature'
                                : command == 'custom'
                                    ? 'key_${DateTime.now().microsecondsSinceEpoch}'
                                    : command,
                            'label': command == 'temperature'
                                ? 'Đặt $temperature°C'
                                : command == 'on'
                                    ? 'Bật'
                                    : command == 'off'
                                        ? 'Tắt'
                                        : text.trim()
                          });
                        },
                        child: const Text('Bắt đầu'))
                  ],
                )));
    if (!mounted || capture == null || selected == null) return;
    setState(() {
      busy = true;
      error = null;
      notice =
          'Hướng remote vào mắt thu SubBox và bấm lệnh ${capture['label']} trong 8 giây.';
    });
    try {
      final result = await ref.read(gatewayClientProvider).request(
          '/api/v1/ir/remotes/${selected!['remote_id']}/learn',
          method: 'POST',
          timeout: const Duration(seconds: 25),
          body: capture);
      if (mounted)
        setState(() {
          selected = result;
          draft = Map<String, dynamic>.from(
              result['requested_state'] as Map? ?? {});
          final temperatures = (result['temperatures'] as List? ?? []);
          if (temperatures.isNotEmpty &&
              !temperatures.contains(draft['temperature']))
            draft['temperature'] = temperatures.first;
          notice = 'Đã học “${capture['label']}”.';
        });
    } catch (e) {
      if (mounted)
        setState(() {
          error = '$e';
          notice = null;
        });
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> configureReceiver() async {
    final parents = _rows(data?['subboxes']);
    final node = await showDialog<Map<String, dynamic>>(
        context: context,
        builder: (ctx) =>
            SimpleDialog(title: const Text('Mắt thu hồng ngoại'), children: [
              for (final p in parents)
                SimpleDialogOption(
                    onPressed: () => Navigator.pop(ctx, p),
                    child: Text(p['room'].toString()))
            ]));
    if (!mounted || node == null) return;
    var enabled = node['rx'] == true;
    final confirmed = await showDialog<bool>(
        context: context,
        builder: (ctx) => StatefulBuilder(
            builder: (ctx, update) => AlertDialog(
                    title: const Text('Phần cứng SubBox'),
                    content: Column(mainAxisSize: MainAxisSize.min, children: [
                      CheckboxListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Đã lắp mắt thu hồng ngoại'),
                          value: enabled,
                          onChanged: node['rx_supported'] == true
                              ? (v) => update(() => enabled = v!)
                              : null),
                      Text(node['rx_supported'] == true
                          ? 'Chỉ bật khi đã có mắt thu. LED phát không thu được mã remote.'
                          : 'SubBox cần firmware mới hỗ trợ học IR.'),
                    ]),
                    actions: [
                      TextButton(
                          onPressed: () => Navigator.pop(ctx),
                          child: const Text('Hủy')),
                      FilledButton(
                          onPressed: node['rx_supported'] == true
                              ? () => Navigator.pop(ctx, true)
                              : null,
                          child: const Text('Lưu'))
                    ])));
    if (!mounted || confirmed != true) return;
    setState(() => busy = true);
    try {
      final result = await ref.read(gatewayClientProvider).request(
          '/api/v1/ir/receivers/${node['node_id']}',
          method: 'POST',
          body: {'enabled': enabled});
      if (mounted) setState(() => data = result);
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> rename() async {
    final value = await showDialog<Map<String, dynamic>>(
        context: context, builder: (_) => _RemoteNameDialog(remote: selected!));
    if (!mounted || value == null) return;
    setState(() => busy = true);
    try {
      final result = await ref.read(gatewayClientProvider).request(
          '/api/v1/ir/remotes/${selected!['remote_id']}/configure',
          method: 'POST',
          body: value);
      if (mounted) {
        choose(result);
        await load();
      }
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> remove() async {
    final yes = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
                title: const Text('Xóa remote?'),
                content: Text(selected!['name'].toString()),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(ctx, false),
                      child: const Text('Hủy')),
                  TextButton(
                      onPressed: () => Navigator.pop(ctx, true),
                      child: const Text('Xóa'))
                ]));
    if (yes != true || !mounted) return;
    setState(() => busy = true);
    try {
      await ref.read(gatewayClientProvider).request(
          '/api/v1/ir/remotes/${selected!['remote_id']}',
          method: 'DELETE');
      if (mounted)
        setState(() {
          selected = null;
          busy = false;
        });
      await load();
    } catch (e) {
      if (mounted)
        setState(() {
          error = '$e';
          busy = false;
        });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    final remotes = _rows(data?['remotes']);
    final canLearn = selected != null &&
        _rows(data?['subboxes']).any(
            (n) => n['node_id'] == selected!['node_id'] && n['rx'] == true);
    return PopScope(
      canPop: selected == null && !busy,
      onPopInvokedWithResult: (popped, _) {
        if (!popped && !busy) setState(() => selected = null);
      },
      child: FlagshipBackdrop(
          child: Scaffold(
        backgroundColor: Colors.transparent,
        appBar: AppBar(
            backgroundColor: Colors.transparent,
            leading: IconButton(
                tooltip: 'Quay lại',
                icon: const Icon(Icons.arrow_back_rounded),
                onPressed: busy
                    ? null
                    : () {
                        if (selected != null)
                          setState(() => selected = null);
                        else
                          Navigator.pop(context);
                      }),
            title: Text(selected?['name']?.toString() ?? 'Remote'),
            actions: [
              if (data != null)
                IconButton(
                    tooltip: 'Mắt thu hồng ngoại',
                    onPressed: busy ? null : configureReceiver,
                    icon: const Icon(Icons.sensors_rounded)),
              if (selected == null && data != null)
                IconButton(
                    tooltip: 'Thêm remote',
                    onPressed: busy ? null : add,
                    icon: const Icon(Icons.add_rounded)),
              if (selected != null)
                IconButton(
                    tooltip: 'Tên và giọng nói',
                    onPressed: busy ? null : rename,
                    icon: const Icon(Icons.edit_outlined)),
              if (selected != null)
                IconButton(
                    tooltip: 'Xóa remote',
                    onPressed: busy ? null : remove,
                    icon: const Icon(Icons.delete_outline_rounded))
            ]),
        body: loading
            ? const Center(child: CircularProgressIndicator())
            : ListView(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 32),
                children: [
                  const HomeConnectionName(),
                  if (error != null)
                    Padding(
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        child: Text(error!,
                            style: TextStyle(color: theme.colorScheme.error))),
                  if (data == null)
                    TextButton(
                        onPressed: () {
                          setState(() => loading = true);
                          load();
                        },
                        child: const Text('Thử lại')),
                  if (busy) const LinearProgressIndicator(),
                  if (notice != null)
                    Padding(
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        child: Text(notice!)),
                  if (selected == null && data != null) ...[
                    const SizedBox(height: 16),
                    if (remotes.isEmpty)
                      Padding(
                          padding: const EdgeInsets.symmetric(vertical: 32),
                          child: Column(children: [
                            const Icon(Icons.settings_remote_rounded, size: 44),
                            const SizedBox(height: 16),
                            const Text(
                                'Thêm TV, điều hòa hoặc remote của bạn.'),
                            const SizedBox(height: 20),
                            FilledButton.icon(
                                onPressed: add,
                                icon: const Icon(Icons.add_rounded),
                                label: const Text('Thêm remote')),
                          ])),
                    for (final remote in remotes)
                      Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: DecoratedBox(
                              decoration: Soft3DDecorations.card(isDark: dark),
                              child: ListTile(
                                  leading: Icon(
                                      remote['category'] == 'air_conditioner'
                                          ? Icons.ac_unit_rounded
                                          : Icons.settings_remote_rounded),
                                  title: Text(remote['name'].toString()),
                                  subtitle: Text(
                                      '${remote['brand']} · ${remote['model']}'),
                                  trailing:
                                      const Icon(Icons.chevron_right_rounded),
                                  onTap: () => choose(remote)))),
                  ],
                  if (selected != null) ...[
                    const SizedBox(height: 14),
                    if (selected!['climate'] == true &&
                        selected!['full_climate'] != false)
                      Container(
                        decoration: Soft3DDecorations.card(
                            isDark: dark,
                            isActive: true,
                            accentColor: const Color(0xFF56ACB1),
                            radius: 24),
                        padding: const EdgeInsets.all(20),
                        child: Column(children: [
                          Text('Cấu hình sẽ gửi',
                              style: theme.textTheme.bodySmall),
                          Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                IconButton(
                                    tooltip: 'Giảm nhiệt độ',
                                    onPressed: busy ||
                                            (draft['temperature'] as num? ??
                                                    26) <=
                                                16
                                        ? null
                                        : () => setState(() =>
                                            draft['temperature'] =
                                                (draft['temperature'] as num? ??
                                                            26)
                                                        .toInt() -
                                                    1),
                                    icon: const Icon(Icons.remove_rounded)),
                                Flexible(
                                    child: Padding(
                                        padding: const EdgeInsets.all(16),
                                        child: Text(
                                            '${draft['temperature'] ?? 26}°',
                                            style: const TextStyle(
                                                fontSize: 54,
                                                fontWeight: FontWeight.w600,
                                                letterSpacing: -2)))),
                                IconButton(
                                    tooltip: 'Tăng nhiệt độ',
                                    onPressed: busy ||
                                            (draft['temperature'] as num? ??
                                                    26) >=
                                                30
                                        ? null
                                        : () => setState(() =>
                                            draft['temperature'] =
                                                (draft['temperature'] as num? ??
                                                            26)
                                                        .toInt() +
                                                    1),
                                    icon: const Icon(Icons.add_rounded)),
                              ]),
                          SwitchListTile(
                              contentPadding: EdgeInsets.zero,
                              title: const Text('Nguồn'),
                              value: draft['power'] == true,
                              onChanged: busy
                                  ? null
                                  : (value) =>
                                      setState(() => draft['power'] = value)),
                          DropdownButtonFormField<String>(
                              initialValue: draft['mode']?.toString() ?? 'cool',
                              decoration:
                                  const InputDecoration(labelText: 'Chế độ'),
                              items: const [
                                DropdownMenuItem(
                                    value: 'cool', child: Text('Làm lạnh')),
                                DropdownMenuItem(
                                    value: 'heat', child: Text('Sưởi')),
                                DropdownMenuItem(
                                    value: 'dry', child: Text('Hút ẩm')),
                                DropdownMenuItem(
                                    value: 'auto', child: Text('Tự động')),
                                DropdownMenuItem(
                                    value: 'fan', child: Text('Quạt'))
                              ],
                              onChanged: busy
                                  ? null
                                  : (v) => setState(() => draft['mode'] = v)),
                          const SizedBox(height: 14),
                          DropdownButtonFormField<int>(
                              initialValue: (draft['fan'] as num? ?? 0).toInt(),
                              decoration: const InputDecoration(
                                  labelText: 'Tốc độ quạt'),
                              items: [
                                const DropdownMenuItem(
                                    value: 0, child: Text('Tự động')),
                                for (var i = 1; i <= 5; i++)
                                  DropdownMenuItem(
                                      value: i, child: Text('Mức $i'))
                              ],
                              onChanged: busy
                                  ? null
                                  : (v) => setState(() => draft['fan'] = v)),
                          SwitchListTile(
                              contentPadding: EdgeInsets.zero,
                              title: const Text('Đảo gió'),
                              value: draft['swing'] == true,
                              onChanged: busy
                                  ? null
                                  : (v) => setState(() => draft['swing'] = v)),
                          const SizedBox(height: 12),
                          SizedBox(
                              width: double.infinity,
                              child: FilledButton.icon(
                                  onPressed: busy
                                      ? null
                                      : () => send({
                                            'state':
                                                Map<String, dynamic>.from(draft)
                                          }),
                                  icon:
                                      const Icon(Icons.wifi_tethering_rounded),
                                  label: const Text('Phát lệnh'))),
                        ]),
                      ),
                    if (selected!['full_climate'] == false &&
                        selected!['climate'] == true)
                      Container(
                          decoration: Soft3DDecorations.card(
                              isDark: dark, isActive: true),
                          padding: const EdgeInsets.all(20),
                          child: Column(children: [
                            const Text('Nhiệt độ đã học'),
                            const SizedBox(height: 12),
                            DropdownButtonFormField<int>(
                                initialValue: (selected!['temperatures']
                                            as List)
                                        .contains(draft['temperature'])
                                    ? draft['temperature'] as int
                                    : (selected!['temperatures'] as List).first
                                        as int,
                                items: [
                                  for (final t
                                      in selected!['temperatures'] as List)
                                    DropdownMenuItem(
                                        value: t as int, child: Text('$t°C'))
                                ],
                                onChanged: busy
                                    ? null
                                    : (v) => setState(
                                        () => draft['temperature'] = v)),
                            const SizedBox(height: 16),
                            FilledButton(
                                onPressed: busy
                                    ? null
                                    : () => send({
                                          'state': {
                                            'temperature':
                                                draft['temperature'] ??
                                                    (selected!['temperatures']
                                                            as List)
                                                        .first
                                          }
                                        }),
                                child: const Text('Đặt nhiệt độ')),
                          ])),
                    const SizedBox(height: 16),
                    Wrap(
                        spacing: 10,
                        runSpacing: 10,
                        children: _rows(selected!['buttons'])
                            .map((button) => OutlinedButton(
                                onPressed: busy
                                    ? null
                                    : () => send({'key': button['key']}),
                                child: Text(_caption(button['key'].toString(),
                                    button['label'].toString()))))
                            .toList()),
                    const SizedBox(height: 20),
                    OutlinedButton.icon(
                        onPressed: busy || !canLearn ? null : learn,
                        icon: const Icon(Icons.add_rounded),
                        label: const Text('Học nút từ remote gốc')),
                    const SizedBox(height: 12),
                    Text(
                        'Hồng ngoại không báo lại trạng thái thực của thiết bị.',
                        style: theme.textTheme.bodySmall),
                    if (!canLearn)
                      Text('SubBox này chưa có mắt thu IR để học nút.',
                          style: theme.textTheme.bodySmall),
                  ],
                ],
              ),
      )),
    );
  }
}

class _RemoteNameDialog extends StatefulWidget {
  const _RemoteNameDialog({required this.remote});
  final Map<String, dynamic> remote;
  @override
  State<_RemoteNameDialog> createState() => _RemoteNameDialogState();
}

class _RemoteNameDialogState extends State<_RemoteNameDialog> {
  late final TextEditingController name, alias;
  String? error;
  @override
  void initState() {
    super.initState();
    name = TextEditingController(text: widget.remote['name'].toString());
    alias = TextEditingController(
        text:
            (widget.remote['aliases'] as List? ?? []).firstOrNull?.toString() ??
                name.text);
  }

  @override
  void dispose() {
    name.dispose();
    alias.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
          title: const Text('Tên và giọng nói'),
          content: SingleChildScrollView(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(
                controller: name,
                maxLength: 100,
                decoration: const InputDecoration(labelText: 'Tên thiết bị')),
            TextField(
                controller: alias,
                maxLength: 100,
                decoration:
                    const InputDecoration(labelText: 'Tên gọi giọng nói')),
            if (error != null)
              Text(error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ])),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Hủy')),
            FilledButton(
                onPressed: () {
                  if (name.text.trim().isEmpty || alias.text.trim().isEmpty) {
                    setState(() => error = 'Nhập tên và tên gọi giọng nói.');
                    return;
                  }
                  Navigator.pop(context, {
                    'name': name.text.trim(),
                    'aliases': [alias.text.trim()]
                  });
                },
                child: const Text('Lưu'))
          ]);
}

class _AddRemoteSheet extends ConsumerStatefulWidget {
  const _AddRemoteSheet({required this.data});
  final Map<String, dynamic> data;
  @override
  ConsumerState<_AddRemoteSheet> createState() => _AddRemoteSheetState();
}

class _AddRemoteSheetState extends ConsumerState<_AddRemoteSheet> {
  final name = TextEditingController(text: 'Điều hòa Panasonic');
  final alias = TextEditingController(text: 'Điều hòa Panasonic');
  bool aliasEdited = false;
  String category = 'air_conditioner', profile = 'learned';
  int? node;
  bool busy = false, tested = false, confirmed = false;
  String? error;
  List<Map<String, dynamic>> get profiles => _rows(widget.data['profiles'])
      .where((p) => p['category'] == category)
      .toList();
  List<Map<String, dynamic>> get parents => _rows(widget.data['subboxes']);
  bool get canLearn =>
      parents.any((p) => p['node_id'] == node && p['rx'] == true);
  @override
  void initState() {
    super.initState();
    node = parents.firstOrNull?['node_id'] as int?;
    if (profiles.isNotEmpty)
      profile = profiles
          .firstWhere((p) => p['id'] == 'panasonic-cwa75c4179',
              orElse: () => profiles.first)['id']
          .toString();
  }

  @override
  void dispose() {
    name.dispose();
    alias.dispose();
    super.dispose();
  }

  Future<void> test() async {
    setState(() {
      busy = true;
      error = null;
      tested = false;
      confirmed = false;
    });
    try {
      await ref.read(gatewayClientProvider).request('/api/v1/ir/test',
          method: 'POST',
          body: {
            'node_id': node,
            'profile_id': profile,
            'idempotency_key': _requestKey()
          });
      if (mounted) setState(() => tested = true);
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> save() async {
    if (busy) return;
    if (name.text.trim().isEmpty) {
      setState(() => error = 'Nhập tên thiết bị.');
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final result = await ref
          .read(gatewayClientProvider)
          .request('/api/v1/ir/remotes', method: 'POST', body: {
        'node_id': node,
        'profile_id': profile,
        'name': name.text.trim(),
        'aliases': [
          alias.text.trim().isEmpty ? name.text.trim() : alias.text.trim()
        ],
        'category': category,
        'confirmed': confirmed
      });
      if (mounted) Navigator.pop(context, result);
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Padding(
        padding: EdgeInsets.fromLTRB(
            24, 24, 24, MediaQuery.viewInsetsOf(context).bottom + 24),
        child: SingleChildScrollView(
            child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
              const Text('Thêm remote',
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
              const SizedBox(height: 20),
              if (parents.isEmpty)
                const Text('Thêm SubBox vào phòng trước khi cấu hình remote.'),
              if (parents.isNotEmpty)
                DropdownButtonFormField<int>(
                    initialValue: node,
                    decoration:
                        const InputDecoration(labelText: 'SubBox trong phòng'),
                    items: parents
                        .map((p) => DropdownMenuItem(
                            value: p['node_id'] as int,
                            child: Text(p['room'].toString())))
                        .toList(),
                    isExpanded: true,
                    onChanged: busy
                        ? null
                        : (v) => setState(() {
                              node = v;
                              tested = false;
                              confirmed = false;
                            })),
              const SizedBox(height: 16),
              DropdownButtonFormField<String>(
                  initialValue: category,
                  decoration: const InputDecoration(labelText: 'Loại thiết bị'),
                  items: const [
                    DropdownMenuItem(
                        value: 'air_conditioner', child: Text('Điều hòa')),
                    DropdownMenuItem(value: 'tv', child: Text('TV')),
                    DropdownMenuItem(value: 'fan', child: Text('Quạt')),
                    DropdownMenuItem(
                        value: 'custom', child: Text('Thiết bị khác'))
                  ],
                  onChanged: busy
                      ? null
                      : (v) => setState(() {
                            category = v!;
                            profile = profiles.firstOrNull?['id']?.toString() ??
                                'learned';
                            tested = false;
                            confirmed = false;
                          })),
              const SizedBox(height: 16),
              DropdownButtonFormField<String>(
                  key: ValueKey('$category/$profile'),
                  initialValue: profile,
                  isExpanded: true,
                  decoration:
                      const InputDecoration(labelText: 'Hãng / bộ mã remote'),
                  items: [
                    for (final p in profiles)
                      DropdownMenuItem(
                          value: p['id'].toString(),
                          child: Text('${p['brand']} ${p['model']}',
                              overflow: TextOverflow.ellipsis)),
                    DropdownMenuItem(
                        value: 'learned',
                        enabled: canLearn,
                        child: const Text('Học từ remote gốc'))
                  ],
                  onChanged: busy
                      ? null
                      : (v) => setState(() {
                            profile = v!;
                            tested = false;
                            confirmed = false;
                          })),
              const SizedBox(height: 16),
              TextField(
                  controller: name,
                  onChanged: (v) {
                    if (!aliasEdited) alias.text = v;
                  },
                  maxLength: 100,
                  decoration: const InputDecoration(labelText: 'Tên thiết bị')),
              TextField(
                  controller: alias,
                  onChanged: (_) => aliasEdited = true,
                  maxLength: 100,
                  decoration:
                      const InputDecoration(labelText: 'Tên gọi giọng nói')),
              if (profile != 'learned') ...[
                OutlinedButton.icon(
                    onPressed: busy || node == null ? null : test,
                    icon: const Icon(Icons.wifi_tethering_rounded),
                    label: const Text('Thử bộ mã')),
                CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Thiết bị đã phản ứng đúng'),
                    value: confirmed,
                    onChanged: tested && !busy
                        ? (v) => setState(() => confirmed = v == true)
                        : null),
              ] else
                const Text(
                    'Cần mắt thu IR để học nút. Với điều hòa, học cả trạng thái như “Tắt” hoặc “Lạnh 26°C”.'),
              if (error != null)
                Padding(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: Text(error!,
                        style: TextStyle(
                            color: Theme.of(context).colorScheme.error))),
              const SizedBox(height: 16),
              SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                      onPressed: busy ||
                              node == null ||
                              (profile != 'learned' && !confirmed) ||
                              (profile == 'learned' && !canLearn)
                          ? null
                          : save,
                      child: Text(busy ? 'Đang xử lý…' : 'Lưu remote'))),
            ])),
      );
}
