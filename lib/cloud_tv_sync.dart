import 'dart:async';
import 'dart:convert';
import 'dart:io';

const String cloudTvBaseUrl = 'https://billaresdonmiguel.pages.dev';

String _signature(List<Map<String, dynamic>> tables) => jsonEncode(tables);

Timer? _cloudTvRetryTimer;
String? _lastPublishedSignature;
bool _cloudTvPublishing = false;

Future<void> publishCloudTvState(List<Map<String, dynamic>> tables) async {
  if (_cloudTvPublishing) return;
  final String signature = _signature(tables);
  if (signature == _lastPublishedSignature) return;
  _cloudTvPublishing = true;
  try {
    final HttpClient client = HttpClient()..connectionTimeout = const Duration(seconds: 5);
    final Uri uri = Uri.parse('$cloudTvBaseUrl/api/publish');
    final HttpClientRequest request = await client.postUrl(uri);
    request.headers.contentType = ContentType.json;
    request.write(jsonEncode(<String, dynamic>{
      'brand': 'Billares Don Miguel',
      'updatedAt': DateTime.now().toIso8601String(),
      'tables': tables,
    }));
    final HttpClientResponse response = await request.close().timeout(const Duration(seconds: 8));
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
