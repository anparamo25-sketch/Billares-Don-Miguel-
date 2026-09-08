import 'package:flutter_test/flutter_test.dart';
import 'package:billares_don_miguel/main.dart';

void main() {
  testWidgets('La aplicación inicia correctamente', (tester) async {
    await tester.pumpWidget(const BillaresApp());
    expect(find.byType(LoginPage), findsOneWidget);
  });
}
