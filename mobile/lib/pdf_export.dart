import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:pdfrx/pdfrx.dart';

/// Rewrites a separate PDF and verifies that it opens without a password.
/// Never pass the signed original to a viewer as though this copy preserved signatures.
Future<Uint8List> pdfWithoutPassword(
  Uint8List source, {
  required PdfPasswordProvider passwordProvider,
}) async {
  final document = await PdfDocument.openData(
    source,
    passwordProvider: passwordProvider,
  );
  try {
    final output = await document.encodePdf(removeSecurity: true);
    if (output.isEmpty) throw StateError('PDF non generato');
    final check = await PdfDocument.openData(output);
    try {
      if (check.isEncrypted || check.pages.length != document.pages.length) {
        throw StateError('Copia PDF non verificata');
      }
    } finally {
      await check.dispose();
    }
    return output;
  } finally {
    await document.dispose();
  }
}

class PdfExportConsentDialog extends StatefulWidget {
  const PdfExportConsentDialog({super.key});

  @override
  State<PdfExportConsentDialog> createState() => _PdfExportConsentDialogState();
}

class _PdfExportConsentDialogState extends State<PdfExportConsentDialog> {
  bool _authorized = false;

  @override
  Widget build(BuildContext context) => AlertDialog(
    scrollable: true,
    title: const Text('Esporta PDF senza password'),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Usa questa funzione solo su documenti tuoi o per i quali sei autorizzato '
          'a rimuovere la protezione. Conoscere la password non implica, da solo, '
          'tale autorizzazione. Rispetta i diritti di terzi e gli obblighi di riservatezza.\n\n'
          'Verrà creata sul dispositivo una nuova copia senza cifratura: chiunque '
          'abbia accesso alla copia potrà leggerla. L’originale non viene modificato. '
          'La riscrittura può invalidare le firme digitali: conserva l’originale '
          'firmato e non usare la copia come prova della validità delle firme.\n\n'
          'Sei responsabile dell’uso e della diffusione della copia. Nei limiti '
          'consentiti dalla legge, lo sviluppatore non risponde degli usi illeciti '
          'dell’utente. Restano ferme le responsabilità non escludibili per legge, '
          'incluse quelle per dolo o colpa grave, e i diritti inderogabili del consumatore.',
        ),
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          value: _authorized,
          onChanged: (value) => setState(() => _authorized = value ?? false),
          title: const Text(
            'Dichiaro di essere autorizzato e di aver compreso gli effetti sulla riservatezza e sulle firme.',
          ),
          controlAffinity: ListTileControlAffinity.leading,
        ),
      ],
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context, false),
        child: const Text('Annulla'),
      ),
      FilledButton(
        onPressed: _authorized ? () => Navigator.pop(context, true) : null,
        child: const Text('Crea copia senza password'),
      ),
    ],
  );
}
