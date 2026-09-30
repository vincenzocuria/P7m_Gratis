import 'dart:typed_data';

import 'package:pkcs7/pkcs7.dart' show X509;
import 'package:pointycastle/asn1.dart';
import 'package:pointycastle/export.dart' show Digest;

import 'p7m.dart';
import 'revocation.dart';

class TimestampResult {
  final bool? integrity;
  final DateTime? time;
  final String detail;
  final List<SignerResult> signers;
  const TimestampResult(
    this.integrity,
    this.time,
    this.detail, [
    this.signers = const [],
  ]);
}

TimestampResult inspectTimestamp((Uint8List, Uint8List) input) {
  try {
    final token = sequence(input.$1).elements!;
    final data = (children(token[1]).single as ASN1Sequence).elements!;
    final content = (data[2] as ASN1Sequence).elements!;
    if (oid(content.first) != '1.2.840.113549.1.9.16.1.4') {
      return const TimestampResult(false, null, 'Contenuto marca non TSTInfo');
    }
    final decoded = decodeP7m((input.$1, 'marca.tst'));
    final info = sequence(decoded.bytes).elements!;
    final imprint = (info[2] as ASN1Sequence).elements!;
    final digest = hashes[algorithm(imprint.first)];
    if (digest == null) {
      return const TimestampResult(
        null,
        null,
        'Algoritmo della marca non supportato',
      );
    }
    final time = asTime(info[4]);
    if (!same(octets(imprint[1]), Digest(digest).process(input.$2)) ||
        decoded.signers.isEmpty ||
        decoded.signers.any((s) => s.integrity == false)) {
      return TimestampResult(
        false,
        time,
        'Firma o impronta della marca non valida',
      );
    }
    if (time.isAfter(DateTime.now().toUtc().add(const Duration(minutes: 5)))) {
      return TimestampResult(false, time, 'Marca temporale con data futura');
    }
    for (final signer in decoded.signers) {
      if (signer.certificate == null || signer.integrity != true) {
        return TimestampResult(null, time, 'Firma della marca non verificata');
      }
      final cert = X509.fromDer(signer.certificate!);
      final tbs = tbsFields(cert);
      var validEku = false;
      for (final item in tbs) {
        if (item.tag == 0xa3) {
          final ext = extensions(children(item).single as ASN1Sequence);
          final eku = ext['2.5.29.37'];
          if (eku != null && eku.$1) {
            final purposes = sequence(eku.$2).elements!.map(oid).toList();
            validEku =
                purposes.length == 1 && purposes.single == '1.3.6.1.5.5.7.3.8';
          }
        }
      }
      if (!validEku ||
          cert.notBefore.isAfter(time) ||
          cert.notAfter.isBefore(time)) {
        return TimestampResult(
          false,
          time,
          'Certificato TSA non idoneo alla data della marca',
        );
      }
    }
    return TimestampResult(
      true,
      time,
      'Firma e impronta della marca verificate',
      decoded.signers,
    );
  } catch (_) {
    return const TimestampResult(
      null,
      null,
      'Marca temporale non verificabile',
    );
  }
}
