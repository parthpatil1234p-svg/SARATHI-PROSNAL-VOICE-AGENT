import 'package:flutter/foundation.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import '../config/config.dart';

class SupabaseService {
  static final SupabaseService instance = SupabaseService._internal();
  SupabaseService._internal();

  bool _isInitialized = false;
  bool get isInitialized => _isInitialized;

  SupabaseClient get client => Supabase.instance.client;

  Future<void> init() async {
    if (_isInitialized) return;
    try {
      await Supabase.initialize(
        url: AppConfig.supabaseUrl,
        publishableKey: AppConfig.supabaseAnonKey,
      );
      _isInitialized = true;
      debugPrint('[SARATHI Cloud] Supabase initialized successfully.');
    } catch (e) {
      debugPrint('[SARATHI Cloud] Initialization error: $e');
    }
  }

  /// Streams active tasks in real-time from Supabase.
  Stream<List<Map<String, dynamic>>> streamTasks() {
    if (!_isInitialized) return const Stream.empty();
    return client
        .from('tasks')
        .stream(primaryKey: ['id'])
        .order('created_at', ascending: false);
  }

  /// Adds a task to the synchronized cloud database.
  Future<bool> addTask(String title, {String category = 'voice_task'}) async {
    if (!_isInitialized) return false;
    try {
      await client.from('tasks').insert({
        'title': title,
        'category': category,
        'status': 'pending',
        'device_origin': 'mobile',
      });
      return true;
    } catch (e) {
      debugPrint('[SARATHI Cloud] Error adding task: $e');
      return false;
    }
  }

  /// Toggles task status between pending and completed.
  Future<bool> toggleTaskStatus(String id, bool isCompleted) async {
    if (!_isInitialized) return false;
    try {
      await client.from('tasks').update({
        'status': isCompleted ? 'completed' : 'pending',
        'updated_at': DateTime.now().toIso8601String(),
      }).eq('id', id);
      return true;
    } catch (e) {
      debugPrint('[SARATHI Cloud] Error updating task: $e');
      return false;
    }
  }

  /// Saves a conversation turn to the shared memory table.
  Future<void> saveConversationTurn(String role, String content) async {
    if (!_isInitialized) return;
    try {
      await client.from('memory_turns').insert({
        'role': role,
        'content': content,
        'synced_desktop': false,
      });
    } catch (e) {
      debugPrint('[SARATHI Cloud] Error saving turn: $e');
    }
  }
}
