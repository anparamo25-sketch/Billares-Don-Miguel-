import 'package:flutter_test/flutter_test.dart';
import 'package:billares_don_miguel/main.dart';

void main() {
  testWidgets('La aplicación inicia en la pantalla de administrador', (
    tester,
  ) async {
    await tester.pumpWidget(const BillaresApp());
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.byType(LoginPage), findsOneWidget);
  });

  test('Las cinco tarifas permanecen bloqueadas con los valores acordados', () {
    expect(tableRates[1], 120);
    expect(tableRates[2], 120);
    expect(tableRates[3], 100);
    expect(tableRates[4], 100);
    expect(tableRates[5], 70);
    expect(appVersion, '1.2.9+129');
  });

  test('Los estados funcionales de una mesa existen sin arquitectura de dispositivos por mesa', () {
    expect(
      TableStatus.values,
      containsAll(<TableStatus>[
        TableStatus.available,
        TableStatus.playing,
        TableStatus.pending,
      ]),
    );
  });
}
