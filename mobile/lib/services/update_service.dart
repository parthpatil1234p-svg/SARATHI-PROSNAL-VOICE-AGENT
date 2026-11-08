import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

class UpdateInfo {
  final String commitSha;
  final String commitMessage;
  final String date;
  final String htmlUrl;

  UpdateInfo({
    required this.commitSha,
    required this.commitMessage,
    required this.date,
    required this.htmlUrl,
  });
}

class UpdateService {
  static final UpdateService instance = UpdateService._internal();
  UpdateService._internal();

  // The compiled commit SHA of this build (first 7 chars)
  static const String currentBuildSha = 'e72d0aa';
  static const String currentVersion = '1.0.0';

  static const String githubRepo = 'parthpatil1234p-svg/SARATHI-PROSNAL-VOICE-AGENT';
  static const String githubApiUrl = 'https://api.github.com/repos/$githubRepo/commits/main';

  /// Checks GitHub main branch for newer commits than the current build.
  Future<UpdateInfo?> checkForUpdates() async {
    try {
      final res = await http.get(
        Uri.parse(githubApiUrl),
        headers: {'User-Agent': 'SARATHI-Mobile-Agent'},
      ).timeout(const Duration(seconds: 4));

      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        final fullSha = data['sha'] as String? ?? '';
        final shortSha = fullSha.length >= 7 ? fullSha.substring(0, 7) : fullSha;
        final commitObj = data['commit'] ?? {};
        final message = (commitObj['message'] as String? ?? '').split('\n').first;
        final date = commitObj['author']?['date'] as String? ?? '';
        final htmlUrl = data['html_url'] as String? ?? 'https://github.com/$githubRepo';

        if (shortSha.isNotEmpty && shortSha != currentBuildSha) {
          return UpdateInfo(
            commitSha: shortSha,
            commitMessage: message,
            date: date,
            htmlUrl: htmlUrl,
          );
        }
      }
    } catch (e) {
      debugPrint('[SARATHI Update] Check failed: $e');
    }
    return null;
  }

  /// Shows the high-tech update prompt dialog to Parth.
  void showUpdateDialog(BuildContext context, UpdateInfo update) {
    showDialog(
      context: context,
      barrierDismissible: true,
      builder: (ctx) {
        return AlertDialog(
          backgroundColor: const Color(0xFF0C131D),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: const BorderSide(color: Color(0xFF00F3FF), width: 1.2),
          ),
          title: const Row(
            children: [
              Icon(Icons.system_update, color: Color(0xFF00FF88), size: 22),
              SizedBox(width: 8),
              Text(
                'UPDATE AVAILABLE',
                style: TextStyle(
                  fontFamily: 'monospace',
                  color: Colors.white,
                  fontSize: 15,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 1.2,
                ),
              ),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'A new update was pushed to GitHub repository:\n',
                style: TextStyle(color: Colors.white.withValues(alpha: 0.8), fontSize: 13),
              ),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: const Color(0xFF070B11),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: const Color(0xFF1E2D40)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Text(
                          'COMMIT: ',
                          style: TextStyle(fontFamily: 'monospace', color: Color(0xFF00F3FF), fontSize: 11, fontWeight: FontWeight.bold),
                        ),
                        Text(
                          update.commitSha,
                          style: const TextStyle(fontFamily: 'monospace', color: Color(0xFF00FF88), fontSize: 11),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      update.commitMessage,
                      style: const TextStyle(color: Colors.white70, fontSize: 12),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                'Current version: v1.0.0 ($currentBuildSha)',
                style: TextStyle(fontFamily: 'monospace', color: Color(0xFF536D88), fontSize: 11),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('LATER', style: TextStyle(color: Colors.white54)),
            ),
            ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF00F3FF),
                foregroundColor: Colors.black,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
              ),
              icon: const Icon(Icons.download, size: 16),
              label: const Text('VIEW & UPDATE', style: TextStyle(fontWeight: FontWeight.bold)),
              onPressed: () async {
                Navigator.pop(ctx);
                final uri = Uri.parse('https://github.com/$githubRepo');
                if (await canLaunchUrl(uri)) {
                  await launchUrl(uri, mode: LaunchMode.externalApplication);
                }
              },
            ),
          ],
        );
      },
    );
  }
}
