import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:flutter/services.dart';

/// Only our export folder and the sharing plugin's folder are managed here.
/// Never follow links or delete the temporary directory itself.
class TemporaryFiles {
  static Future<Directory> root() => getTemporaryDirectory();

  static Future<void> cleanPicker() async {
    if (Platform.isIOS) {
      // The upstream picker discards deletion errors; use a checked native call.
      await const MethodChannel('app.vcuria.p7m/files')
          .invokeMethod<void>('cleanTemporaryFiles');
    } else if (Platform.isAndroid) {
      await clean(await root(), all: true, folders: const ['file_picker']);
    }
  }

  static String exportName(String name) {
    final clean = name.replaceAll(RegExp(r'[\\/\x00-\x1f]'), '_');
    if (clean.isEmpty || clean == '.' || clean == '..') return 'documento';
    if (utf8.encode(clean).length <= 180) return clean;
    final dot = clean.lastIndexOf('.');
    final suffix = dot > 0 && clean.length - dot < 16
        ? clean.substring(dot)
        : '';
    final prefix = StringBuffer();
    var length = utf8.encode(suffix).length;
    for (final rune in clean.runes) {
      final next = String.fromCharCode(rune);
      length += utf8.encode(next).length;
      if (length > 180) break;
      prefix.write(next);
    }
    return '$prefix$suffix';
  }

  static Future<File> createExport(Uint8List bytes, String name) async {
    final base = await root();
    final exports = Directory('${base.path}/p7m_exports');
    await exports.create(recursive: true);
    final folder = await exports.createTemp('document_');
    return File('${folder.path}/${exportName(name)}')
        .writeAsBytes(bytes, flush: true);
  }

  /// The age limit is checked at startup. Manual deletion uses all=true.
  static Future<void> clean(
    Directory base, {
    bool all = false,
    DateTime? now,
    List<String> folders = const ['p7m_exports', 'share_plus'],
  }) async {
    final cutoff = (now ?? DateTime.now()).subtract(const Duration(hours: 24));
    for (final name in folders) {
      if (!const ['p7m_exports', 'share_plus', 'file_picker'].contains(name)) {
        throw ArgumentError('Unmanaged temporary folder');
      }
      final folder = Directory('${base.path}/$name');
      if (await FileSystemEntity.type(folder.path, followLinks: false) !=
          FileSystemEntityType.directory) {
        continue;
      }
      await for (final item in folder.list(followLinks: false)) {
        final stat = await item.stat();
        if (all || stat.modified.isBefore(cutoff)) {
          if (item is Directory) {
            await item.delete(recursive: true);
          } else {
            await item.delete();
          }
        }
      }
    }
  }
}
