from pathlib import Path

TARGET = Path('lib/main.dart')

def replace_dashboard(source: str) -> str:
    start = source.find('  Widget dashboard() =>')
    end = source.find('\n  Widget historyPage()', start)
    if start < 0 or end < 0:
        raise SystemExit('ADMIN DASHBOARD FAILED: no se encontró dashboard() completo')
    dashboard = r'''  Widget dashboard() => LayoutBuilder(
        builder: (BuildContext context, BoxConstraints constraints) {
          final double width = constraints.maxWidth;
          final int columns = width >= 1100 ? 3 : width >= 650 ? 2 : 1;
          final bool compact = width < 650;
          final int available = tableList.where((BillTable t) => t.status == TableStatus.available).length;
          final int playing = tableList.where((BillTable t) => t.status == TableStatus.playing).length;
          final int pending = tableList.where((BillTable t) => t.status == TableStatus.pending).length;
          Widget metricCard(String title, String value, IconData icon) {
            return Card(elevation: 3, margin: EdgeInsets.zero, child: Padding(padding: EdgeInsets.all(compact ? 14 : 18), child: Row(children: <Widget>[
              Container(width: compact ? 42 : 48, height: compact ? 42 : 48, decoration: BoxDecoration(color: Theme.of(context).colorScheme.primaryContainer, borderRadius: BorderRadius.circular(14)), child: Icon(icon, color: Theme.of(context).colorScheme.onPrimaryContainer)),
              const SizedBox(width: 12),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
                Text(title, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 13)),
                const SizedBox(height: 3),
                Text(value, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: compact ? 21 : 24, fontWeight: FontWeight.w800)),
              ])),
            ])));
          }
          return SingleChildScrollView(
            padding: EdgeInsets.fromLTRB(compact ? 12 : 20, compact ? 12 : 18, compact ? 12 : 20, 24),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: <Widget>[
              Container(
                padding: EdgeInsets.all(compact ? 16 : 22),
                decoration: BoxDecoration(gradient: LinearGradient(colors: <Color>[Theme.of(context).colorScheme.primary, Theme.of(context).colorScheme.primaryContainer]), borderRadius: BorderRadius.circular(22)),
                child: Wrap(alignment: WrapAlignment.spaceBetween, crossAxisAlignment: WrapCrossAlignment.center, spacing: 16, runSpacing: 12, children: <Widget>[
                  Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
                    const Text('Billares Don Miguel', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900, color: Colors.white)),
                    const SizedBox(height: 4),
                    Text('Panel central • Control de mesas', style: TextStyle(color: Colors.white.withValues(alpha: 0.88))),
                  ]),
                  Chip(avatar: Icon(Icons.wifi, size: 18, color: lanIp != null ? Colors.green : Colors.red), label: Text(lanIp != null ? 'LAN conectado' : 'LAN no disponible')),
                ]),
              ),
              const SizedBox(height: 14),
              GridView.count(crossAxisCount: columns, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(), crossAxisSpacing: 12, mainAxisSpacing: 12, childAspectRatio: width >= 1100 ? 2.35 : width >= 650 ? 2.7 : 3.1, children: <Widget>[
                metricCard('Disponibles', '$available', Icons.check_circle_outline),
                metricCard('En juego', '$playing', Icons.sports_bar),
                metricCard('Pendientes', '$pending', Icons.payments_outlined),
                metricCard('Generado hoy', money(todayTotal), Icons.attach_money),
              ]),
              const SizedBox(height: 14),
              Card(elevation: 2, child: Padding(padding: EdgeInsets.all(compact ? 14 : 18), child: Wrap(alignment: WrapAlignment.spaceBetween, crossAxisAlignment: WrapCrossAlignment.center, spacing: 14, runSpacing: 12, children: <Widget>[
                Row(mainAxisSize: MainAxisSize.min, children: <Widget>[
                  Icon(workdayActive ? Icons.lock_open : Icons.lock_outline, color: workdayActive ? Colors.green : Colors.orange),
                  const SizedBox(width: 10),
                  Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
                    const Text('Jornada de trabajo', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                    Text(workdayActive ? 'ABIERTA • ${clock(workdayOpenedAt ?? DateTime.now())}' : 'CERRADA', style: TextStyle(color: workdayActive ? Colors.green : Colors.orange, fontWeight: FontWeight.w700)),
                  ]),
                ]),
                Wrap(spacing: 8, runSpacing: 8, children: <Widget>[
                  if (workdayActive) Text('Juegos: $workdayGames'),
                  if (workdayActive) Text('Generado: ${money(workdayGenerated)}'),
                  if (!workdayActive && workdayClosedAt != null) Text('Cierre: ${clock(workdayClosedAt!)}'),
                  FilledButton.icon(onPressed: workdayActive ? closeWorkday : openWorkday, icon: Icon(workdayActive ? Icons.lock : Icons.lock_open), label: Text(workdayActive ? 'Cerrar jornada' : 'Abrir jornada')),
                ]),
              ]))),
              const SizedBox(height: 12),
              Wrap(spacing: 10, runSpacing: 10, children: <Widget>[
                FilledButton.icon(onPressed: showTvConnection, icon: const Icon(Icons.tv), label: const Text('Mostrar en TV')),
                OutlinedButton.icon(onPressed: checkForUpdate, icon: const Icon(Icons.system_update_alt), label: const Text('Buscar actualización')),
              ]),
              const SizedBox(height: 16),
              Row(children: <Widget>[
                Expanded(child: Text('Estado de las mesas', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800))),
                if (!compact) const Text('🟢 Disponible   🔴 En juego   🟡 Pendiente'),
              ]),
              if (compact) const Padding(padding: EdgeInsets.only(top: 5), child: Align(alignment: Alignment.centerLeft, child: Text('🟢 Disponible   🔴 En juego   🟡 Pendiente', style: TextStyle(fontSize: 12)))),
              const SizedBox(height: 10),
              GridView.builder(padding: EdgeInsets.zero, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(), gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: columns, mainAxisExtent: width >= 1100 ? 350 : width >= 650 ? 365 : 390, crossAxisSpacing: 14, mainAxisSpacing: 14), itemCount: tableList.length, itemBuilder: (_, int index) => tableCard(tableList[index])),
            ]),
          );
        },
      );
'''
    return source[:start] + dashboard + source[end:]

source = TARGET.read_text()
source = replace_dashboard(source)
TARGET.write_text(source)
print('OK: panel administrativo reemplazado por diseño responsive 1.2.7')
