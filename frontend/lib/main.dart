import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

final apiBaseProvider = Provider<String>((ref) => const String.fromEnvironment(
    'API_BASE',
    defaultValue: 'http://localhost:8000'));

final wsProvider = StateProvider<WebSocketChannel?>((ref) => null);

final responsesProvider =
    StateProvider<List<Map<String, dynamic>>>((ref) => []);
final submitStateProvider =
    StateProvider<String?>((ref) => null); // vacio-nulo| en cola | completado
final lastResponseIdProvider = StateProvider<int?>((ref) => null);

Future<List<Map<String, dynamic>>> fetchResponses(String base) async {
  final r = await http.get(Uri.parse('$base/api/responses'));
  if (r.statusCode == 200) {
    final List data = jsonDecode(r.body);
    return data.cast<Map<String, dynamic>>();
  }
  return [];
}

final router = GoRouter(
  routes: [
    GoRoute(path: '/', builder: (ctx, st) => const HomePage()),
    GoRoute(path: '/list', builder: (ctx, st) => const ListPage()),
    GoRoute(
      path: '/detail/:id',
      builder: (ctx, st) {
        final id = int.tryParse(st.pathParameters['id'] ?? '');
        return DetailPage(responseId: id);
      },
    ),
    GoRoute(
      path: '/dashboard/:child',
      builder: (ctx, st) {
        final child = st.pathParameters['child'] ?? '';
        return DashboardPage(childId: child);
      },
    ),
  ],
);

void main() {
  runApp(const ProviderScope(child: MyApp()));
}

class MyApp extends ConsumerWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      routerConfig: router,
      title: 'EmoTrack',
      theme: ThemeData(useMaterial3: true, colorSchemeSeed: Colors.blue),
      locale: const Locale('es'),
      supportedLocales: const [Locale('es'), Locale('en')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
    );
  }
}

class HomePage extends ConsumerStatefulWidget {
  const HomePage({super.key});

  @override
  ConsumerState<HomePage> createState() => _HomePageState();
}

class _HomePageState extends ConsumerState<HomePage> {
  final _childController = TextEditingController();
  final _textController = TextEditingController();

  @override
  void initState() {
    super.initState();
    final base = ref.read(apiBaseProvider);
    final channel = WebSocketChannel.connect(
        Uri.parse(base.replaceFirst('http', 'ws') + '/ws'));
    ref.read(wsProvider.notifier).state = channel;
    channel.stream.listen((event) {
      try {
        final msg = jsonDecode(event);
        if (msg is Map &&
            (msg['type'] == 'task_queued' || msg['type'] == 'task_completed')) {
          if (msg['type'] == 'task_queued') {
            ref.read(submitStateProvider.notifier).state = 'QUEUED';
          }
          if (msg['type'] == 'task_completed') {
            ref.read(submitStateProvider.notifier).state = 'COMPLETED';
          }
          // Refresh list on updates
          fetchResponses(base).then(
              (items) => ref.read(responsesProvider.notifier).state = items);
          if (mounted) {
            final es = _statusEs(ref.read(submitStateProvider) ?? '');
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text('Actualización en tiempo real: $es')),
            );
          }
        }
      } catch (_) {
        // ignore non-JSON pings
      }
    });
  }

  @override
  void dispose() {
    ref.read(wsProvider)?.sink.close();
    super.dispose();
  }

  Future<void> _submit() async {
    final base = ref.read(apiBaseProvider);
    final uri = Uri.parse('$base/api/submit-responses');
    final req = http.MultipartRequest('POST', uri)
      ..fields['child_id'] = _childController.text
      ..fields['text'] = _textController.text
      ..fields['selected_emoji'] = '🙂';
    final res = await req.send();
    final body = await http.Response.fromStream(res);
    if (res.statusCode == 202) {
      try {
        final data = jsonDecode(body.body) as Map<String, dynamic>;
        ref.read(lastResponseIdProvider.notifier).state =
            data['response_id'] as int?;
        ref.read(submitStateProvider.notifier).state = 'QUEUED';
      } catch (_) {}
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Enviado!')));
      }
    } else {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Error: ${res.statusCode} ${body.body}')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Formulario')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            TextField(
                controller: _childController,
                decoration:
                    const InputDecoration(labelText: 'Nombre del niño o niña')),
            const SizedBox(height: 8),
            TextField(
                controller: _textController,
                decoration:
                    const InputDecoration(labelText: '¿Cómo te sientes hoy?')),
            const SizedBox(height: 16),
            Consumer(builder: (ctx, ref, _) {
              final st = ref.watch(submitStateProvider);
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  FilledButton(
                      onPressed: _submit,
                      child: const Text('Enviar respuesta')),
                  const SizedBox(height: 8),
                  if (st != null) Text('Estado del envío: ${_statusEs(st)}'),
                ],
              );
            }),
            const SizedBox(height: 16),
            FilledButton(
                onPressed: () => context.go('/list'),
                child: const Text('Ver respuestas')),
            const SizedBox(height: 8),
            FilledButton(
              onPressed: () {
                final child = _childController.text.trim();
                if (child.isEmpty) {
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text('Ingresa el nombre del niño o niña')));
                } else {
                  context.go('/dashboard/$child');
                }
              },
              child: const Text('Ver panel'),
            ),
          ],
        ),
      ),
    );
  }
}

class ListPage extends ConsumerWidget {
  const ListPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final base = ref.watch(apiBaseProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Respuestas')),
      body: FutureBuilder(
        future: fetchResponses(base),
        builder: (ctx, snap) {
          if (!snap.hasData)
            return const Center(child: CircularProgressIndicator());
          final items = snap.data as List<Map<String, dynamic>>;
          return ListView.builder(
            itemCount: items.length,
            itemBuilder: (ctx, i) {
              final r = items[i];
              return ListTile(
                title: Text('${r['child_name']} — ${r['emotion']}'),
                subtitle: Text(_formatSubtitle(r)),
                onTap: () {
                  final id = r['id'];
                  if (id is int) context.go('/detail/$id');
                },
              );
            },
          );
        },
      ),
    );
  }

  String _formatSubtitle(Map<String, dynamic> r) {
    final created = r['created_at'] as String?;
    String fecha = created ?? '';
    try {
      if (created != null) {
        final dt = DateTime.tryParse(created);
        if (dt != null)
          fecha = DateFormat('dd/MM/yyyy HH:mm', 'es').format(dt.toLocal());
      }
    } catch (_) {}
    final st = _statusEs(r['status'] as String?);
    return '$st • $fecha';
  }
}

class DetailPage extends ConsumerWidget {
  final int? responseId;
  const DetailPage({super.key, required this.responseId});

  Future<Map<String, dynamic>?> _fetchDetail(String base, int id) async {
    final r = await http.get(Uri.parse('$base/api/responses/$id'));
    if (r.statusCode == 200) return jsonDecode(r.body) as Map<String, dynamic>;
    return null;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final base = ref.watch(apiBaseProvider);
    final id = responseId;
    return Scaffold(
      appBar: AppBar(title: const Text('Detalle de respuesta')),
      body: id == null
          ? const Center(child: Text('ID inválido'))
          : FutureBuilder(
              future: _fetchDetail(base, id),
              builder: (ctx, snap) {
                if (snap.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (!snap.hasData || snap.data == null) {
                  return const Center(child: Text('No encontrado'));
                }
                final data = snap.data as Map<String, dynamic>;
                final analysis = data['analysis_json'];
                return Padding(
                  padding: const EdgeInsets.all(16),
                  child: SingleChildScrollView(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Niño/niña: ${data['child_name']}',
                            style: Theme.of(context).textTheme.titleLarge),
                        const SizedBox(height: 8),
                        Text(
                            'Emoción: ${data['emotion']} • Estado: ${_statusEs(data['status'] as String?)}'),
                        const SizedBox(height: 16),
                        Text('Análisis (JSON):',
                            style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 8),
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: Theme.of(context)
                                .colorScheme
                                .surfaceContainerHighest,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(const JsonEncoder.withIndent('  ')
                              .convert(analysis)),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
    );
  }
}

String _statusEs(String? status) {
  switch ((status ?? '').toUpperCase()) {
    case 'QUEUED':
      return 'En cola';
    case 'COMPLETED':
      return 'Completado';
    case 'FAILED':
      return 'Fallido';
    default:
      return status ?? '';
  }
}

class DashboardPage extends ConsumerWidget {
  final String childId;
  const DashboardPage({super.key, required this.childId});

  Future<Map<String, dynamic>?> _fetchDashboard(
      String base, String child) async {
    final r = await http.get(Uri.parse('$base/api/dashboard/$child'));
    if (r.statusCode == 200) return jsonDecode(r.body) as Map<String, dynamic>;
    return null;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final base = ref.watch(apiBaseProvider);
    return Scaffold(
      appBar: AppBar(title: Text('Dashboard — $childId')),
      body: FutureBuilder(
        future: _fetchDashboard(base, childId),
        builder: (ctx, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (!snap.hasData || snap.data == null) {
            return const Center(child: Text('Sin datos'));
          }
          final data = snap.data as Map<String, dynamic>;
          final total = data['total'];
          final byEmotion =
              (data['by_emotion'] as Map?)?.cast<String, dynamic>() ?? {};
          final series =
              (data['series_by_day'] as Map?)?.cast<String, dynamic>() ?? {};
          final sortedDays = series.keys.toList()..sort();
          final spots = <FlSpot>[];
          for (var i = 0; i < sortedDays.length; i++) {
            final day = sortedDays[i];
            final count = (series[day] as num?)?.toDouble() ?? 0.0;
            spots.add(FlSpot(i.toDouble(), count));
          }
          return Padding(
            padding: const EdgeInsets.all(16),
            child: ListView(
              children: [
                Text('Total respuestas: $total',
                    style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 16),
                Text('Por emoción',
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                ...byEmotion.entries.map((e) =>
                    ListTile(title: Text(e.key), trailing: Text('${e.value}'))),
                const SizedBox(height: 16),
                Text('Serie por día',
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                if (spots.isEmpty)
                  const Text('Aún no hay datos suficientes')
                else
                  SizedBox(
                    height: 220,
                    child: LineChart(
                      LineChartData(
                        lineBarsData: [
                          LineChartBarData(
                            spots: spots,
                            isCurved: true,
                            color: Theme.of(context).colorScheme.primary,
                            dotData: const FlDotData(show: true),
                          ),
                        ],
                        titlesData: FlTitlesData(
                          bottomTitles: AxisTitles(
                            sideTitles: SideTitles(
                              showTitles: true,
                              getTitlesWidget: (value, meta) {
                                final idx = value.toInt();
                                if (idx < 0 || idx >= sortedDays.length)
                                  return const SizedBox.shrink();
                                return Padding(
                                  padding: const EdgeInsets.only(top: 4),
                                  child: Text(sortedDays[idx],
                                      style: const TextStyle(fontSize: 10)),
                                );
                              },
                              reservedSize: 32,
                              interval: 1,
                            ),
                          ),
                          leftTitles: AxisTitles(
                            sideTitles:
                                SideTitles(showTitles: true, interval: 1),
                          ),
                          topTitles: const AxisTitles(
                              sideTitles: SideTitles(showTitles: false)),
                          rightTitles: const AxisTitles(
                              sideTitles: SideTitles(showTitles: false)),
                        ),
                        gridData: const FlGridData(show: true),
                        borderData: FlBorderData(show: true),
                      ),
                    ),
                  ),
                const SizedBox(height: 8),
                ...series.entries.map((e) =>
                    ListTile(title: Text(e.key), trailing: Text('${e.value}'))),
              ],
            ),
          );
        },
      ),
    );
  }
}
