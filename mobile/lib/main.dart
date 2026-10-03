import 'dart:convert';
import 'dart:typed_data';
import 'dart:async';
import 'dart:io';

import 'core/certificate_service.dart';
import 'core/revocation.dart';
import 'core/timestamp.dart';

import 'package:flutter/services.dart';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:share_plus/share_plus.dart';
import 'package:pdfrx/pdfrx.dart';
import 'package:url_launcher/url_launcher.dart';

import 'core/p7m.dart';
import 'core/temporary_files.dart';
import 'help.dart';

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
  bool exporting = false;
  late final Future<void> startupCleanup;
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
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        scrollable: true,
        title: const Text('Controllo revoca online'),
        content: const Text(
          'Gli emittenti riceveranno il tuo indirizzo IP e l’identificativo dei certificati. Il documento non viene inviato. Alcuni servizi usano HTTP, senza cifratura della connessione. Puoi leggere ed estrarre il documento anche senza questo controllo.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Annulla'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Controlla online'),
          ),
        ],
      ),
    );
    if (confirmed != true ||
        !mounted ||
        generation != id ||
        checkingRevocation) {
      return;
    }
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
    startupCleanup = cleanOldExports();
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

  Future<void> cleanOldExports() async {
    try {
      await TemporaryFiles.clean(await TemporaryFiles.root());
    } catch (_) {
      // A later manual cleanup reports errors; opening documents stays available.
    }
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
      final result = await compute(decodeDocument, (
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
    if (busy || exporting) return;
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
      final builder = BytesBuilder();
      await for (final chunk in f.readAsByteStream().timeout(
        const Duration(seconds: 30),
      )) {
        if (builder.length + chunk.length > 50 * 1024 * 1024) {
          throw const FormatException('Limite di 50 MB superato');
        }
        builder.add(chunk);
      }
      final bytes = builder.takeBytes();
      final result = await compute(decodeDocument, (bytes, f.name));
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
      // Android clears only file_picker/. The iOS plugin clears its whole tmp
      // directory, so it is called only by explicit cleanup after closing preview.
      if (Platform.isAndroid && !exporting) {
        try {
          await TemporaryFiles.cleanPicker();
        } catch (_) {
          // Manual cleanup remains available.
        }
      }
      if (mounted) {
        setState(() => busy = false);
        drainPending();
      }
    }
  }

  Future<void> export(bool share) async {
    final d = doc;
    if (d == null || exporting) return;
    setState(() => exporting = true);
    try {
      await startupCleanup;
      if (share) {
        final file = await TemporaryFiles.createExport(d.bytes, d.name);
        if (!mounted) return;
        final box = context.findRenderObject() as RenderBox?;
        await SharePlus.instance.share(
          ShareParams(
            files: [XFile(file.path)],
            fileNameOverrides: [TemporaryFiles.exportName(d.name)],
            sharePositionOrigin: box == null
                ? null
                : box.localToGlobal(Offset.zero) & box.size,
          ),
        );
      } else {
        final saved = await FilePicker.saveFile(
          fileName: TemporaryFiles.exportName(d.name),
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
    } finally {
      if (mounted) setState(() => exporting = false);
    }
  }

  Future<void> clearDocuments() async {
    if (busy || exporting || checkingRevocation) return;
    ++generation;
    setState(() {
      busy = true;
      doc = null;
      assessments = [];
      timestampDetails = [];
      error = null;
    });
    var failed = false;
    try {
      await startupCleanup;
      await WidgetsBinding.instance.endOfFrame;
      await TemporaryFiles.clean(await TemporaryFiles.root(), all: true);
    } catch (_) {
      failed = true;
    }
    try {
      await TemporaryFiles.cleanPicker();
    } catch (_) {
      failed = true;
    }
    if (!mounted) return;
    setState(() => busy = false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          failed
              ? 'Documento chiuso. Alcuni temporanei non sono stati cancellati.'
              : 'Documento chiuso e copie temporanee cancellate',
        ),
      ),
    );
    drainPending();
  }

  Future<void> openWebsite(String address) async {
    try {
      if (await launchUrl(
        Uri.parse(address),
        mode: LaunchMode.externalApplication,
      )) {
        return;
      }
    } catch (_) {
      // Keep the document available if a browser cannot be opened.
    }
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Impossibile aprire il browser')),
      );
    }
  }

  void showInformation() {
    showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        scrollable: true,
        title: const Text('P7M Gratis'),
        content: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'Sviluppata da Vincenzo Curia',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            const Text('Versione $appVersion'),
            const SizedBox(height: 12),
            const Text(
              'PDF e documenti P7M in una sola app. Gratuita, senza pubblicità e senza account.',
            ),
            const SizedBox(height: 16),
            TextButton.icon(
              onPressed: () => Navigator.of(
                context,
              ).push(MaterialPageRoute<void>(builder: (_) => const HelpPage())),
              icon: const Icon(Icons.school_outlined),
              label: const Text('Come funziona'),
            ),
            TextButton.icon(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(builder: (_) => const PrivacyPage()),
              ),
              icon: const Icon(Icons.privacy_tip_outlined),
              label: const Text('Privacy'),
            ),
            TextButton.icon(
              onPressed: () => openWebsite(privacyUrl),
              icon: const Icon(Icons.open_in_new),
              label: const Text('Informativa online'),
            ),
            TextButton.icon(
              onPressed: () => openWebsite('mailto:$supportEmail'),
              icon: const Icon(Icons.mail_outline),
              label: const Text('Assistenza e privacy'),
            ),
            const SelectableText(supportEmail),
            TextButton.icon(
              onPressed: () => showLicensePage(
                context: context,
                applicationName: 'P7M Gratis',
                applicationVersion: appVersion,
                applicationLegalese: 'Sviluppata da Vincenzo Curia',
              ),
              icon: const Icon(Icons.code),
              label: const Text('Licenze open source'),
            ),
            TextButton.icon(
              onPressed: () {
                Navigator.pop(dialogContext);
                unawaited(clearDocuments());
              },
              icon: const Icon(Icons.cleaning_services_outlined),
              label: const Text('Chiudi documento e pulisci temporanei'),
            ),
            const SizedBox(height: 8),
            FilledButton.tonalIcon(
              onPressed: () => openWebsite('https://vcuria.app/'),
              icon: const Icon(Icons.language),
              label: const Text('Scopri vcuria.app'),
            ),
            const SizedBox(height: 16),
            const Text(
              'Disponibile anche per Windows: apri ed estrai i P7M sul tuo computer.',
            ),
            const SizedBox(height: 8),
            TextButton.icon(
              onPressed: () => openWebsite(
                'https://github.com/vincenzocuria/P7m_Gratis/releases/tag/v2.1.0',
              ),
              icon: const Icon(Icons.desktop_windows_outlined),
              label: const Text('Versione desktop Windows'),
            ),
            const SizedBox(height: 12),
            const Text(
              'I documenti vengono elaborati sul dispositivo. Il controllo facoltativo della revoca contatta gli emittenti dei certificati.',
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Chiudi'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final d = doc;
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'P7M Gratis',
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        actions: [
          IconButton(
            onPressed: busy || exporting ? null : open,
            tooltip: 'Apri P7M o PDF',
            icon: const Icon(Icons.folder_open),
          ),
          IconButton(
            onPressed: showInformation,
            tooltip: 'Informazioni e sviluppatore',
            icon: const Icon(Icons.help_outline),
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
                        'Leggi i PDF, apri e verifica i P7M. I tuoi documenti restano sul dispositivo, senza account.',
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 24),
                      FilledButton.icon(
                        onPressed: open,
                        icon: const Icon(Icons.folder_open),
                        label: const Text('Apri un P7M o PDF'),
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
              length: d.isPlainPdf ? 1 : 2,
              child: Column(
                children: [
                  DocumentHeader(
                    name: d.name,
                    isPlainPdf: d.isPlainPdf,
                    onSave: exporting ? null : () => export(false),
                    onShare: exporting ? null : () => export(true),
                  ),
                  if (!d.isPlainPdf)
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
                        if (!d.isPlainPdf)
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
                              const Padding(
                                padding: EdgeInsets.symmetric(vertical: 12),
                                child: Text(
                                  'Controllo facoltativo: invia IP e identificativo del certificato agli emittenti, senza il documento. Alcuni servizi usano HTTP.',
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
                                                assessments[index]
                                                        ?.revocation ==
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
      // Keep each document's asynchronous layout separate while switching files.
      return PdfViewer.data(d.bytes, key: ObjectKey(d), sourceName: d.name);
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

/// A bounded header keeps long filenames from displacing the document.
class DocumentHeader extends StatelessWidget {
  const DocumentHeader({
    super.key,
    required this.name,
    required this.isPlainPdf,
    required this.onSave,
    required this.onShare,
  });

  final String name;
  final bool isPlainPdf;
  final VoidCallback? onSave;
  final VoidCallback? onShare;

  @override
  Widget build(BuildContext context) {
    final type = isPlainPdf
        ? 'PDF semplice • non è una busta P7M'
        : 'P7M • documento estratto';
    return Padding(
      padding: const EdgeInsets.only(left: 16, right: 4),
      child: Row(
        children: [
          Expanded(
            child: InkWell(
              borderRadius: BorderRadius.circular(12),
              onTap: () => showDialog<void>(
                context: context,
                builder: (dialogContext) => AlertDialog(
                  scrollable: true,
                  title: const Text('Informazioni documento'),
                  content: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      SelectableText(name),
                      const SizedBox(height: 12),
                      Text(type),
                      if (isPlainPdf) ...[
                        const SizedBox(height: 12),
                        const Text(
                          'Lettura PDF. Eventuali firme interne al PDF (PAdES) non vengono verificate.',
                        ),
                      ],
                    ],
                  ),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(dialogContext),
                      child: const Text('Chiudi'),
                    ),
                  ],
                ),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            type,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ),
                        const Padding(
                          padding: EdgeInsets.symmetric(horizontal: 4),
                          child: Icon(Icons.info_outline, size: 16),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
          IconButton(
            onPressed: onSave,
            tooltip: 'Salva',
            icon: const Icon(Icons.save_alt),
          ),
          IconButton(
            onPressed: onShare,
            tooltip: 'Condividi',
            icon: const Icon(Icons.share),
          ),
        ],
      ),
    );
  }
}
