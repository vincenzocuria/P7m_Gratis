import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:pdfrx/pdfrx.dart';

/// PDF preview that asks for the password of protected documents.
///
/// The preview never stays on an empty grey area: while the document is
/// loading a progress indicator is shown, and if loading does not complete
/// (no document, no error and no password request) a message with a retry
/// button appears after [loadTimeout].
class PasswordPdfPreview extends StatefulWidget {
  const PasswordPdfPreview({
    super.key,
    required this.bytes,
    required this.name,
    this.loadTimeout = const Duration(seconds: 20),
    this.onPassword,
  });

  final Uint8List bytes;
  final String name;
  final Duration loadTimeout;

  /// Called with the password that successfully unlocked the PDF, or with
  /// null when the document opened without one.
  final ValueChanged<String?>? onPassword;

  @override
  State<PasswordPdfPreview> createState() => _PasswordPdfPreviewState();
}

class _PasswordPdfPreviewState extends State<PasswordPdfPreview> {
  var _attempts = 0;
  var _revision = 0;
  var _cancelled = false;
  var _asking = false;
  var _ready = false;
  var _stalled = false;
  var _empty = false;
  String? _lastPassword;
  Timer? _watchdog;
  final _controller = PdfViewerController();
  late PdfDocumentRef _ref = _createRef();

  // A key unique to this preview instance and attempt: pdfrx shares loaded
  // documents (and their errors) between viewers with the same key, so a key
  // made only of the file name could reuse a stale document or error.
  PdfDocumentRef _createRef() => PdfDocumentRefData(
    widget.bytes,
    sourceName: widget.name,
    key: PdfDocumentRefKey(widget.name, [
      identityHashCode(this),
      identityHashCode(widget.bytes),
      _revision,
    ]),
    passwordProvider: _requestPassword,
    firstAttemptByEmptyPassword: true,
    // The bytes are already in memory: load them directly instead of through
    // on-demand native reads.
    maxSizeToCacheOnMemory: widget.bytes.length + 1,
  );

  @override
  void initState() {
    super.initState();
    _startWatchdog();
  }

  @override
  void dispose() {
    _watchdog?.cancel();
    super.dispose();
  }

  void _startWatchdog() {
    _watchdog?.cancel();
    _watchdog = Timer(widget.loadTimeout, () {
      if (!mounted || _ready || _asking) return;
      final listenable = _ref.resolveListenable();
      if (listenable.document == null && listenable.error == null) {
        debugPrint('PDF preview: loading not completed for ${widget.name}');
        setState(() => _stalled = true);
      }
    });
  }

  Future<String?> _requestPassword() async {
    if (!mounted) return null;
    _watchdog?.cancel();
    final incorrect = _attempts++ > 0;
    _asking = true;
    if (mounted) setState(() {});
    String? password;
    try {
      password = await showDialog<String>(
        context: context,
        barrierDismissible: false,
        useRootNavigator: true,
        builder: (_) => PdfPasswordDialog(incorrect: incorrect),
      );
    } catch (e, s) {
      debugPrint('PDF preview: password dialog failed: $e\n$s');
      password = null;
    } finally {
      _asking = false;
    }
    _cancelled = password == null;
    if (!mounted) return null;
    if (!_cancelled) {
      _lastPassword = password;
      _startWatchdog();
    }
    setState(() {});
    return password;
  }

  void _retry() {
    setState(() {
      _attempts = 0;
      _cancelled = false;
      _stalled = false;
      _ready = false;
      _empty = false;
      _lastPassword = null;
      _revision++;
      _ref = _createRef();
    });
    _startWatchdog();
  }

  bool _onTap(
    BuildContext context,
    PdfViewerController controller,
    PdfViewerGeneralTapHandlerDetails details,
  ) {
    if (details.type != PdfViewerGeneralTapType.doubleTap) return false;
    if (!controller.isReady) return false;
    final fit = controller.alternativeFitScale ?? controller.minScale;
    final nearFit = controller.currentZoom <= fit * 1.15;
    if (nearFit) {
      unawaited(controller.zoomUp(zoomCenter: details.documentPosition));
    } else {
      unawaited(controller.setZoom(details.documentPosition, fit));
    }
    return true;
  }

  Widget _message(String text, {bool retry = true}) => Center(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(text, textAlign: TextAlign.center),
          if (retry) ...[
            const SizedBox(height: 12),
            FilledButton(onPressed: _retry, child: const Text('Riprova')),
          ],
        ],
      ),
    ),
  );

  @override
  Widget build(BuildContext context) {
    if (_stalled) {
      return _message(
        'Il PDF non si è aperto. Riprova; se il problema continua salva o '
        'condividi il documento per aprirlo con un\'altra app.',
      );
    }
    if (_empty) {
      return _message(
        'Il PDF non contiene pagine visualizzabili. Salva o condividi il '
        'documento per aprirlo con un\'altra app.',
      );
    }
    return PdfViewer(
      _ref,
      key: ValueKey(_ref.key),
      controller: _controller,
      params: PdfViewerParams(
        sizeDelegateProvider: const PdfViewerSizeDelegateProviderLegacy(
          maxScale: 8,
          minScale: 0.25,
          useAlternativeFitScaleAsMinScale: true,
        ),
        panEnabled: true,
        scaleEnabled: true,
        onGeneralTap: _onTap,
        loadingBannerBuilder: (context, downloaded, total) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const CircularProgressIndicator(),
              const SizedBox(height: 12),
              Text(_asking ? 'In attesa della password…' : 'Apertura del PDF…'),
            ],
          ),
        ),
        onViewerReady: (document, controller) {
          _ready = true;
          _watchdog?.cancel();
          widget.onPassword?.call(_lastPassword);
          if (document.pages.isEmpty && mounted) {
            setState(() => _empty = true);
          }
        },
        errorBannerBuilder: (context, error, stackTrace, documentRef) {
          _watchdog?.cancel();
          debugPrint('PDF preview error: $error');
          return _message(
            _cancelled || error is PdfPasswordException
                ? 'PDF protetto: inserisci la password per aprirlo.'
                : 'Impossibile aprire il PDF. Il file potrebbe essere danneggiato '
                      'o usare un formato non supportato.',
          );
        },
      ),
    );
  }
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
