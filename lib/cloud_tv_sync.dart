import 'dart:async';
import 'dart:convert';
import 'dart:io';

const String cloudTvBaseUrl = 'https://billaresdonmiguel.pages.dev';

String _signature(List<Map<String, dynamic>> tables) => jsonEncode(tables);

String _elapsedFor(Map<String, dynamic> table) {
  final String? startRaw = table['start'] as String?;
  if (startRaw == null || startRaw.isEmpty) return '00:00:00';
  final DateTime? start = DateTime.tryParse(startRaw);
  if (start == null) return '00:00:00';
  final String? endRaw = table['end'] as String?;
  final DateTime finish = endRaw == null || endRaw.isEmpty
      ? DateTime.now()
      : (DateTime.tryParse(endRaw) ?? DateTime.now());
  final int seconds = finish.difference(start).inSeconds.clamp(0, 2147483647);
  final int hours = seconds ~/ 3600;
  final int minutes = (seconds % 3600) ~/ 60;
  final int remaining = seconds % 60;
  return '${hours.toString().padLeft(2, '0')}:${minutes.toString().padLeft(2, '0')}:${remaining.toString().padLeft(2, '0')}';
}

Timer? _cloudTvRetryTimer;
String? _lastPublishedSignature;
bool _cloudTvPublishing = false;

Future<void> publishCloudTvState(List<Map<String, dynamic>> tables) async {
  if (_cloudTvPublishing) return;
  final List<Map<String, dynamic>> payloadTables = tables.map((
    Map<String, dynamic> table,
  ) {
    final Map<String, dynamic> copy = Map<String, dynamic>.from(table);
    copy['elapsed'] = _elapsedFor(copy);
    return copy;
  }).toList();
  final String signature = _signature(payloadTables);
  if (signature == _lastPublishedSignature) return;
  _cloudTvPublishing = true;
  try {
    final HttpClient client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 5);
    final Uri uri = Uri.parse('$cloudTvBaseUrl/api/publish');
    final HttpClientRequest request = await client.postUrl(uri);
    request.headers.contentType = ContentType.json;
    request.write(
      jsonEncode(<String, dynamic>{
        'brand': 'Billares Don Miguel',
        'updatedAt': DateTime.now().toIso8601String(),
        'tables': payloadTables,
      }),
    );
    final HttpClientResponse response = await request.close().timeout(
      const Duration(seconds: 8),
    );
    await response.drain<void>();
    client.close(force: true);
    if (response.statusCode >= 200 && response.statusCode < 300) {
      _lastPublishedSignature = signature;
    }
  } catch (_) {
    _cloudTvRetryTimer?.cancel();
    _cloudTvRetryTimer = Timer(const Duration(seconds: 5), () {
      publishCloudTvState(tables);
    });
  } finally {
    _cloudTvPublishing = false;
  }
}

void disposeCloudTvSync() {
  _cloudTvRetryTimer?.cancel();
  _cloudTvRetryTimer = null;
}
