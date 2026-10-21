import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:xml/xml.dart';

const officeExtensions = {'doc', 'docx', 'docm', 'dotx', 'odt'};

/// Plain text of a Word (.doc, .docx) or OpenDocument (.odt) file, paragraph
/// by paragraph. Returns null when the file cannot be read safely.
String? officeText(Uint8List bytes) {
  try {
    if (isOle2(bytes)) {
      final text = word97Text(bytes);
      return text.isEmpty ? null : text;
    }
    final archive = ZipDecoder().decodeBytes(bytes);
    final word = archive.findFile('word/document.xml');
    final entry = word ?? archive.findFile('content.xml');
    // Refuse oversized entries: a small archive can expand enormously.
    if (entry == null || entry.size > 20 * 1024 * 1024) return null;
    final xml = XmlDocument.parse(
      utf8.decode(entry.content, allowMalformed: true),
    );
    final paragraphs = word != null
        ? xml.findAllElements('w:p').map(_wordText)
        : xml.descendantElements
              .where(
                (e) =>
                    e.name.qualified == 'text:p' ||
                    e.name.qualified == 'text:h',
              )
              .map(_odfText);
    final text = paragraphs.join('\n').trim();
    return text.isEmpty ? null : text;
  } catch (_) {
    return null;
  }
}

String _wordText(XmlElement paragraph) {
  final out = StringBuffer();
  for (final node in paragraph.descendantElements) {
    switch (node.name.qualified) {
      case 'w:t':
        out.write(node.innerText);
      case 'w:tab':
        out.write('\t');
      case 'w:br' || 'w:cr':
        out.write('\n');
    }
  }
  return out.toString();
}

String _odfText(XmlElement element) {
  final out = StringBuffer();
  for (final node in element.children) {
    if (node is XmlText) {
      out.write(node.value);
    } else if (node is XmlElement) {
      switch (node.name.qualified) {
        case 'text:tab':
          out.write('\t');
        case 'text:line-break':
          out.write('\n');
        case 'text:s':
          final count = int.tryParse(node.getAttribute('text:c') ?? '') ?? 1;
          out.write(' ' * count.clamp(1, 100));
        default:
          out.write(_odfText(node));
      }
    }
  }
  return out.toString();
}

const _oleMagic = [0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1];
const _maxStream = 64 * 1024 * 1024;
const _freeSect = 0xFFFFFFFF;
const _endOfChain = 0xFFFFFFFE;

/// True for Compound File (OLE2) containers such as Word 97-2003 documents.
bool isOle2(Uint8List bytes) {
  if (bytes.length < 8) return false;
  for (var i = 0; i < 8; i++) {
    if (bytes[i] != _oleMagic[i]) return false;
  }
  return true;
}

/// Extension of an OLE2 Office document from its streams ('doc', 'xls',
/// 'ppt'), or null when it is not one or cannot be read.
String? oleExtension(Uint8List bytes) {
  try {
    final names = _CompoundFile(bytes).entries;
    if (names.containsKey('WordDocument')) return 'doc';
    if (names.containsKey('Workbook') || names.containsKey('Book')) {
      return 'xls';
    }
    if (names.containsKey('PowerPoint Document')) return 'ppt';
  } catch (_) {}
  return null;
}

int _u16(Uint8List b, int offset) =>
    ByteData.sublistView(b).getUint16(offset, Endian.little);

int _u32(Uint8List b, int offset) =>
    ByteData.sublistView(b).getUint32(offset, Endian.little);

List<int> _u32s(Uint8List b) => [
  for (var i = 0; i + 4 <= b.length; i += 4) _u32(b, i),
];

/// Python-style slice: out-of-range bounds are clamped instead of thrown.
Uint8List _slice(Uint8List b, int start, int end) {
  start = start.clamp(0, b.length);
  end = end.clamp(start, b.length);
  return Uint8List.sublistView(b, start, end);
}

/// Minimal read-only Compound File Binary (MS-CFB) reader.
class _CompoundFile {
  _CompoundFile(this.data) {
    if (data.length < 512 || !isOle2(data)) {
      throw const FormatException('Non è un file OLE2');
    }
    sectorSize = 1 << _u16(data, 0x1E);
    if ((sectorSize != 512 && sectorSize != 4096) || _u16(data, 0x20) != 6) {
      throw const FormatException('Dimensione dei settori OLE2 non valida');
    }
    final fatCount = _u32(data, 0x2C);
    final dirStart = _u32(data, 0x30);
    miniCutoff = _u32(data, 0x38);
    final miniFatStart = _u32(data, 0x3C);
    final miniFatCount = _u32(data, 0x40);
    final difatCount = _u32(data, 0x48);
    final fatSectors = [
      for (var i = 0; i < 109; i++)
        if (_u32(data, 0x4C + 4 * i) != _freeSect) _u32(data, 0x4C + 4 * i),
    ];
    var sector = _u32(data, 0x44);
    for (var n = 0; n < min(difatCount, 10000); n++) {
      if (sector == _freeSect || sector == _endOfChain) break;
      final values = _u32s(_sector(sector));
      fatSectors.addAll(
        values.take(values.length - 1).where((v) => v != _freeSect),
      );
      sector = values.last;
    }
    fat = [for (final s in fatSectors.take(fatCount)) ..._u32s(_sector(s))];
    entries = _directory(_chain(dirStart, fat, sectorSize, _sector));
    final root = entries['Root Entry'];
    miniStream = root == null
        ? Uint8List(0)
        : _slice(_chain(root.$1, fat, sectorSize, _sector), 0, root.$2);
    miniFat = miniFatCount == 0
        ? const []
        : _u32s(_chain(miniFatStart, fat, sectorSize, _sector));
  }

  final Uint8List data;
  late final int sectorSize;
  late final int miniCutoff;
  late final List<int> fat;
  late final List<int> miniFat;
  late final Map<String, (int, int)> entries;
  late final Uint8List miniStream;

  Uint8List _sector(int index) {
    final start = (index + 1) * sectorSize;
    if (start + sectorSize > data.length) {
      throw const FormatException('Settore OLE2 fuori dal file');
    }
    return Uint8List.sublistView(data, start, start + sectorSize);
  }

  Uint8List _miniSector(int index) {
    final start = index * 64;
    if (start + 64 > miniStream.length) {
      throw const FormatException('Mini settore OLE2 fuori dallo stream');
    }
    return Uint8List.sublistView(miniStream, start, start + 64);
  }

  static Uint8List _chain(
    int start,
    List<int> table,
    int size,
    Uint8List Function(int) read,
  ) {
    final out = BytesBuilder(copy: false);
    final seen = <int>{};
    var sector = start;
    while (sector != _endOfChain && sector != _freeSect) {
      if (!seen.add(sector) ||
          sector >= table.length ||
          out.length > _maxStream) {
        throw const FormatException('Catena OLE2 non valida');
      }
      out.add(read(sector));
      sector = table[sector];
    }
    return out.takeBytes();
  }

  static Map<String, (int, int)> _directory(Uint8List raw) {
    final entries = <String, (int, int)>{};
    for (var offset = 0; offset + 128 <= raw.length; offset += 128) {
      final nameLength = _u16(raw, offset + 64);
      final kind = raw[offset + 66];
      if (!const {1, 2, 5}.contains(kind) ||
          nameLength < 2 ||
          nameLength > 64) {
        continue;
      }
      // The stored length counts the UTF-16 terminator.
      final name = String.fromCharCodes([
        for (var i = 0; i + 2 <= nameLength - 2; i += 2) _u16(raw, offset + i),
      ]);
      final size =
          _u32(raw, offset + 120) + _u32(raw, offset + 124) * 0x100000000;
      entries.putIfAbsent(name, () => (_u32(raw, offset + 116), size));
    }
    return entries;
  }

  Uint8List stream(String name) {
    final entry = entries[name];
    if (entry == null) throw FormatException('Stream OLE2 assente: $name');
    final (start, size) = entry;
    if (size > _maxStream) {
      throw const FormatException('Stream OLE2 troppo grande');
    }
    final bytes = size < miniCutoff && name != 'Root Entry'
        ? _chain(start, miniFat, 64, _miniSector)
        : _chain(start, fat, sectorSize, _sector);
    return _slice(bytes, 0, size);
  }
}

/// Main document text of a Word 97-2003 file, read through its piece table
/// (CLX). Footnotes, headers and comments past ccpText are left out.
String word97Text(Uint8List bytes) {
  final ole = _CompoundFile(bytes);
  final word = ole.stream('WordDocument');
  if (word.length < 0x1AA || _u16(word, 0) != 0xA5EC) {
    throw const FormatException('Documento Word non riconosciuto');
  }
  final flags = _u16(word, 0x0A);
  if (flags & 0x0100 != 0) {
    throw const FormatException('Documento Word cifrato');
  }
  final table = ole.stream(flags & 0x0200 != 0 ? '1Table' : '0Table');
  final ccpText = ByteData.sublistView(word).getInt32(0x4C, Endian.little);
  final fcClx = _u32(word, 0x1A2);
  final clx = _slice(table, fcClx, fcClx + _u32(word, 0x1A6));
  var pos = 0;
  while (pos < clx.length && clx[pos] == 0x01) {
    // Skip Prc entries (property modifiers) before the piece table.
    final size = ByteData.sublistView(clx).getInt16(pos + 1, Endian.little);
    if (size < 0) throw const FormatException('Tabella dei pezzi non valida');
    pos += 3 + size;
  }
  if (pos >= clx.length || clx[pos] != 0x02) {
    throw const FormatException('Tabella dei pezzi assente');
  }
  final plc = _slice(clx, pos + 5, pos + 5 + _u32(clx, pos + 1));
  final count = (plc.length - 4) ~/ 12;
  if (count < 1) return '';
  final cps = [for (var i = 0; i <= count; i++) _u32(plc, 4 * i)];
  final text = StringBuffer();
  var total = 0;
  for (var i = 0; i < count; i++) {
    if (ccpText > 0 && total >= ccpText) break;
    final fc = _u32(plc, (count + 1) * 4 + i * 8 + 2);
    final length = cps[i + 1] - cps[i];
    if (length <= 0 || length > _maxStream) continue;
    if (fc & 0x40000000 != 0) {
      // Compressed piece: one cp1252 byte per character.
      final start = (fc & 0x3FFFFFFF) ~/ 2;
      text.write(_cp1252(_slice(word, start, start + length)));
    } else {
      final piece = _slice(word, fc, fc + 2 * length);
      text.write(
        String.fromCharCodes([
          for (var j = 0; j + 2 <= piece.length; j += 2) _u16(piece, j),
        ]),
      );
      if (piece.length.isOdd) text.write('�');
    }
    total += length;
  }
  var result = text.toString();
  if (ccpText > 0 && result.length > ccpText) {
    result = result.substring(0, ccpText);
  }
  return _cleanWordText(result);
}

/// Windows-1252 bytes 0x80-0x9F; the others match Latin-1. Dart has no
/// cp1252 codec, so the table is written out by hand.
const _cp1252High = [
  0x20AC, 0xFFFD, 0x201A, 0x0192, 0x201E, 0x2026, 0x2020, 0x2021, //
  0x02C6, 0x2030, 0x0160, 0x2039, 0x0152, 0xFFFD, 0x017D, 0xFFFD, //
  0xFFFD, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014, //
  0x02DC, 0x2122, 0x0161, 0x203A, 0x0153, 0xFFFD, 0x017E, 0x0178, //
];

String _cp1252(Uint8List bytes) => String.fromCharCodes([
  for (final b in bytes) b >= 0x80 && b < 0xA0 ? _cp1252High[b - 0x80] : b,
]);

String _cleanWordText(String text) {
  // Fields: keep the displayed result, drop the instruction
  // (0x13 instruction 0x14 result 0x15).
  final out = StringBuffer();
  final stack = <bool>[];
  for (final ch in text.split('')) {
    if (ch == '\x13') {
      stack.add(true);
    } else if (ch == '\x14' && stack.isNotEmpty) {
      stack.last = false;
    } else if (ch == '\x15' && stack.isNotEmpty) {
      stack.removeLast();
    } else if (stack.isEmpty || !stack.last) {
      out.write(ch);
    }
  }
  return out
      .toString()
      .replaceAll('\r\x07', '\n')
      .replaceAll('\x07', '\t')
      .replaceAll('\r', '\n')
      .replaceAll('\x0b', '\n')
      .replaceAll('\x0c', '\n\n')
      .replaceAll(RegExp(r'[\x00-\x08\x0e-\x1f]'), '')
      .replaceAll(RegExp(r'\n{3,}'), '\n\n')
      .trim();
}
