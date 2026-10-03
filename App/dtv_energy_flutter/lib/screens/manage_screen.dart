import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import '../services/gateway_client.dart';
import 'home_screen.dart';

class ManageScreen extends StatefulWidget {
  const ManageScreen({super.key, required this.client});
  final GatewayClient client;
  @override
  State<ManageScreen> createState() => _ManageScreenState();
}

class _ManageScreenState extends State<ManageScreen> {
  @override
  void initState() {
    super.initState();
    widget.client.refresh();
  }

  Future<void> _pair(String id, Map<String, dynamic> node) async {
    final result = await showModalBottomSheet<bool>(
        context: context,
        isScrollControlled: true,
        useSafeArea: true,
        builder: (_) => PairSheet(client: widget.client, id: id, node: node));
    if (result == true && mounted)
      showMessage(context, 'Đã thêm thiết bị vào nhà.');
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
      listenable: widget.client,
      builder: (context, _) => Scaffold(
            appBar: AppBar(title: const Text('Thêm thiết bị'), actions: [
              IconButton(
                  tooltip: 'Tìm thiết bị',
                  onPressed:
                      widget.client.loading ? null : widget.client.refresh,
                  icon: const Icon(Icons.refresh))
            ]),
            body: SafeArea(
                child: RefreshIndicator(
                    onRefresh: widget.client.refresh,
                    child:
                        ListView(padding: const EdgeInsets.all(20), children: [
                      if (widget.client.loading)
                        const LinearProgressIndicator(),
                      if (widget.client.error != null)
                        Text(widget.client.error!,
                            style: TextStyle(
                                color: Theme.of(context).colorScheme.error)),
                      const SizedBox(height: 16),
                      const Text('Thiết bị được tìm thấy',
                          style: TextStyle(
                              fontSize: 22, fontWeight: FontWeight.w700)),
                      const SizedBox(height: 20),
                      if (widget.client.pending.isEmpty)
                        const EmptyState(
                            icon: Icons.sensors_rounded,
                            title: 'Chưa có thiết bị chờ',
                            subtitle:
                                'Thiết bị chưa ghép nối sẽ xuất hiện khi kết nối Gateway.'),
                      for (final entry in widget.client.pending.entries)
                        Padding(
                            padding: const EdgeInsets.only(bottom: 12),
                            child: Card(
                                child: ListTile(
                              contentPadding: const EdgeInsets.symmetric(
                                  horizontal: 16, vertical: 12),
                              leading: const Icon(Icons.add_link_rounded),
                              title: Text(
                                  '${asMap(entry.value)['hardware'] ?? 'Thiết bị mới'}'),
                              subtitle: Text(
                                  '${asMap(entry.value)['mac'] ?? entry.key}'),
                              trailing: const Icon(Icons.chevron_right),
                              onTap: widget.client.connected &&
                                      widget.client.isAdmin
                                  ? () => _pair(entry.key, asMap(entry.value))
                                  : null,
                            ))),
                    ]))),
          ));
}

class PairSheet extends StatefulWidget {
  const PairSheet(
      {super.key, required this.client, required this.id, required this.node});
  final GatewayClient client;
  final String id;
  final Map<String, dynamic> node;
  @override
  State<PairSheet> createState() => _PairSheetState();
}

class _PairSheetState extends State<PairSheet> {
  final _name = TextEditingController();
  final _room = TextEditingController();
  final _form = GlobalKey<FormState>();
  String _first = 'light', _second = 'fan';
  bool _busy = false;
  String? _error;
  @override
  void dispose() {
    _name.dispose();
    _room.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await widget.client.request('/api/provision',
          body: {
            'device_id': widget.id,
            'mac': widget.node['mac'] ?? '',
            'name': _name.text.trim(),
            'room': _room.text.trim(),
            'rl1': _first,
            'rl2': _second,
          },
          timeout: const Duration(seconds: 20));
      if (result['success'] == false || result['error'] != null)
        throw GatewayException(
            '${result['error'] ?? 'Không thể thêm thiết bị'}');
      await widget.client.refresh();
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted)
        setState(() {
          _error = e.toString();
          _busy = false;
        });
    }
  }

  @override
  Widget build(BuildContext context) => Padding(
        padding: EdgeInsets.fromLTRB(
            24, 24, 24, MediaQuery.viewInsetsOf(context).bottom + 24),
        child: SingleChildScrollView(
            child: Form(
                key: _form,
                child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Kết nối thiết bị',
                          style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: 20),
                      TextFormField(
                          controller: _name,
                          maxLength: 64,
                          enabled: !_busy,
                          decoration:
                              const InputDecoration(labelText: 'Tên thiết bị'),
                          validator: (s) => s == null || s.trim().isEmpty
                              ? 'Nhập tên thiết bị'
                              : null),
                      const SizedBox(height: 12),
                      TextFormField(
                          controller: _room,
                          maxLength: 64,
                          enabled: !_busy,
                          decoration: const InputDecoration(
                              labelText: 'Phòng', hintText: 'phong_khach'),
                          validator: (s) => s == null || s.trim().isEmpty
                              ? 'Nhập phòng'
                              : null),
                      const SizedBox(height: 12),
                      DropdownButtonFormField<String>(
                          initialValue: _first,
                          decoration:
                              const InputDecoration(labelText: 'Kênh 1'),
                          items: _types,
                          onChanged: _busy
                              ? null
                              : (v) => setState(() => _first = v!)),
                      const SizedBox(height: 16),
                      DropdownButtonFormField<String>(
                          initialValue: _second,
                          decoration:
                              const InputDecoration(labelText: 'Kênh 2'),
                          items: _types,
                          onChanged: _busy
                              ? null
                              : (v) => setState(() => _second = v!)),
                      if (_error != null)
                        Padding(
                            padding: const EdgeInsets.only(top: 16),
                            child: Text(_error!,
                                style: TextStyle(
                                    color:
                                        Theme.of(context).colorScheme.error))),
                      const SizedBox(height: 24),
                      SizedBox(
                          width: double.infinity,
                          child: FilledButton(
                              onPressed: _busy ? null : _save,
                              child: Text(
                                  _busy ? 'Đang kết nối...' : 'Thêm vào nhà'))),
                    ]))),
      );

  List<DropdownMenuItem<String>> get _types => const [
        DropdownMenuItem(value: 'light', child: Text('Đèn')),
        DropdownMenuItem(value: 'fan', child: Text('Quạt')),
        DropdownMenuItem(value: 'pump', child: Text('Máy bơm')),
        DropdownMenuItem(value: 'switch', child: Text('Công tắc')),
      ];
}

class FirmwareScreen extends StatefulWidget {
  const FirmwareScreen({super.key, required this.client});
  final GatewayClient client;
  @override
  State<FirmwareScreen> createState() => _FirmwareScreenState();
}

class _FirmwareScreenState extends State<FirmwareScreen> {
  List<Map<String, dynamic>> _files = [];
  bool _loading = true, _busy = false;
  String? _error;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await widget.client.request('/api/ota/list');
      if (mounted)
        setState(() =>
            _files = (data['firmwares'] as List? ?? []).map(asMap).toList());
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _upload() async {
    setState(() => _busy = true);
    try {
      final selected = await FilePicker.platform.pickFiles(
          type: FileType.custom, allowedExtensions: ['bin'], withData: true);
      if (selected == null) return;
      final file = selected.files.single;
      if (file.bytes == null)
        throw const GatewayException('Không đọc được file firmware.');
      await widget.client.uploadFirmware(file.name, file.bytes!);
      await _load();
      if (mounted) showMessage(context, 'Đã tải firmware lên Gateway.');
    } catch (e) {
      if (mounted) showMessage(context, e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _flash(Map<String, dynamic> file) async {
    final devices = widget.client.nodes.entries
        .where((e) => asMap(e.value)['status'] == 'online')
        .toList();
    if (devices.isEmpty) {
      showMessage(context, 'Không có thiết bị trực tuyến.');
      return;
    }
    String nodeId = devices.first.key;
    final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => StatefulBuilder(
            builder: (context, update) => AlertDialog(
                  title: const Text('Cập nhật firmware?'),
                  content: SingleChildScrollView(
                      child: Column(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                        Text('${file['filename']}'),
                        const SizedBox(height: 12),
                        const Text(
                            'Thiết bị sẽ khởi động lại. Chọn firmware đúng phần cứng và giữ nguồn điện ổn định.'),
                        const SizedBox(height: 20),
                        DropdownButtonFormField<String>(
                            initialValue: nodeId,
                            isExpanded: true,
                            decoration: const InputDecoration(
                                labelText: 'Thiết bị đích'),
                            items: devices
                                .map((e) => DropdownMenuItem(
                                    value: e.key,
                                    child: Text(nodeName(e.key, asMap(e.value)),
                                        overflow: TextOverflow.ellipsis)))
                                .toList(),
                            onChanged: (value) =>
                                update(() => nodeId = value!)),
                      ])),
                  actions: [
                    TextButton(
                        onPressed: () => Navigator.pop(context, false),
                        child: const Text('Hủy')),
                    FilledButton(
                        onPressed: () => Navigator.pop(context, true),
                        child: const Text('Cập nhật'))
                  ],
                )));
    if (confirmed != true || !mounted) return;
    setState(() => _busy = true);
    try {
      final result = await widget.client.request('/api/ota/flash',
          body: {'filename': file['filename'], 'node_id': nodeId},
          timeout: const Duration(seconds: 30));
      if (result['success'] != true)
        throw GatewayException(
            '${result['error'] ?? 'Không gửi được yêu cầu cập nhật'}');
      if (mounted)
        showMessage(
            context, 'Đã gửi yêu cầu cập nhật. Chờ thiết bị kết nối lại.');
    } catch (e) {
      if (mounted) showMessage(context, e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Firmware thiết bị'), actions: [
          IconButton(
              tooltip: 'Làm mới',
              onPressed: _loading || _busy ? null : _load,
              icon: const Icon(Icons.refresh))
        ]),
        body: SafeArea(
            child: ListView(padding: const EdgeInsets.all(20), children: [
          FilledButton.icon(
              onPressed: _busy ? null : _upload,
              icon: const Icon(Icons.upload_file_outlined),
              label: Text(_busy ? 'Đang xử lý...' : 'Tải file .bin')),
          const SizedBox(height: 24),
          if (_loading || _busy) const LinearProgressIndicator(),
          if (_error != null)
            Padding(
                padding: const EdgeInsets.symmetric(vertical: 20),
                child: Text(_error!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error))),
          if (!_loading && _files.isEmpty && _error == null)
            const EmptyState(
                icon: Icons.system_update_outlined,
                title: 'Chưa có firmware',
                subtitle: 'Không có bản firmware nào trên Gateway.'),
          for (final file in _files)
            Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Card(
                    child: ListTile(
                  leading: const Icon(Icons.description_outlined),
                  title: Text('${file['filename']}'),
                  subtitle: Text(metric(file['size_kb'], 'KB')),
                  trailing: IconButton(
                      tooltip: 'Cập nhật thiết bị',
                      onPressed: _busy ? null : () => _flash(file),
                      icon: const Icon(Icons.system_update_alt_rounded)),
                ))),
        ])),
      );
}
