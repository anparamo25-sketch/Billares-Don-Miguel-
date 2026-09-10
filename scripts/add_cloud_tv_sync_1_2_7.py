from pathlib import Path
import re

TARGET = Path('lib/main.dart')
source = TARGET.read_text()

if "import 'cloud_tv_sync.dart';" not in source:
    anchor = "import 'package:shared_preferences/shared_preferences.dart';"
    if anchor not in source:
        raise SystemExit('CLOUD TV FAILED: no se encontró el bloque de imports')
    source = source.replace(anchor, anchor + "\nimport 'cloud_tv_sync.dart';", 1)

source = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.7+127';", source, count=1)

publish_call = """publishCloudTvState(tableList.map((BillTable t) => <String, dynamic>{\n        'number': t.number,\n        'status': t.status.name,\n        'start': t.start?.toIso8601String(),\n        'end': t.end?.toIso8601String(),\n        'amount': t.status == TableStatus.playing ? t.liveAmount : t.amount,\n        'rate': t.rate,\n      }).toList());"""

# The TV calculates live elapsed time and live amount itself. Therefore we only publish
# when the logical table state changes; the sync helper suppresses identical payloads.
ticker_marker = "if (mounted) setState(() {});\n    });"
if publish_call not in source:
    if ticker_marker not in source:
        raise SystemExit('CLOUD TV FAILED: no se encontró el ticker principal')
    source = source.replace(
        ticker_marker,
        "if (mounted) setState(() {});\n      " + publish_call + "\n    });",
        1,
    )

if 'disposeCloudTvSync();' not in source:
    dispose_marker = "server?.close(force: true);"
    if dispose_marker not in source:
        raise SystemExit('CLOUD TV FAILED: no se encontró dispose del servidor')
    source = source.replace(dispose_marker, dispose_marker + "\n    disposeCloudTvSync();", 1)

TARGET.write_text(source)
print('OK: aplicación central conectada al publicador Cloud TV')
