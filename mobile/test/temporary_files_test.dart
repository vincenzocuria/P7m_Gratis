import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:p7m_gratis/core/temporary_files.dart';

void main() {
  test(
    'Pulizia limitata alle copie gestite: originali e recenti preservati',
    () async {
      final root = await Directory.systemTemp.createTemp('p7m-clean-test-');
      addTearDown(() => root.delete(recursive: true));
      final original = await File('${root.path}/originale.pdf')
          .writeAsString('originale');
      final exports = await Directory('${root.path}/p7m_exports').create();
      final old = await File('${exports.path}/vecchio.pdf')
          .writeAsString('vecchio');
      final recent = await File('${exports.path}/recente.pdf')
          .writeAsString('recente');
      final now = DateTime.now();
      await old.setLastModified(now.subtract(const Duration(hours: 25)));
      await TemporaryFiles.clean(root, now: now);
      expect(await old.exists(), false);
      expect(await recent.exists(), true);
      expect(await original.readAsString(), 'originale');
      await TemporaryFiles.clean(root, all: true);
      expect(await recent.exists(), false);
      expect(await original.exists(), true);
      expect(await root.exists(), true);
      await expectLater(
        TemporaryFiles.clean(root, all: true, folders: ['../']),
        throwsArgumentError,
      );
      expect(await original.exists(), true);
    },
  );

  test('Nomi esportati sicuri e limitati in byte mantenendo estensione', () {
    final name = '${List.filled(200, 'è').join()}.pdf';
    final safe = TemporaryFiles.exportName(name);
    expect(utf8.encode(safe).length, lessThanOrEqualTo(180));
    expect(safe.endsWith('.pdf'), true);
    expect(
      TemporaryFiles.exportName('../cartella/documento.pdf'),
      '.._cartella_documento.pdf',
    );
    expect(TemporaryFiles.exportName('..'), 'documento');
  });
}
