import 'package:flutter_test/flutter_test.dart';
import 'package:billares_don_miguel/main.dart';

void main() {
  testWidgets('La aplicación inicia en la pantalla de administrador', (tester) async {
    await tester.pumpWidget(const BillaresApp());
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.byType(LoginPage), findsOneWidget);
  });
}
