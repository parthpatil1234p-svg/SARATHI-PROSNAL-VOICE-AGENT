import 'package:flutter/material.dart';
import '../services/voice_service.dart';
import '../services/supabase_service.dart';
import '../services/update_service.dart';

class TacticalHudScreen extends StatefulWidget {
  const TacticalHudScreen({super.key});

  @override
  State<TacticalHudScreen> createState() => _TacticalHudScreenState();
}

class _TacticalHudScreenState extends State<TacticalHudScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  final TextEditingController _textInputCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);

    VoiceService.instance.addListener(() {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _pulseController.dispose();
    _textInputCtrl.dispose();
    super.dispose();
  }

  Color _getStateColor(AssistantVoiceState state) {
    switch (state) {
      case AssistantVoiceState.listening:
        return const Color(0xFF00FF88); // Neon Green
      case AssistantVoiceState.processing:
        return const Color(0xFFFFB800); // Amber
      case AssistantVoiceState.speaking:
        return const Color(0xFF00F3FF); // Cyan
      case AssistantVoiceState.idle:
        return const Color(0xFF00D2FF).withValues(alpha: 0.7);
    }
  }

  String _getStateLabel(AssistantVoiceState state) {
    switch (state) {
      case AssistantVoiceState.listening:
        return 'LISTENING...';
      case AssistantVoiceState.processing:
        return 'SYNAPSE PROCESSING...';
      case AssistantVoiceState.speaking:
        return 'SYNTHESIZING...';
      case AssistantVoiceState.idle:
        return 'STANDBY';
    }
  }

  @override
  Widget build(BuildContext context) {
    final voice = VoiceService.instance;
    final stateColor = _getStateColor(voice.state);

    return Scaffold(
      backgroundColor: const Color(0xFF070B11),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0B121C),
        elevation: 0,
        title: Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                color: Color(0xFF00FF88),
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 8),
            const Text(
              'SARATHI // MK.VII',
              style: TextStyle(
                fontFamily: 'monospace',
                fontWeight: FontWeight.bold,
                fontSize: 15,
                letterSpacing: 1.5,
                color: Colors.white,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Check for Updates',
            icon: const Icon(Icons.system_update_alt, color: Color(0xFF00F3FF), size: 20),
            onPressed: () async {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Checking GitHub for updates...'), duration: Duration(seconds: 1)),
              );
              final update = await UpdateService.instance.checkForUpdates();
              if (!context.mounted) return;
              if (update != null) {
                UpdateService.instance.showUpdateDialog(context, update);
              } else {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('SARATHI is up to date with GitHub! (v1.0.0)'), backgroundColor: Color(0xFF002830)),
                );
              }
            },
          ),
          Container(
            margin: const EdgeInsets.symmetric(vertical: 12, horizontal: 12),
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: const Color(0xFF002830),
              borderRadius: BorderRadius.circular(4),
              border: Border.all(color: const Color(0xFF00F3FF), width: 0.8),
            ),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.cloud_done, color: Color(0xFF00F3FF), size: 14),
                SizedBox(width: 4),
                Text(
                  'SUPABASE LIVE',
                  style: TextStyle(
                    fontFamily: 'monospace',
                    fontSize: 10,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF00F3FF),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            // Center Arc Reactor Visualizer
            Expanded(
              flex: 4,
              child: Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    GestureDetector(
                      onTap: () {
                        if (voice.state == AssistantVoiceState.listening) {
                          voice.stopListening();
                        } else {
                          voice.startListening();
                        }
                      },
                      child: AnimatedBuilder(
                        animation: _pulseController,
                        builder: (context, child) {
                          final scale = voice.state == AssistantVoiceState.listening
                              ? 1.0 + (_pulseController.value * 0.15)
                              : 1.0;
                          return Transform.scale(
                            scale: scale,
                            child: Container(
                              width: 140,
                              height: 140,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: const Color(0xFF0B1420),
                                border: Border.all(
                                  color: stateColor,
                                  width: 2.5,
                                ),
                                boxShadow: [
                                  BoxShadow(
                                    color: stateColor.withValues(alpha: 0.35),
                                    blurRadius: 25,
                                    spreadRadius: 3,
                                  ),
                                ],
                              ),
                              child: Icon(
                                voice.state == AssistantVoiceState.listening
                                    ? Icons.mic
                                    : (voice.state == AssistantVoiceState.speaking
                                        ? Icons.graphic_eq
                                        : Icons.fingerprint),
                                size: 54,
                                color: stateColor,
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      _getStateLabel(voice.state),
                      style: TextStyle(
                        fontFamily: 'monospace',
                        color: stateColor,
                        fontSize: 12,
                        letterSpacing: 2.0,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Transcript Feed
            Expanded(
              flex: 3,
              child: Container(
                margin: const EdgeInsets.symmetric(horizontal: 16),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFF0C131D),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: const Color(0xFF1E2D40)),
                ),
                child: ListView(
                  children: [
                    if (voice.lastUserSpeech.isNotEmpty) ...[
                      _buildChatTurn('PARTH', voice.lastUserSpeech, const Color(0xFF00FF88)),
                      const SizedBox(height: 10),
                    ],
                    _buildChatTurn('SARATHI', voice.lastAssistantSpeech, const Color(0xFF00F3FF)),
                  ],
                ),
              ),
            ),

            // Cloud Synchronized Tasks View
            Expanded(
              flex: 3,
              child: Container(
                margin: const EdgeInsets.all(16),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: const Color(0xFF0A0F17),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: const Color(0xFF152232)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          '// SYNCHRONIZED CLOUD TASKS',
                          style: TextStyle(
                            fontFamily: 'monospace',
                            fontSize: 11,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 1.2,
                            color: Color(0xFF7B91A8),
                          ),
                        ),
                        Icon(Icons.sync, color: Color(0xFF7B91A8), size: 14),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Expanded(
                      child: StreamBuilder<List<Map<String, dynamic>>>(
                        stream: SupabaseService.instance.streamTasks(),
                        builder: (context, snapshot) {
                          if (snapshot.connectionState == ConnectionState.waiting) {
                            return const Center(
                              child: SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF00F3FF)),
                              ),
                            );
                          }
                          final tasks = snapshot.data ?? [];
                          if (tasks.isEmpty) {
                            return const Center(
                              child: Text(
                                'No pending tasks. Say "Add task..." to create one.',
                                style: TextStyle(color: Color(0xFF4A607A), fontSize: 11),
                              ),
                            );
                          }
                          return ListView.builder(
                            itemCount: tasks.length,
                            itemBuilder: (context, idx) {
                              final task = tasks[idx];
                              final isDone = task['status'] == 'completed';
                              return Container(
                                margin: const EdgeInsets.symmetric(vertical: 3),
                                decoration: BoxDecoration(
                                  color: const Color(0xFF0D1622),
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: ListTile(
                                  dense: true,
                                  visualDensity: VisualDensity.compact,
                                  leading: Checkbox(
                                    value: isDone,
                                    activeColor: const Color(0xFF00FF88),
                                    onChanged: (val) {
                                      SupabaseService.instance.toggleTaskStatus(
                                        task['id'],
                                        val ?? false,
                                      );
                                    },
                                  ),
                                  title: Text(
                                    task['title'] ?? '',
                                    style: TextStyle(
                                      color: isDone ? Colors.white38 : Colors.white,
                                      fontSize: 13,
                                      decoration: isDone ? TextDecoration.lineThrough : null,
                                    ),
                                  ),
                                  subtitle: Text(
                                    'Origin: ${task['device_origin'] ?? 'mobile'}',
                                    style: const TextStyle(color: Color(0xFF536D88), fontSize: 10),
                                  ),
                                ),
                              );
                            },
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Bottom Input Bar
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              decoration: const BoxDecoration(
                color: Color(0xFF0A1018),
                border: Border(top: BorderSide(color: Color(0xFF1E2D40))),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _textInputCtrl,
                      style: const TextStyle(color: Colors.white, fontSize: 13),
                      decoration: const InputDecoration(
                        hintText: "Speak or type command (e.g. 'Call mom')...",
                        hintStyle: TextStyle(color: Color(0xFF4B6079), fontSize: 12),
                        border: InputBorder.none,
                      ),
                      onSubmitted: (val) {
                        if (val.trim().isNotEmpty) {
                          voice.processUserInput(val);
                          _textInputCtrl.clear();
                        }
                      },
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.send, color: Color(0xFF00F3FF), size: 18),
                    onPressed: () {
                      final txt = _textInputCtrl.text.trim();
                      if (txt.isNotEmpty) {
                        voice.processUserInput(txt);
                        _textInputCtrl.clear();
                      }
                    },
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildChatTurn(String sender, String text, Color accent) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '// $sender',
          style: TextStyle(
            fontFamily: 'monospace',
            color: accent,
            fontSize: 10,
            fontWeight: FontWeight.bold,
            letterSpacing: 1.1,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          text,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 13,
            height: 1.4,
          ),
        ),
      ],
    );
  }
}
