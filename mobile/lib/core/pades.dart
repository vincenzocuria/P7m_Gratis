import 'dart:convert';
import 'dart:typed_data';

import 'p7m.dart';

const _detachedSubFilters = {'adbe.pkcs7.detached', 'ETSI.CAdES.detached'};
const _documentTimestamp = 'ETSI.RFC3161';

/// PAdES signatures embedded in a PDF, verified as detached CMS over the
/// bytes listed by each /ByteRange.
List<SignerResult> verifyPades(Uint8List pdf) {
  if (!isPdf(pdf)) return const [];
  final text = latin1.decode(pdf);
  final results = <SignerResult>[];
  final ranges = RegExp(r'/ByteRange\s*\[\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*\]')
      .allMatches(text)
      .toList();
  if (ranges.length > 20) {
    return const [
      SignerResult(
        'Firme nel PDF',
        null,
        'Troppe firme nel PDF: verifica non eseguita',
      ),
    ];
  }
  var number = 0;
  for (final match in ranges) {
    final values = [for (var i = 1; i <= 4; i++) int.tryParse(match[i]!)];
    if (values.any((v) => v == null)) continue;
    final [start, length, start2, length2] = values.cast<int>();
    if (start + length > start2 || start2 + length2 > pdf.length) continue;
    final cms = _contents(text.substring(start + length, start2));
    if (cms == null) continue;
    number++;
    final role = ranges.length == 1
        ? 'Firma nel PDF'
        : 'Firma nel PDF n. $number';
    final subFilter = _subFilter(text, match.start);
    final signed = Uint8List(length + length2)
      ..setRange(0, length, pdf, start)
      ..setRange(length, length + length2, pdf, start2);
    // A later signature or annotation appends a revision after this range.
    final tail = latin1.decode(pdf.sublist(start2 + length2)).trim();
    final note = start != 0
        ? 'Il ByteRange non parte dall\'inizio del PDF'
        : tail.isEmpty
        ? null
        : 'Il PDF è stato modificato dopo questa firma (es. altre firme o annotazioni): la verifica vale per la versione firmata';
    if (subFilter == _documentTimestamp) {
      results.add(
        SignerResult(
          'Marca temporale del documento',
          null,
          'Marca temporale sul PDF: non è una firma',
          null,
          null,
          const [],
          [cms],
          signed,
          role,
        ),
      );
      continue;
    }
    if (subFilter == null || !_detachedSubFilters.contains(subFilter)) {
      results.add(
        SignerResult(
          'Firmatario non identificato',
          null,
          subFilter == null
              ? 'Tipo di firma PDF non indicato'
              : 'Tipo di firma PDF non supportato: $subFilter',
          null,
          null,
          const [],
          const [],
          null,
          role,
        ),
      );
      continue;
    }
    try {
      final data = parseSignedData(cms);
      if (data.content != null) {
        throw const FormatException('Firma PDF non separata');
      }
      if (data.signers.isEmpty) {
        results.add(
          SignerResult(
            'Firmatario non identificato',
            false,
            'Firma PDF senza firmatario',
            null,
            null,
            const [],
            const [],
            null,
            role,
          ),
        );
      }
      for (final signer in data.signers) {
        for (final result in verifySignerTree(
          signer,
          data.certificates,
          signed,
          data.contentType,
        )) {
          final isCounter = result.role.isNotEmpty;
          var detail = result.detail;
          if (note != null && result.integrity == true) {
            detail += '\n$note';
          }
          results.add(
            result.copyWith(
              detail: detail,
              integrity: start != 0 ? false : null,
              role: isCounter ? '${result.role} ($role)' : role,
            ),
          );
        }
      }
    } catch (_) {
      results.add(
        SignerResult(
          'Firmatario non identificato',
          null,
          'Verifica incompleta: firma PDF non leggibile',
          null,
          null,
          const [],
          const [],
          null,
          role,
        ),
      );
    }
  }
  return results;
}

/// Hexadecimal /Contents value, trimmed to the DER length of the CMS.
Uint8List? _contents(String gap) {
  final compact = gap.replaceAll(RegExp(r'\s'), '');
  if (compact.length < 4 ||
      !compact.startsWith('<') ||
      !compact.endsWith('>')) {
    return null;
  }
  final hex = compact.substring(1, compact.length - 1);
  if (hex.length.isOdd || !RegExp(r'^[0-9A-Fa-f]+$').hasMatch(hex)) {
    return null;
  }
  final padded = Uint8List(hex.length ~/ 2);
  for (var i = 0; i < padded.length; i++) {
    padded[i] = int.parse(hex.substring(i * 2, i * 2 + 2), radix: 16);
  }
  if (padded.length < 2 || padded[0] != 0x30) return null;
  var total = 2 + padded[1];
  if (padded[1] >= 0x80) {
    final count = padded[1] & 0x7f;
    if (count == 0 || count > 4 || padded.length < 2 + count) return null;
    var length = 0;
    for (var i = 0; i < count; i++) {
      length = (length << 8) | padded[2 + i];
    }
    total = 2 + count + length;
  }
  if (total > padded.length) return null;
  return Uint8List.sublistView(padded, 0, total);
}

/// /SubFilter of the signature dictionary closest to the ByteRange.
String? _subFilter(String text, int position) {
  final from = position < 8000 ? 0 : position - 8000;
  final to = position + 8000 > text.length ? text.length : position + 8000;
  String? best;
  var distance = 1 << 30;
  for (final m in RegExp(
    r'/SubFilter\s*/([A-Za-z0-9_.]+)',
  ).allMatches(text.substring(from, to))) {
    final d = (from + m.start - position).abs();
    if (d < distance) {
      distance = d;
      best = m[1];
    }
  }
  return best;
}
