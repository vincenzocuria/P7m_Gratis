import 'dart:convert';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:xml/xml.dart';

const officeExtensions = {'docx', 'docm', 'dotx', 'odt'};

/// Plain text of a Word (.docx) or OpenDocument (.odt) file, paragraph by
/// paragraph. Returns null when the file cannot be read safely.
String? officeText(Uint8List bytes) {
  try {
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
