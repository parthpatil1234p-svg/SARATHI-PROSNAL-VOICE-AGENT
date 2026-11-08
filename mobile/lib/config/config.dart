import 'env_local.dart';

/// Global configuration for SARATHI Mobile.
class AppConfig {
  static const String assistantName = 'SARATHI';
  static const String userName = 'Parth';

  // Supabase Cloud Sync Configuration
  static const String supabaseUrl = 'https://lgcvrwfdvrsliqdqwcoj.supabase.co';
  static const String supabaseAnonKey = 'sb_publishable_cOZlCBv1Rh4jmsPck4PEhg_K_zrH4td';

  // Groq Cloud AI Engine (Blazing fast sub-250ms Qwen-27B conversational model)
  static const String groqApiKey = localGroqApiKey;
  static const String groqModel = 'qwen/qwen3.8-27b';
}
