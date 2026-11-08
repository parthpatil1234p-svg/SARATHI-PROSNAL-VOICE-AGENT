import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:url_launcher/url_launcher.dart';
import 'ai_service.dart';
import 'supabase_service.dart';

enum AssistantVoiceState { idle, listening, processing, speaking }

class VoiceService extends ChangeNotifier {
  static final VoiceService instance = VoiceService._internal();
  VoiceService._internal();

  final stt.SpeechToText _speech = stt.SpeechToText();
  final FlutterTts _tts = FlutterTts();

  AssistantVoiceState _state = AssistantVoiceState.idle;
  AssistantVoiceState get state => _state;

  String _lastUserSpeech = '';
  String get lastUserSpeech => _lastUserSpeech;

  String _lastAssistantSpeech = 'SARATHI Mobile Mk.VII is online. Say "Hey Sarathi" or tap the core.';
  String get lastAssistantSpeech => _lastAssistantSpeech;

  bool _isSpeechAvailable = false;
  bool get isSpeechAvailable => _isSpeechAvailable;

  bool _alwaysOnWakeWord = true;
  bool get alwaysOnWakeWord => _alwaysOnWakeWord;

  Timer? _restartListeningTimer;

  static const List<String> wakePhrases = [
    'hey sarathi',
    'hey sarthi',
    'sarathi',
    'sarthi',
    'sarathy',
    'hey jarvis',
    'सारथी',
  ];

  Future<void> init() async {
    _isSpeechAvailable = await _speech.initialize(
      onError: (val) {
        debugPrint('[STT Error] $val');
        _scheduleAutoRestart();
      },
      onStatus: _handleStatus,
    );

    await _tts.setLanguage('en-GB');
    await _tts.setPitch(1.0);
    await _tts.setSpeechRate(0.5);

    _tts.setCompletionHandler(() {
      _setState(AssistantVoiceState.idle);
      _scheduleAutoRestart();
    });

    if (_isSpeechAvailable && _alwaysOnWakeWord) {
      startListening();
    }
  }

  void toggleAlwaysOnWakeWord() {
    _alwaysOnWakeWord = !_alwaysOnWakeWord;
    notifyListeners();
    if (_alwaysOnWakeWord) {
      startListening();
    } else {
      stopListening();
    }
  }

  void _handleStatus(String status) {
    if (status == 'done' || status == 'notListening') {
      if (_state == AssistantVoiceState.listening) {
        _setState(AssistantVoiceState.idle);
      }
      _scheduleAutoRestart();
    }
  }

  void _scheduleAutoRestart() {
    if (!_alwaysOnWakeWord || _state == AssistantVoiceState.speaking || _state == AssistantVoiceState.processing) {
      return;
    }
    _restartListeningTimer?.cancel();
    _restartListeningTimer = Timer(const Duration(milliseconds: 400), () {
      if (_alwaysOnWakeWord && _state == AssistantVoiceState.idle && !_speech.isListening) {
        startListening();
      }
    });
  }

  void _setState(AssistantVoiceState newState) {
    _state = newState;
    notifyListeners();
  }

  /// Starts listening to user speech via microphone.
  Future<void> startListening() async {
    if (!_isSpeechAvailable) return;
    if (_state == AssistantVoiceState.speaking) {
      await _tts.stop();
    }

    _setState(AssistantVoiceState.listening);
    await _speech.listen(
      onResult: (result) {
        final recognized = result.recognizedWords.trim();
        _lastUserSpeech = recognized;
        notifyListeners();

        // Check for instant Wake-Word match
        final lower = recognized.toLowerCase();
        for (final wp in wakePhrases) {
          if (lower.contains(wp)) {
            // Found wake word! Extract command after wake phrase
            final idx = lower.indexOf(wp);
            final postCmd = recognized.substring(idx + wp.length).trim().replaceAll(RegExp(r'^[,\.\?\!\:\s]+'), '');

            if (result.finalResult || postCmd.length >= 3) {
              _speech.stop();
              if (postCmd.isEmpty) {
                // User just said "Hey Sarathi"
                _speakDirect("At your service, Parth. How can I assist you, sir?");
              } else {
                // User said "Hey Sarathi <command>"
                processUserInput(postCmd);
              }
              return;
            }
          }
        }

        // If not using strict wake phrase or finalized manually
        if (result.finalResult && recognized.isNotEmpty) {
          processUserInput(recognized);
        }
      },
      listenOptions: stt.SpeechListenOptions(
        listenMode: stt.ListenMode.dictation,
        pauseFor: const Duration(seconds: 3),
      ),
    );
  }

  /// Stops microphone listening.
  Future<void> stopListening() async {
    _restartListeningTimer?.cancel();
    await _speech.stop();
    _setState(AssistantVoiceState.idle);
  }

  Future<void> _speakDirect(String text) async {
    _lastAssistantSpeech = text;
    SupabaseService.instance.saveConversationTurn('assistant', text);
    _setState(AssistantVoiceState.speaking);
    await _tts.speak(text);
  }

  /// Processes text turn through AI reasoning, executes actions, and speaks response.
  Future<void> processUserInput(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return;

    _lastUserSpeech = trimmed;
    _setState(AssistantVoiceState.processing);

    // Save user turn to Cloud Memory
    SupabaseService.instance.saveConversationTurn('user', trimmed);

    // Query Groq Qwen AI
    final rawResponse = await AIService.instance.query(trimmed);

    // Parse Actions
    String spokenText = rawResponse;

    // Check for CALL action: [ACTION:CALL:<target>]
    final callMatch = RegExp(r'\[ACTION:CALL:(.*?)\]').firstMatch(rawResponse);
    if (callMatch != null) {
      final target = callMatch.group(1)?.trim() ?? '';
      spokenText = rawResponse.replaceAll(callMatch.group(0)!, '').trim();
      _initiatePhoneCall(target);
    }

    // Check for TASK action: [ACTION:TASK:<title>]
    final taskMatch = RegExp(r'\[ACTION:TASK:(.*?)\]').firstMatch(rawResponse);
    if (taskMatch != null) {
      final taskTitle = taskMatch.group(1)?.trim() ?? '';
      spokenText = rawResponse.replaceAll(taskMatch.group(0)!, '').trim();
      SupabaseService.instance.addTask(taskTitle, category: 'voice_command');
    }

    await _speakDirect(spokenText);
  }

  Future<void> _initiatePhoneCall(String target) async {
    try {
      final cleanedNumber = target.replaceAll(RegExp(r'[^\d+]'), '');
      final Uri uri = cleanedNumber.isNotEmpty
          ? Uri.parse('tel:$cleanedNumber')
          : Uri.parse('tel:');
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri);
      }
    } catch (e) {
      debugPrint('[SARATHI Action] Call launch error: $e');
    }
  }
}
