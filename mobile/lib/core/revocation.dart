import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:pkcs7/pkcs7.dart' show X509;
import 'package:pointycastle/asn1.dart';
import 'package:pointycastle/export.dart' show Digest;

import 'p7m.dart';

enum RevocationStatus { good, revoked, unknown }

ASN1Sequence sequence(Uint8List bytes) {
  checkAsn1Limits(bytes);
  final parser = ASN1Parser(bytes);
  final value = parser.nextObject() as ASN1Sequence;
  if (parser.hasNext()) {
    throw const FormatException('Dati aggiuntivi non ammessi');
  }
  return value;
}

List<ASN1Object> tbsFields(X509 c) =>
    (c.asn1.elements!.first as ASN1Sequence).elements!;
ASN1Object subjectName(X509 c) {
  final tbs = tbsFields(c);
  return tbs[tbs.first.tag == 0xa0 ? 5 : 4];
}

bool directlyIssued(X509 leaf, X509 issuer) =>
    same(
      leaf.asn1Issuer.elements!.first.encode(),
      subjectName(issuer).encode(),
    ) &&
    verifyDetachedSignature(
          issuer,
          leaf.asn1.elements![1] as ASN1Sequence,
          leaf.asn1.elements!.first.encodedBytes!,
          Uint8List.fromList(
            (leaf.asn1.elements![2] as ASN1BitString).stringValues!,
          ),
        ) ==
        true;
DateTime asTime(ASN1Object o) => o is ASN1UtcTime
    ? o.time!.toUtc()
    : (o as ASN1GeneralizedTime).dateTimeValue!.toUtc();
void requireFresh(DateTime current, DateTime next, DateTime now) {
  if (current.isAfter(now.add(const Duration(minutes: 5))) ||
      next.isBefore(now) ||
      !next.isAfter(current)) {
    throw const FormatException('Risposta di revoca scaduta o incoerente');
  }
}

Map<String, (bool, Uint8List)> extensions(ASN1Sequence list) {
  final result = <String, (bool, Uint8List)>{};
  for (final item in list.elements!) {
    final f = (item as ASN1Sequence).elements!;
    final key = oid(f.first);
    if (result.containsKey(key)) {
      throw const FormatException('Estensione duplicata');
    }
    result[key] = (
      f.length == 3 && (f[1] as ASN1Boolean).boolValue!,
      octets(f.last),
    );
  }
  return result;
}

/// Accepts only complete direct CRLs authenticated by the issuing CA.
RevocationStatus validateCrl(
  Uint8List bytes,
  X509 leaf,
  X509 issuer, {
  DateTime? at,
}) {
  final now = (at ?? DateTime.now()).toUtc();
  if (!directlyIssued(leaf, issuer)) {
    throw const FormatException('Emittente non corrispondente');
  }
  final keyUsage = certificateExtensions(issuer)['2.5.29.15'];
  if (keyUsage != null) {
    final bits =
        (ASN1Parser(keyUsage).nextObject() as ASN1BitString).stringValues!;
    if (bits.isEmpty || bits.first & 2 == 0) {
      throw const FormatException('Emittente senza cRLSign');
    }
  }
  if (ascii
      .decode(bytes.take(10).toList(), allowInvalid: true)
      .startsWith('-----BEGIN')) {
    final text = ascii.decode(bytes);
    bytes = base64.decode(text.replaceAll(RegExp(r'-----[^-]+-----|\s'), ''));
  }
  final crl = sequence(bytes).elements!;
  if (crl.length != 3) throw const FormatException('CRL malformata');
  final tbs = (crl.first as ASN1Sequence).elements!;
  var i = tbs.first is ASN1Integer ? 1 : 0;
  if (!same(tbs[i++].encode(), crl[1].encode()) ||
      !same(tbs[i++].encode(), subjectName(issuer).encode())) {
    throw const FormatException('Emittente CRL non corrispondente');
  }
  final current = asTime(tbs[i++]);
  if (i >= tbs.length ||
      (tbs[i] is! ASN1UtcTime && tbs[i] is! ASN1GeneralizedTime)) {
    throw const FormatException('nextUpdate assente');
  }
  final next = asTime(tbs[i++]);
  requireFresh(current, next, now);
  final entries = <ASN1Object>[];
  if (i < tbs.length && tbs[i] is ASN1Sequence) {
    entries.addAll((tbs[i++] as ASN1Sequence).elements!);
  }
  if (i < tbs.length) {
    if (tbs[i].tag != 0xa0) {
      throw const FormatException('Estensioni CRL malformate');
    }
    final ext = extensions(children(tbs[i++]).single as ASN1Sequence);
    if (ext.containsKey('2.5.29.27') ||
        ext.containsKey('2.5.29.28') ||
        ext.entries.any(
          (e) => e.value.$1 && !['2.5.29.35', '2.5.29.20'].contains(e.key),
        )) {
      throw const FormatException(
        'CRL delta, parziale, indiretta o non supportata',
      );
    }
  }
  if (i != tbs.length ||
      verifyDetachedSignature(
            issuer,
            crl[1] as ASN1Sequence,
            crl.first.encodedBytes!,
            Uint8List.fromList((crl[2] as ASN1BitString).stringValues!),
          ) !=
          true) {
    throw const FormatException('Firma CRL non valida');
  }
  var revoked = false;
  for (final entry in entries) {
    final fields = (entry as ASN1Sequence).elements!;
    if (fields.length < 2 || fields.length > 3) {
      throw const FormatException('Voce CRL malformata');
    }
    if (asTime(fields[1]).isAfter(now.add(const Duration(minutes: 5)))) {
      throw const FormatException('Revoca con data futura');
    }
    if (fields.length == 3) {
      final ext = extensions(fields[2] as ASN1Sequence);
      if (ext.containsKey('2.5.29.29') || ext.values.any((e) => e.$1)) {
        throw const FormatException('Voce CRL non supportata');
      }
      final reason = ext['2.5.29.21'];
      if (reason != null &&
          (ASN1Parser(reason.$2).nextObject() as ASN1Integer).integer ==
              BigInt.from(8)) {
        throw const FormatException('CRL con removeFromCRL non supportata');
      }
    }
    if ((fields.first as ASN1Integer).integer == leaf.serialNumber) {
      revoked = true;
    }
  }
  return revoked ? RevocationStatus.revoked : RevocationStatus.good;
}

ASN1Sequence certId(X509 leaf, X509 issuer) => ASN1Sequence(
  elements: [
    ASN1Sequence(
      elements: [
        ASN1ObjectIdentifier.fromIdentifierString('1.3.14.3.2.26'),
        ASN1Null(),
      ],
    ),
    ASN1OctetString(
      octets: Digest('SHA-1').process(subjectName(issuer).encode()),
    ),
    ASN1OctetString(octets: Digest('SHA-1').process(issuer.publicKeyBytes)),
    ASN1Integer(leaf.serialNumber),
  ],
);
Uint8List ocspRequest(X509 leaf, X509 issuer) => ASN1Sequence(
  elements: [
    ASN1Sequence(
      elements: [
        ASN1Sequence(
          elements: [
            ASN1Sequence(elements: [certId(leaf, issuer)]),
          ],
        ),
      ],
    ),
  ],
).encode();

/// Checks CertID, responder authorization, response signature and freshness.
RevocationStatus validateOcsp(
  Uint8List bytes,
  X509 leaf,
  X509 issuer, {
  DateTime? at,
}) {
  final now = (at ?? DateTime.now()).toUtc();
  if (!directlyIssued(leaf, issuer)) {
    throw const FormatException('Emittente non corrispondente');
  }
  final response = sequence(bytes).elements!;
  if ((response.first as ASN1Integer).integer != BigInt.zero ||
      response.length != 2) {
    throw const FormatException('OCSP non riuscito');
  }
  final responseBytes =
      (children(response[1]).single as ASN1Sequence).elements!;
  if (oid(responseBytes.first) != '1.3.6.1.5.5.7.48.1.1') {
    throw const FormatException('OCSP non supportato');
  }
  final basic = sequence(octets(responseBytes[1])).elements!;
  if (basic.length < 3 || basic.length > 4) {
    throw const FormatException('OCSP malformato');
  }
  final data = (basic.first as ASN1Sequence).elements!;
  var i = data.first.tag == 0xa0 ? 1 : 0;
  final responderId = data[i++];
  final produced = asTime(data[i++]);
  if (produced.isAfter(now.add(const Duration(minutes: 5)))) {
    throw const FormatException('OCSP con data futura');
  }
  final responses = (data[i++] as ASN1Sequence).elements!;
  if (i < data.length) {
    final ext = extensions(children(data[i++]).single as ASN1Sequence);
    if (ext.values.any((v) => v.$1)) {
      throw const FormatException('Estensione OCSP critica sconosciuta');
    }
  }
  if (i != data.length) throw const FormatException('Dati OCSP inattesi');
  final candidates = <X509>[issuer];
  if (basic.length == 4) {
    for (final c in (children(basic[3]).single as ASN1Sequence).elements!) {
      final cert = X509(c as ASN1Sequence);
      if (!candidates.any((existing) => same(existing.der, cert.der))) {
        candidates.add(cert);
      }
    }
  }
  final matching = candidates.where((c) {
    if (responderId.tag == 0xa1) {
      return same(
        children(responderId).single.encode(),
        subjectName(c).encode(),
      );
    }
    if (responderId.tag == 0xa2) {
      return same(
        octets(children(responderId).single),
        Digest('SHA-1').process(c.publicKeyBytes),
      );
    }
    return false;
  }).toList();
  if (matching.length != 1) {
    throw const FormatException('Responder OCSP ambiguo o assente');
  }
  final responder = matching.single;
  if (!same(responder.der, issuer.der)) {
    final ext = certificateExtensions(responder);
    final eku = ext['2.5.29.37'];
    final usage = ext['2.5.29.15'];
    if (!directlyIssued(responder, issuer) ||
        eku == null ||
        !(sequence(eku).elements!.map(oid).contains('1.3.6.1.5.5.7.3.9')) ||
        !ext.containsKey('1.3.6.1.5.5.7.48.1.5') ||
        responder.notBefore.isAfter(now) ||
        responder.notAfter.isBefore(now) ||
        (usage != null &&
            ((ASN1Parser(usage).nextObject() as ASN1BitString)
                        .stringValues!
                        .first &
                    128 ==
                0))) {
      throw const FormatException(
        'Responder OCSP non autorizzato o revoca delegata non accertata',
      );
    }
  }
  if (verifyDetachedSignature(
        responder,
        basic[1] as ASN1Sequence,
        basic.first.encodedBytes!,
        Uint8List.fromList((basic[2] as ASN1BitString).stringValues!),
      ) !=
      true) {
    throw const FormatException('Firma OCSP non valida');
  }
  final selected = responses.where((r) {
    final id = ((r as ASN1Sequence).elements!.first as ASN1Sequence).elements!;
    final digest = hashes[algorithm(id.first)];
    return digest != null &&
        (id[3] as ASN1Integer).integer == leaf.serialNumber &&
        same(
          octets(id[1]),
          Digest(digest).process(subjectName(issuer).encode()),
        ) &&
        same(octets(id[2]), Digest(digest).process(issuer.publicKeyBytes));
  }).toList();
  if (selected.length != 1) {
    throw const FormatException('CertID OCSP assente o duplicato');
  }
  final status = (selected.single as ASN1Sequence).elements!;
  if (status.length < 4 || status[3].tag != 0xa0) {
    throw const FormatException('nextUpdate OCSP assente');
  }
  requireFresh(asTime(status[2]), asTime(children(status[3]).single), now);
  if (produced.isBefore(
    asTime(status[2]).subtract(const Duration(minutes: 5)),
  )) {
    throw const FormatException('producedAt OCSP incoerente');
  }
  if (status.length > 4) {
    final ext = extensions(children(status[4]).single as ASN1Sequence);
    if (status.length != 5 || ext.values.any((v) => v.$1)) {
      throw const FormatException('Estensione OCSP non supportata');
    }
  }
  if (status[1].tag == 0x80 && status[1].valueBytes!.isEmpty) {
    return RevocationStatus.good;
  }
  if (status[1].tag == 0xa1) {
    final revocation = children(status[1]);
    if (revocation.isEmpty ||
        asTime(revocation.first).isAfter(now.add(const Duration(minutes: 5)))) {
      throw const FormatException('Data revoca OCSP non valida');
    }
    return RevocationStatus.revoked;
  }
  return RevocationStatus.unknown;
}

List<String> endpoints(X509 cert, bool ocsp) {
  final ext = certificateExtensions(cert);
  final out = <String>[];
  if (ocsp) {
    final aia = ext['1.3.6.1.5.5.7.1.1'];
    if (aia != null) {
      for (final item in sequence(aia).elements!) {
        final f = (item as ASN1Sequence).elements!;
        if (oid(f.first) == '1.3.6.1.5.5.7.48.1' && f[1].tag == 0x86) {
          out.add(ascii.decode(f[1].valueBytes!));
        }
      }
    }
  } else {
    final crl = ext['2.5.29.31'];
    if (crl != null) {
      for (final point in sequence(crl).elements!) {
        final f = (point as ASN1Sequence).elements!;
        // A full, direct distribution point only: no reasons or cRLIssuer.
        if (f.length != 1 || f.first.tag != 0xa0) continue;
        final name = children(f.first).single;
        if (name.tag != 0xa0) continue;
        for (final uri in children(name)) {
          if (uri.tag == 0x86) out.add(ascii.decode(uri.valueBytes!));
        }
      }
    }
  }
  return out.take(2).toList();
}

bool publicAddress(InternetAddress address) {
  final b = address.rawAddress;
  if (b.length == 16) {
    // Only global unicast, excluding mapped IPv4 and transition mechanisms.
    return b[0] & 0xe0 == 0x20 &&
        !(b[0] == 0x20 && b[1] == 1 && b[2] == 0x0d && b[3] == 0xb8) &&
        !(b[0] == 0x20 && b[1] == 2) &&
        !(b[0] == 0x20 && b[1] == 1 && b[2] == 0 && b[3] == 0);
  }
  return !(b[0] == 0 ||
      b[0] == 10 ||
      b[0] == 127 ||
      b[0] >= 224 ||
      (b[0] == 100 && b[1] >= 64 && b[1] <= 127) ||
      (b[0] == 169 && b[1] == 254) ||
      (b[0] == 172 && b[1] >= 16 && b[1] <= 31) ||
      (b[0] == 192 && b[1] == 168) ||
      (b[0] == 192 && b[1] == 0) ||
      (b[0] == 192 && b[1] == 2) ||
      (b[0] == 198 && (b[1] == 18 || b[1] == 19 || b[1] == 51)) ||
      (b[0] == 203 && b[1] == 0 && b[2] == 113));
}

Future<Uint8List> fetchRevocation(
  String url, [
  Uint8List? requestBody,
  DateTime? deadline,
]) async {
  final uri = Uri.parse(url);
  if (!['http', 'https'].contains(uri.scheme) ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      ![80, 443].contains(uri.port)) {
    throw const FormatException('Endpoint di revoca non consentito');
  }
  final addresses = await InternetAddress.lookup(uri.host)
      .timeout(const Duration(seconds: 4));
  if (addresses.isEmpty || addresses.any((a) => !publicAddress(a))) {
    throw const FormatException('Endpoint locale o privato non consentito');
  }
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 4);
  var remaining =
      deadline?.difference(DateTime.now()) ?? const Duration(seconds: 15);
  if (remaining <= Duration.zero) {
    client.close(force: true);
    throw TimeoutException('Tempo massimo del controllo superato');
  }
  if (remaining > const Duration(seconds: 15)) {
    remaining = const Duration(seconds: 15);
  }
  final timer = Timer(remaining, () => client.close(force: true));
  client.findProxy = (_) => 'DIRECT';
  client.connectionFactory = (url, proxyHost, proxyPort) =>
      connectPinned(url, addresses.first);
  try {
    final request = await client
        .openUrl(requestBody == null ? 'GET' : 'POST', uri)
        .timeout(const Duration(seconds: 5));
    request.followRedirects = false;
    if (requestBody != null) {
      request.headers.set('Content-Type', 'application/ocsp-request');
      request.headers.set('Accept', 'application/ocsp-response');
      request.add(requestBody);
    }
    final response = await request.close().timeout(const Duration(seconds: 5));
    if (response.statusCode != 200) {
      throw const HttpException('Endpoint di revoca non disponibile');
    }
    final builder = BytesBuilder();
    await for (final part in response.timeout(const Duration(seconds: 5))) {
      if (builder.length + part.length > 16 * 1024 * 1024) {
        throw const FormatException('Risposta di revoca troppo grande');
      }
      builder.add(part);
    }
    return builder.takeBytes();
  } finally {
    timer.cancel();
    client.close(force: true);
  }
}

// A custom HttpClient factory must perform TLS itself. Keep the validated IP
// pinned while authenticating the original hostname and sending its SNI.
Future<ConnectionTask<Socket>> connectPinned(
  Uri uri,
  InternetAddress address, {
  SecurityContext? context,
}) async {
  final task = await Socket.startConnect(address, uri.port);
  Socket? connected;
  final socket = task.socket.then((plain) async {
    connected = plain;
    if (uri.scheme != 'https') return plain;
    try {
      final secure = await SecureSocket.secure(
        plain,
        host: uri.host,
        context: context,
      );
      connected = secure;
      return secure;
    } catch (_) {
      plain.destroy();
      rethrow;
    }
  });
  return ConnectionTask.fromSocket(socket, () {
    task.cancel();
    connected?.destroy();
  });
}

RevocationStatus validateRevocationResponse(
  (Uint8List, Uint8List, Uint8List, bool) input,
) {
  try {
    final leaf = X509.fromDer(input.$2), issuer = X509.fromDer(input.$3);
    return input.$4
        ? validateOcsp(input.$1, leaf, issuer)
        : validateCrl(input.$1, leaf, issuer);
  } catch (_) {
    return RevocationStatus.unknown;
  }
}
