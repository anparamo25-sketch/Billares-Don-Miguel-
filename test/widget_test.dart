import 'package:flutter_test/flutter_test.dart';
import 'package:billares_don_miguel/main.dart';

void main() {
  testWidgets('La pantalla de acceso muestra Billares Don Miguel', (tester) async {
    await tester.pumpWidget(const BillaresApp());
    expect(find.text('Billares Don Miguel'), findsOneWidget);
  });
}
