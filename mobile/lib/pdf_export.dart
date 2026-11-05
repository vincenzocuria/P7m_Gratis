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
    title: const Text('Esporta senza password'),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Crea una copia senza protezione. L\'originale non cambia.'),
        const SizedBox(height: 12),
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          value: _authorized,
          onChanged: (value) => setState(() => _authorized = value ?? false),
          title: const Text('Sono autorizzato'),
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
        child: const Text('Continua'),
      ),
    ],
  );
}
