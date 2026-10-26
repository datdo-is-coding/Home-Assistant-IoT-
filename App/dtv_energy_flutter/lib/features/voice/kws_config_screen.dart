import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/action_box.dart';
import '../../providers/smart_home_providers.dart';
import '../../services/gateway_client.dart';

const _rooms = {
  'BEDROOM': 'Phòng ngủ',
  'LIVING_ROOM': 'Phòng khách',
  'KITCHEN': 'Bếp',
};
const _roles = {'LIGHT': 'Đèn', 'FAN': 'Quạt'};

class KwsConfigScreen extends ConsumerStatefulWidget {
  const KwsConfigScreen({super.key});

  @override
  ConsumerState<KwsConfigScreen> createState() => _KwsConfigScreenState();
}

class _KwsConfigScreenState extends ConsumerState<KwsConfigScreen> {
  Map<String, dynamic>? _config;
  List<Map<String, dynamic>> _bindings = [], _sources = [];
  bool _busy = false, _dirty = false;
  String? _error;
  int? _generation;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _accept(Map<String, dynamic> config) {
    if (config['revision'] is! int ||
        config['bindings'] is! List ||
        config['sources'] is! List) {
      throw const GatewayException('Gateway trả về cấu hình không hợp lệ.');
    }
    _config = config;
    _bindings = (config['bindings'] as List).map(asMap).toList();
    _sources = (config['sources'] as List).map(asMap).toList();
    _dirty = false;
  }

  Future<void> _load() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final gateway = ref.read(gatewayClientProvider);
    final generation = gateway.generation;
    try {
      final config = await gateway.request('/api/kws/config');
      if (!mounted) return;
      setState(() {
        _accept(config);
        _generation = generation;
      });
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _refresh() async {
    if (_dirty) {
      final discard = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Tải lại cấu hình?'),
          content: const Text(
              'Các thay đổi chưa lưu sẽ bị bỏ. Cấu hình mới nhất sẽ được tải từ Gateway.'),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Giữ bản đang sửa')),
            FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Bỏ thay đổi và tải lại')),
          ],
        ),
      );
      if (discard != true || !mounted) return;
    }
    await _load();
  }

  Future<void> _save() async {
    final gateway = ref.read(gatewayClientProvider);
    if (_generation != gateway.generation) {
      setState(() => _error =
          'Phiên đăng nhập đã thay đổi. Hãy tải lại cấu hình trước khi lưu.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result =
          await gateway.request('/api/kws/config', method: 'PUT', body: {
        'revision': _config!['revision'],
        'bindings': [
          for (final binding in _bindings)
            {
              for (final key in ['room', 'device', 'node_id', 'channel'])
                key: binding[key],
            }
        ],
        'sources': [
          for (final source in _sources)
            {
              'node_id': source['node_id'],
              'room': source['room'],
            }
        ],
      });
      if (!mounted) return;
      setState(() => _accept(result));
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e is GatewayException && e.statusCode == 409
          ? 'Cấu hình đã thay đổi ở nơi khác. Bản sửa của bạn vẫn được giữ; tải lại cấu hình mới trước khi sửa và lưu lại.'
          : 'Không thể lưu cấu hình: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final gateway = ref.watch(gatewayClientProvider);
    final boxes = ref.watch(actionBoxesStreamProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Khẩu lệnh tại SubBox'),
        actions: [
          IconButton(
            key: const Key('kws_refresh'),
            tooltip: 'Tải lại cấu hình và trạng thái',
            onPressed: _busy ? null : _refresh,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: !gateway.isAdmin
          ? const Center(
              child: Text('Cấu hình khẩu lệnh yêu cầu quyền Quản trị viên.'))
          : boxes.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) =>
                  Center(child: Text('Không thể tải thiết bị: $error')),
              data: (allBoxes) =>
                  _editor(allBoxes.where((box) => !box.isSubBox).toList()),
            ),
    );
  }

  Widget _editor(List<ActionBox> boxes) {
    final targets = <String, String>{
      for (final box in boxes)
        for (final channel in box.channels)
          if (const ['ch1', 'ch2', 'ch3'].contains(channel.channelKey))
            '${box.id}:${channel.channelKey.substring(2)}':
                '${box.name} · ${channel.channelKey.toUpperCase()} · ${channel.name}',
    };
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const Text(
            'Nói “Hi ESP”, rồi “bật/tắt đèn/quạt” và tên phòng nếu cần. Chỉ hỗ trợ phòng ngủ, phòng khách và bếp.'),
        const SizedBox(height: 8),
        const Text(
            'Gán khẩu lệnh riêng, giữ nguyên tên và loại tải. Chưa gán thì không điều khiển; không tự chọn kênh.'),
        if (_busy) const LinearProgressIndicator(),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Text(_error!,
                semanticsLabel: _error,
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        if (_config != null) ...[
          const SizedBox(height: 16),
          Text(_dirty
              ? 'Có thay đổi chưa lưu'
              : 'Bản cấu hình ${_config!['revision']} đã lưu tại Gateway'),
          ...asMap(_config!['sync']).entries.map((entry) {
            final sync = asMap(entry.value);
            final status = sync['revision'] == _config!['revision']
                ? sync['status']
                : 'pending';
            final label = switch (status) {
              'applied' => 'Đã áp dụng',
              'error' => 'Lỗi đồng bộ — kiểm tra SubBox và tải lại trạng thái',
              'offline' => 'Ngoại tuyến — chưa xác nhận áp dụng',
              _ => 'Chờ SubBox xác nhận',
            };
            return Text('${entry.key}: $label');
          }),
          if (asMap(_config!['sync']).isEmpty)
            const Text('Chưa có xác nhận áp dụng từ SubBox.'),
          const SizedBox(height: 24),
          Text('Đích điều khiển',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          for (final room in _rooms.entries)
            for (final role in _roles.entries)
              _bindingField(
                  room.key, room.value, role.key, role.value, targets),
          const SizedBox(height: 12),
          Text('Phòng của micro ActionBox',
              style: Theme.of(context).textTheme.titleMedium),
          const Text('Dùng phòng này khi câu nói không nêu phòng.'),
          const SizedBox(height: 12),
          for (final box in boxes) _sourceField(box),
          if (boxes.isEmpty) const Text('Chưa có ActionBox đã đăng ký.'),
          const SizedBox(height: 16),
          FilledButton(
            key: const Key('kws_save'),
            onPressed: _busy || !_dirty ? null : _save,
            child: const Text('Lưu và đồng bộ'),
          ),
          const SizedBox(height: 8),
          const Text(
              'Chỉ trạng thái “Đã áp dụng” xác nhận SubBox đã nhận bản cấu hình này. Dùng nút tải lại để kiểm tra.'),
        ],
      ],
    );
  }

  Widget _bindingField(String room, String roomLabel, String role,
      String roleLabel, Map<String, String> targets) {
    final matches =
        _bindings.where((b) => b['room'] == room && b['device'] == role);
    final binding = matches.firstOrNull;
    final value =
        binding == null ? '' : '${binding['node_id']}:${binding['channel']}';
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: DropdownButtonFormField<String>(
        key: Key('binding_${room}_$role'),
        initialValue: value,
        isExpanded: true,
        decoration: InputDecoration(
            labelText: '$roomLabel · $roleLabel',
            border: const OutlineInputBorder()),
        items: [
          const DropdownMenuItem(value: '', child: Text('Chưa gán')),
          for (final target in targets.entries)
            DropdownMenuItem(
                value: target.key,
                child: Text(target.value, overflow: TextOverflow.ellipsis)),
          if (value.isNotEmpty && !targets.containsKey(value))
            DropdownMenuItem(
                value: value,
                child: Text('$value · Không còn trong danh sách')),
        ],
        onChanged: _busy
            ? null
            : (target) => setState(() {
                  _bindings.removeWhere(
                      (b) => b['room'] == room && b['device'] == role);
                  if (target != null && target.isNotEmpty) {
                    final separator = target.lastIndexOf(':');
                    _bindings.add({
                      'room': room,
                      'device': role,
                      'node_id': target.substring(0, separator),
                      'channel': int.parse(target.substring(separator + 1))
                    });
                  }
                  _dirty = true;
                }),
      ),
    );
  }

  Widget _sourceField(ActionBox box) {
    final source = _sources.where((s) => s['node_id'] == box.id).firstOrNull;
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: DropdownButtonFormField<String>(
        key: Key('source_${box.id}'),
        initialValue: source?['room'] as String? ?? '',
        isExpanded: true,
        decoration: InputDecoration(
            labelText: '${box.name} · ${box.id}',
            border: const OutlineInputBorder()),
        items: [
          const DropdownMenuItem(value: '', child: Text('Chưa gán')),
          for (final room in _rooms.entries)
            DropdownMenuItem(value: room.key, child: Text(room.value)),
        ],
        onChanged: _busy
            ? null
            : (room) => setState(() {
                  _sources.removeWhere((s) => s['node_id'] == box.id);
                  if (room != null && room.isNotEmpty)
                    _sources.add({'node_id': box.id, 'room': room});
                  _dirty = true;
                }),
      ),
    );
  }
}
