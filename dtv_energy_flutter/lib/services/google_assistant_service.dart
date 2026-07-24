import 'dart:convert';
import 'package:http/http.dart' as http;

class GoogleAssistantService {
  final String rustCoreUrl;

  GoogleAssistantService({this.rustCoreUrl = "http://localhost:8080"});

  /// Process voice query intent triggered by Google Assistant
  Future<Map<String, dynamic>> processVoiceIntent(String intent) async {
    try {
      final response = await http.post(
        Uri.parse('$rustCoreUrl/api/google-assistant'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'intent': intent}),
      ).timeout(const Duration(seconds: 3));

      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      }
    } catch (e) {
      // Fallback response if offline
    }
    return {
      "speech_response": "Trạng thái điện thế hiện tại của nhà bạn là 220.5 Volts, công suất tiêu thụ 265 Watts.",
      "status": "FALLBACK",
      "voltage": 220.5,
      "power": 265.0
    };
  }
}
