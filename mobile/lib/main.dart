import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'services/supabase_service.dart';
import 'services/voice_service.dart';
import 'screens/hud_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Enforce dark system UI
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.light,
    systemNavigationBarColor: Color(0xFF070B11),
    systemNavigationBarIconBrightness: Brightness.light,
  ));

  // Initialize Supabase Cloud Sync
  await SupabaseService.instance.init();

  // Initialize Voice and TTS engine
  await VoiceService.instance.init();

  runApp(const SarathiMobileApp());
}

class SarathiMobileApp extends StatelessWidget {
  const SarathiMobileApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SARATHI Mobile',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF070B11),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF00F3FF),
          secondary: Color(0xFF00FF88),
          surface: Color(0xFF0C131D),
        ),
      ),
      home: const TacticalHudScreen(),
    );
  }
}
