import 'package:flutter/material.dart';
import '../services/energy_service.dart';
import '../services/theme_service.dart';

class ProvisioningScreen extends StatefulWidget {
  const ProvisioningScreen({super.key});

  @override
  State<ProvisioningScreen> createState() => _ProvisioningScreenState();
}

class _ProvisioningScreenState extends State<ProvisioningScreen> {
  Map<String, dynamic> _pendingNodes = {};
  bool _isLoading = false;
  final Map<String, TextEditingController> _roomControllers = {};
  final Map<String, String> _rl1Selected = {};
  final Map<String, String> _rl2Selected = {};

  @override
  void initState() {
    super.initState();
    _fetchPending();
  }

  @override
  void dispose() {
    for (final c in _roomControllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _fetchPending() async {
    setState(() => _isLoading = true);
    final data = await EnergyService().fetchNodes();
    final pending = (data['pending'] as Map<String, dynamic>?) ?? {};
    setState(() {
      _pendingNodes = pending;
      _isLoading = false;
      for (final mac in pending.keys) {
        _roomControllers.putIfAbsent(mac, () => TextEditingController(text: 'livingroom'));
        _rl1Selected.putIfAbsent(mac, () => 'light');
        _rl2Selected.putIfAbsent(mac, () => 'fan');
      }
    });
  }

  Future<void> _pairNode(String mac) async {
    final room = _roomControllers[mac]?.text.trim() ?? 'livingroom';
    final rl1 = _rl1Selected[mac] ?? 'light';
    final rl2 = _rl2Selected[mac] ?? 'fan';

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Đang gán thiết bị $mac vào $room...')),
    );

    final res = await EnergyService().provisionNode(
      mac: mac,
      room: room,
      rl1: rl1,
      rl2: rl2,
    );

    if (res['success'] == true) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('✅ Gán thành công node ${res['node_id']}!'),
          backgroundColor: Colors.green,
        ),
      );
      _fetchPending();
    } else {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('❌ Lỗi: ${res['error']}'),
          backgroundColor: Colors.redAccent,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = ThemeService().currentTheme;

    return Scaffold(
      backgroundColor: theme.bg,
      appBar: AppBar(
        backgroundColor: theme.surface,
        elevation: 0,
        title: const Text(
          'Gán Thiết Bị Mới (Provisioning)',
          style: TextStyle(fontFamily: 'Outfit', fontSize: 18, fontWeight: FontWeight.w700),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            onPressed: _fetchPending,
            tooltip: 'Quét lại thiết bị',
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _pendingNodes.isEmpty
              ? _buildEmptyState()
              : ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: _pendingNodes.length,
                  itemBuilder: (context, index) {
                    final mac = _pendingNodes.keys.elementAt(index);
                    final node = _pendingNodes[mac] as Map<String, dynamic>? ?? {};
                    return _buildPendingCard(mac, node);
                  },
                ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: const Color(0xFF00F2FE).withOpacity(0.08),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.sensors_rounded, size: 64, color: Color(0xFF00F2FE)),
            ),
            const SizedBox(height: 20),
            const Text(
              'Không Có Thiết Bị Đang Chờ',
              style: TextStyle(fontFamily: 'Outfit', fontSize: 18, fontWeight: FontWeight.w700, color: Colors.white),
            ),
            const SizedBox(height: 8),
            const Text(
              'Khi cắm nguồn cho ESP32 lần đầu tiên, thiết bị sẽ tự động phát tín hiệu beacon nhận diện để xuất hiện tại đây.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 13, color: Color(0xFF94A3B8), height: 1.4),
            ),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: _fetchPending,
              icon: const Icon(Icons.search_rounded, size: 18),
              label: const Text('Quét Lại Mạng'),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF00F2FE).withOpacity(0.2),
                foregroundColor: const Color(0xFF00F2FE),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPendingCard(String mac, Map<String, dynamic> node) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF0E131F),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF00F2FE).withOpacity(0.3)),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF00F2FE).withOpacity(0.06),
            blurRadius: 16,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: const Color(0xFF00F2FE).withOpacity(0.15),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.developer_board_rounded, color: Color(0xFF00F2FE), size: 22),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      mac,
                      style: const TextStyle(
                        fontFamily: 'monospace',
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: Colors.white,
                      ),
                    ),
                    Text(
                      'Tín hiệu mới phát hiện · Chờ gán phòng',
                      style: TextStyle(fontSize: 11, color: Colors.orangeAccent.shade200),
                    ),
                  ],
                ),
              ),
              const Chip(
                label: Text('MỚI', style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold)),
                backgroundColor: Color(0xFF00F2FE),
                visualDensity: VisualDensity.compact,
              ),
            ],
          ),
          const SizedBox(height: 16),
          const Divider(color: Colors.white10),
          const SizedBox(height: 12),

          // Room input
          const Text('TÊN PHÒNG', style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, color: Color(0xFF64748B))),
          const SizedBox(height: 6),
          TextField(
            controller: _roomControllers[mac],
            style: const TextStyle(fontSize: 13, color: Colors.white),
            decoration: InputDecoration(
              hintText: 'livingroom / bedroom / kitchen',
              filled: true,
              fillColor: Colors.black26,
              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
            ),
          ),
          const SizedBox(height: 12),

          // Relay 1 & Relay 2 types
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('KÊNH 1 (RL1)', style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, color: Color(0xFF64748B))),
                    const SizedBox(height: 6),
                    _buildTypeDropdown(mac, 1),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('KÊNH 2 (RL2)', style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, color: Color(0xFF64748B))),
                    const SizedBox(height: 6),
                    _buildTypeDropdown(mac, 2),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),

          // Pair Button
          SizedBox(
            width: double.infinity,
            height: 44,
            child: ElevatedButton.icon(
              onPressed: () => _pairNode(mac),
              icon: const Icon(Icons.add_link_rounded, size: 20),
              label: const Text('Gán Vào Ngôi Nhà', style: TextStyle(fontWeight: FontWeight.w700)),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF00F2FE),
                foregroundColor: Colors.black,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTypeDropdown(String mac, int channel) {
    final currentVal = channel == 1 ? _rl1Selected[mac] : _rl2Selected[mac];
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: Colors.black26,
        borderRadius: BorderRadius.circular(10),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: currentVal ?? 'light',
          isExpanded: true,
          dropdownColor: const Color(0xFF0E131F),
          items: const [
            DropdownMenuItem(value: 'light', child: Text('Đèn (Light)', style: TextStyle(fontSize: 13))),
            DropdownMenuItem(value: 'fan', child: Text('Quạt (Fan)', style: TextStyle(fontSize: 13))),
            DropdownMenuItem(value: 'switch', child: Text('Công tắc (Switch)', style: TextStyle(fontSize: 13))),
          ],
          onChanged: (val) {
            if (val != null) {
              setState(() {
                if (channel == 1) {
                  _rl1Selected[mac] = val;
                } else {
                  _rl2Selected[mac] = val;
                }
              });
            }
          },
        ),
      ),
    );
  }
}
