import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:pdfrx/pdfrx.dart';

class PasswordPdfPreview extends StatefulWidget {
  const PasswordPdfPreview({
    super.key,
    required this.bytes,
    required this.name,
  });

  final Uint8List bytes;
  final String name;

  @override
  State<PasswordPdfPreview> createState() => _PasswordPdfPreviewState();
}

class _PasswordPdfPreviewState extends State<PasswordPdfPreview> {
  var _attempts = 0;
  var _revision = 0;
  var _cancelled = false;

  Future<String?> _requestPassword() async {
    if (!mounted) return null;
    final incorrect = _attempts++ > 0;
    final password = await showDialog<String>(
      context: context,
      builder: (_) => PdfPasswordDialog(incorrect: incorrect),
    );
    _cancelled = password == null;
    return mounted ? password : null;
  }

  @override
  Widget build(BuildContext context) => PdfViewer.data(
    widget.bytes,
    key: ValueKey(_revision),
    sourceName: widget.name,
    passwordProvider: _requestPassword,
    params: PdfViewerParams(
      errorBannerBuilder: (context, error, stackTrace, documentRef) => Center(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                _cancelled || error is PdfPasswordException
                    ? 'PDF protetto: inserisci la password per aprirlo.'
                    : 'Impossibile aprire il PDF. Il file potrebbe essere danneggiato o usare un formato non supportato.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: () => setState(() {
                  _attempts = 0;
                  _cancelled = false;
                  _revision++;
                }),
                child: const Text('Riprova'),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

class PdfPasswordDialog extends StatefulWidget {
  const PdfPasswordDialog({super.key, this.incorrect = false});

  final bool incorrect;

  @override
  State<PdfPasswordDialog> createState() => _PdfPasswordDialogState();
}

class _PdfPasswordDialogState extends State<PdfPasswordDialog> {
  final _controller = TextEditingController();
  var _visible = false;

  void _submit() => Navigator.of(context).pop(_controller.text);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('PDF protetto da password'),
    content: SingleChildScrollView(
      child: TextField(
        controller: _controller,
        autofocus: true,
        obscureText: !_visible,
        autocorrect: false,
        enableSuggestions: false,
        textInputAction: TextInputAction.done,
        onSubmitted: (_) => _submit(),
        decoration: InputDecoration(
          labelText: 'Password',
          errorText: widget.incorrect ? 'Password errata. Riprova.' : null,
          suffixIcon: IconButton(
            tooltip: _visible ? 'Nascondi password' : 'Mostra password',
            onPressed: () => setState(() => _visible = !_visible),
            icon: Icon(_visible ? Icons.visibility_off : Icons.visibility),
          ),
        ),
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.of(context).pop(),
        child: const Text('Annulla'),
      ),
      FilledButton(onPressed: _submit, child: const Text('Apri')),
    ],
  );
}
