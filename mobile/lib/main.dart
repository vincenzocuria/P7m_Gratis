import 'dart:convert';

import 'package:flutter/services.dart';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:share_plus/share_plus.dart';
import 'package:pdfrx/pdfrx.dart';

import 'core/p7m.dart';

void main() => runApp(const P7mApp());

class P7mApp extends StatelessWidget {
  const P7mApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'P7M Gratis',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff14635c)),
    ),
    home: const Home(),
  );
}

class Home extends StatefulWidget {
  const Home({super.key});
  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> {
  static const channel = MethodChannel('app.vcuria.p7m/files');
  P7mDocument? doc;
  bool busy = false;
  String? error;
  @override
  void initState() {
    super.initState();
    channel.setMethodCallHandler((call) async {
      if (call.method == 'openFile') {
        await receive(call.arguments);
      } else if (call.method == 'fileError' && mounted) {
        setState(() => error = call.arguments.toString());
      }
    });
    channel
        .invokeMethod<Object?>('initialFile')
        .then((file) async {
          if (file != null) await receive(file);
        })
        .catchError((Object e) {
          if (e is! MissingPluginException && mounted) {
            setState(() => error = 'Impossibile leggere l’allegato');
          }
        });
  }

  Future<void> receive(Object? data) async {
    if (!mounted || busy || data is! Map) return;
    setState(() {
      busy = true;
      error = null;
      doc = null;
    });
    try {
      final result = await compute(decodeP7m, (
        data['bytes'] as Uint8List,
        data['name'] as String,
      ));
      if (mounted) setState(() => doc = result);
    } catch (_) {
      if (mounted) {
        setState(() => error = 'Allegato non supportato o danneggiato');
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  void dispose() {
    channel.setMethodCallHandler(null);
    super.dispose();
  }

  Future<void> open() async {
    try {
      final selection = await FilePicker.pickFile();
      if (selection == null || !mounted) return;
      setState(() {
        busy = true;
        error = null;
        doc = null;
      });
      final f = selection;
      if ((await f.length() ?? 0) > 50 * 1024 * 1024) {
        throw const FormatException('Limite di 50 MB superato');
      }
      final bytes = await f.readAsBytes();
      final result = await compute(decodeP7m, (bytes, f.name));
      if (mounted) setState(() => doc = result);
    } catch (e) {
      if (mounted) {
        setState(
          () => error = e is FormatException
              ? e.message.toString()
              : 'File non supportato o danneggiato',
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> export(bool share) async {
    final d = doc!;
    try {
      if (share) {
        final box = context.findRenderObject() as RenderBox?;
        await SharePlus.instance.share(
          ShareParams(
            files: [XFile.fromData(d.bytes, name: d.name)],
            fileNameOverrides: [d.name],
            sharePositionOrigin: box == null
                ? null
                : box.localToGlobal(Offset.zero) & box.size,
          ),
        );
      } else {
        await FilePicker.saveFile(fileName: d.name, bytes: d.bytes);
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Esportazione non riuscita')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = doc;
    return Scaffold(
      appBar: AppBar(
        title: const Text('P7M Gratis'),
        actions: [
          IconButton(
            onPressed: busy ? null : open,
            tooltip: 'Apri P7M',
            icon: const Icon(Icons.folder_open),
          ),
        ],
      ),
      body: busy
          ? const Center(child: CircularProgressIndicator())
          : d == null
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.description_outlined, size: 80),
                    const SizedBox(height: 20),
                    const Text(
                      'I tuoi documenti, aperti.',
                      style: TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'Apri, verifica ed estrai un P7M. Elaborazione locale, senza account.',
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 24),
                    FilledButton.icon(
                      onPressed: open,
                      icon: const Icon(Icons.folder_open),
                      label: const Text('Apri un documento P7M'),
                    ),
                    if (error != null)
                      Padding(
                        padding: const EdgeInsets.all(16),
                        child: Text(error!),
                      ),
                  ],
                ),
              ),
            )
          : DefaultTabController(
              length: 2,
              child: Column(
                children: [
                  ListTile(
                    title: Text(d.name),
                    trailing: Wrap(
                      children: [
                        IconButton(
                          onPressed: () => export(false),
                          tooltip: 'Salva',
                          icon: const Icon(Icons.save_alt),
                        ),
                        IconButton(
                          onPressed: () => export(true),
                          tooltip: 'Condividi',
                          icon: const Icon(Icons.share),
                        ),
                      ],
                    ),
                  ),
                  const TabBar(
                    tabs: [
                      Tab(text: 'Documento'),
                      Tab(text: 'Firme'),
                    ],
                  ),
                  Expanded(
                    child: TabBarView(
                      children: [
                        preview(d),
                        ListView(
                          padding: const EdgeInsets.all(16),
                          children: [
                            const Card(
                              child: Padding(
                                padding: EdgeInsets.all(16),
                                child: Text(
                                  'Firma e integrità vengono controllate. Catena di fiducia, revoca, marche temporali e qualifica eIDAS non sono ancora verificate.',
                                ),
                              ),
                            ),
                            if (d.signers.isEmpty)
                              const ListTile(
                                title: Text('Nessun firmatario presente'),
                              ),
                            for (final s in d.signers)
                              Card(
                                child: ListTile(
                                  leading: Icon(
                                    s.integrity == true
                                        ? Icons.check_circle_outline
                                        : s.integrity == false
                                        ? Icons.error_outline
                                        : Icons.help_outline,
                                  ),
                                  title: Text(s.name),
                                  subtitle: Text(
                                    '${s.detail}\nScadenza certificato: ${s.expires?.toIso8601String().split('T').first ?? 'non disponibile'}',
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
    );
  }

  Widget preview(P7mDocument d) {
    if (d.bytes.length >= 5 &&
        ascii.decode(d.bytes.sublist(0, 5), allowInvalid: true) == '%PDF-') {
      return PdfViewer.data(d.bytes, sourceName: d.name);
    }
    final ext = d.name.toLowerCase().split('.').last;
    if (['png', 'jpg', 'jpeg', 'gif', 'webp'].contains(ext)) {
      return InteractiveViewer(
        child: Center(
          child: Image.memory(
            d.bytes,
            errorBuilder: (_, _, _) => const Text('Anteprima non disponibile'),
          ),
        ),
      );
    }
    if (['txt', 'xml', 'csv', 'json'].contains(ext)) {
      return SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: SelectableText(
          utf8.decode(d.bytes.take(500000).toList(), allowMalformed: true),
        ),
      );
    }
    return const Center(
      child: Text('Salva o condividi il documento per aprirlo.'),
    );
  }
}
