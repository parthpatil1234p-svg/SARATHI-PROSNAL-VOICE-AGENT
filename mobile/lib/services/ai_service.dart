import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../config/config.dart';

class AIService {
  static final AIService instance = AIService._internal();
  AIService._internal();

  final String _systemPrompt = '''
You are SARATHI, an elite, charismatic, and fiercely loyal AI personal companion built specifically for Parth (like Tony Stark's J.A.R.V.I.S.).
Rules:
1. Address Parth with natural charisma, warmth, and subtle wit. Never sound like a sterile teacher, boring bot, or generic assistant.
2. If Parth asks you to place a phone call (e.g., "Call Mom", "Call 9876543210"), prefix your output with: [ACTION:CALL:<target>] followed by your spoken confirmation (e.g. "[ACTION:CALL:Mom] Connecting you to Mom right now, Parth.").
3. If Parth asks you to add a task or reminder (e.g., "Add task buy milk", "Remind me to check servers"), prefix your output with: [ACTION:TASK:<title>] followed by your spoken confirmation (e.g. "[ACTION:TASK:Check servers] Noted, Parth. Synced to your cloud tasks.").
4. Keep spoken responses concise, conversational, and direct (1 to 2 sentences max unless Parth asks for detail).
5. Seamlessly understand and converse in Hindi, Hinglish, and English.
''';

  final List<Map<String, String>> _messages = [];

  void reset() {
    _messages.clear();
  }

  Future<String> query(String userText) async {
    _messages.add({'role': 'user', 'content': userText});
    if (_messages.length > 10) {
      _messages.removeRange(0, _messages.length - 10);
    }

    try {
      final response = await http.post(
        Uri.parse('https://api.groq.com/openai/v1/chat/completions'),
        headers: {
          'Authorization': 'Bearer ${AppConfig.groqApiKey}',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'model': AppConfig.groqModel,
          'messages': [
            {'role': 'system', 'content': _systemPrompt},
            ..._messages,
          ],
          'temperature': 0.7,
          'max_tokens': 200,
        }),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final message = data['choices'][0]['message'];
        String reply = (message['content'] as String?)?.trim() ?? '';
        if (reply.isEmpty && message['reasoning'] != null) {
          reply = (message['reasoning'] as String).trim();
        }
        if (reply.isNotEmpty) {
          _messages.add({'role': 'assistant', 'content': reply});
          return reply;
        }
        return "At your command, Parth. Systems operational.";
      } else {
        debugPrint('[SARATHI AI] Groq API returned ${response.statusCode}: ${response.body}');
        return "Standing by, Parth. Let's try that query once more.";
      }
    } catch (e) {
      debugPrint('[SARATHI AI] Network error: $e');
      return "Network is a bit patchy, Parth. Standing by for local commands.";
    }
  }
}
