import 'dart:convert';
import 'dart:typed_data';
import 'dart:async';

import 'core/certificate_service.dart';
import 'core/revocation.dart';
import 'core/timestamp.dart';

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
  Map? pending;
  List<CertificateAssessment?> assessments = [];
  List<String> timestampDetails = [];
  bool checkingRevocation = false;
  int generation = 0;
  Future<void> updateCertificates(P7mDocument document, int id) async {
    for (var i = 0; i < document.signers.length; i++) {
      final assessment = await CertificateService.assess(document.signers[i]);
      if (!mounted || generation != id) return;
      setState(() => assessments[i] = assessment);
      final signer = document.signers[i];
      final details = <String>[];
      for (final token in signer.timestampTokens) {
        if (signer.signatureBytes == null) break;
        final timestamp = await compute(inspectTimestamp, (
          token,
          signer.signatureBytes!,
        ));
        if (!mounted || generation != id) return;
        var text = timestamp.detail;
        if (timestamp.time != null) {
          text += ': ${timestamp.time!.toIso8601String()}';
        }
        if (timestamp.integrity == true) {
          for (final tsa in timestamp.signers) {
            final trust = await CertificateService.assess(
              tsa,
              at: timestamp.time,
            );
            text += '\nTSA: ${trust.detail}';
          }
          text += '\nValidità storica complessiva non accertata: revoca storica TSA non disponibile';
        }
        details.add(text);
      }
      if (!mounted || generation != id) return;
      setState(
        () => timestampDetails[i] = details.isEmpty
            ? 'Marca temporale assente'
            : details.join('\n'),
      );
    }
  }

  void showDocument(P7mDocument document) {
    final id = ++generation;
    setState(() {
      doc = document;
      assessments = List.filled(document.signers.length, null);
      timestampDetails = List.filled(
        document.signers.length,
        'Controllo marca temporale…',
      );
      checkingRevocation = false;
    });
    unawaited(updateCertificates(document, id));
  }

  void drainPending() {
    final file = pending;
    pending = null;
    if (mounted && file != null) unawaited(receive(file));
  }

  Future<void> checkRevocation() async {
    final document = doc;
    if (document == null || checkingRevocation) return;
    final id = generation;
    setState(() => checkingRevocation = true);
    for (var i = 0; i < document.signers.length; i++) {
      final current =
          assessments[i] ??
          await CertificateService.assess(document.signers[i]);
      final answer = await CertificateService.revocation(
        document.signers[i],
        current,
      );
      if (!mounted || generation != id) return;
      setState(() => assessments[i] = answer);
    }
    if (mounted && generation == id) setState(() => checkingRevocation = false);
  }

  String? error;
  @override
  void initState() {
    super.initState();
    channel.setMethodCallHandler((call) async {
      if (call.method == 'openFile') {
        await receive(call.arguments);
      } else if (call.method == 'fileError' && mounted) {
        setState(() => error = call.arguments.toString());
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error!)));
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
    if (!mounted || data is! Map) return;
    if (busy) {
      pending = data;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Il nuovo documento verrà aperto al termine dell’operazione.',
          ),
        ),
      );
      return;
    }
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
      if (mounted) showDocument(result);
    } catch (_) {
      if (mounted) {
        setState(() => error = 'Allegato non supportato o danneggiato');
      }
    } finally {
      if (mounted) {
        setState(() => busy = false);
        drainPending();
      }
    }
  }

  @override
  void dispose() {
    channel.setMethodCallHandler(null);
    super.dispose();
  }

  Future<void> open() async {
    if (busy) return;
    setState(() => busy = true);
    try {
      final selection = await FilePicker.pickFile();
      if (selection == null || !mounted) return;
      setState(() {
        busy = true;
        error = null;
        doc = null;
      });
      final f = selection;
      if ((f.lengthSync() ?? 0) > 50 * 1024 * 1024) {
        throw const FormatException('Limite di 50 MB superato');
      }
      final builder = BytesBuilder(copy: false);
      await for (final chunk in f.readAsByteStream().timeout(
        const Duration(seconds: 30),
      )) {
        if (builder.length + chunk.length > 50 * 1024 * 1024) {
          throw const FormatException('Limite di 50 MB superato');
        }
        builder.add(chunk);
      }
      final bytes = builder.takeBytes();
      final result = await compute(decodeP7m, (bytes, f.name));
      if (mounted) showDocument(result);
    } catch (e) {
      if (mounted) {
        setState(
          () => error = e is FormatException
              ? e.message.toString()
              : 'File non supportato o danneggiato',
        );
      }
    } finally {
      if (mounted) {
        setState(() => busy = false);
        drainPending();
      }
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
        final saved = await FilePicker.saveFile(
          fileName: d.name,
          bytes: d.bytes,
        );
        if (mounted && saved != null) {
          ScaffoldMessenger.of(context)
              .showSnackBar(const SnackBar(content: Text('Documento salvato')));
        }
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
              child: SingleChildScrollView(
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
                                  'Firma e integrità sono controllate sul dispositivo. La catena usa le radici del sistema. Il controllo online contatta solo gli emittenti dei certificati: il documento non viene caricato. Qualifica eIDAS e validità storica non sono accertate.',
                                ),
                              ),
                            ),
                            if (d.signers.isEmpty)
                              const ListTile(
                                title: Text('Nessun firmatario presente'),
                              ),
                            FilledButton.tonalIcon(
                              onPressed:
                                  checkingRevocation ||
                                      assessments.any((a) => a == null)
                                  ? null
                                  : checkRevocation,
                              icon: checkingRevocation
                                  ? const SizedBox(
                                      width: 18,
                                      height: 18,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Icon(Icons.security),
                              label: Text(
                                checkingRevocation
                                    ? 'Controllo revoca…'
                                    : 'Controlla revoca online',
                              ),
                            ),
                            for (final (index, s) in d.signers.indexed)
                              Card(
                                child: ListTile(
                                  leading: Icon(
                                    (s.integrity == false ||
                                            assessments[index]?.trusted ==
                                                false ||
                                            assessments[index]?.revocation ==
                                                RevocationStatus.revoked)
                                        ? Icons.error_outline
                                        : s.integrity == true &&
                                              assessments[index]?.trusted ==
                                                  true &&
                                              assessments[index]?.revocation ==
                                                  RevocationStatus.good
                                        ? Icons.check_circle_outline
                                        : Icons.help_outline,
                                  ),
                                  title: Text(s.name),
                                  subtitle: Text(
                                    '${s.detail}\n${timestampDetails[index]}\n${assessments[index]?.detail ?? 'Controllo certificato…'}\n${assessments[index]?.revocationDetail ?? 'Revoca non verificata'}\nScadenza certificato: ${s.expires?.toIso8601String().split('T').first ?? 'non disponibile'}',
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
