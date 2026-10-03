import 'dart:typed_data';

import 'package:pkcs7/pkcs7.dart' show X509;
import 'package:pointycastle/export.dart';
import 'package:pointycastle/asn1.dart';

class SignerResult {
  final String name, detail;
  final bool? integrity;
  final DateTime? expires;
  final Uint8List? certificate;
  final List<Uint8List> certificates;
  final List<Uint8List> timestampTokens;
  final Uint8List? signatureBytes;
  const SignerResult(
    this.name,
    this.integrity,
    this.detail, [
    this.expires,
    this.certificate,
    this.certificates = const [],
    this.timestampTokens = const [],
    this.signatureBytes,
  ]);
}

class P7mDocument {
  final Uint8List bytes;
  final String name;
  final List<SignerResult> signers;
  final bool isPlainPdf;
  const P7mDocument(
    this.bytes,
    this.name,
    this.signers, {
    this.isPlainPdf = false,
  });
}

P7mDocument decodeDocument((Uint8List, String) input) {
  if (input.$1.length > 50 * 1024 * 1024) {
    throw const FormatException('Limite di 50 MB superato');
  }
  final bytes = input.$1;
  if (bytes.length >= 8 &&
      same(bytes.sublist(0, 5), [0x25, 0x50, 0x44, 0x46, 0x2d])) {
    final name = input.$2
        .split(RegExp(r'[/\\]'))
        .last
        .replaceAll(RegExp(r'[\x00-\x1f]'), '_');
    return P7mDocument(bytes, name, const [], isPlainPdf: true);
  }
  return decodeP7m(input);
}

List<ASN1Object> children(ASN1Object o) {
  final p = ASN1Parser(o.valueBytes);
  final result = <ASN1Object>[];
  while (p.hasNext()) {
    result.add(p.nextObject());
  }
  return result;
}

String oid(ASN1Object o) =>
    (o as ASN1ObjectIdentifier).objectIdentifierAsString!;
String algorithm(ASN1Object o) => oid((o as ASN1Sequence).elements!.first);
bool same(List<int> a, List<int> b) {
  if (a.length != b.length) return false;
  var diff = 0;
  for (var i = 0; i < a.length; i++) {
    diff |= a[i] ^ b[i];
  }
  return diff == 0;
}

Uint8List octets(ASN1Object o) {
  if (o.tag == 4) return o.valueBytes!;
  if (o.tag == 0x24 || o.tag == 0xa0) {
    return Uint8List.fromList(children(o).expand((c) => octets(c)).toList());
  }
  throw const FormatException('Contenuto P7M non riconosciuto');
}

const hashes = {
  '1.3.14.3.2.26': 'SHA-1',
  '2.16.840.1.101.3.4.2.1': 'SHA-256',
  '2.16.840.1.101.3.4.2.2': 'SHA-384',
  '2.16.840.1.101.3.4.2.3': 'SHA-512',
};
const rsaHashes = {
  '1.2.840.113549.1.1.5': 'SHA-1',
  '1.2.840.113549.1.1.11': 'SHA-256',
  '1.2.840.113549.1.1.12': 'SHA-384',
  '1.2.840.113549.1.1.13': 'SHA-512',
};

P7mDocument decodeP7m((Uint8List, String) input) {
  if (input.$1.length > 50 * 1024 * 1024) {
    throw const FormatException('Limite di 50 MB superato');
  }
  var bytes = input.$1;
  var name = input.$2
      .split(RegExp(r'[/\\]'))
      .last
      .replaceAll(RegExp(r'[\x00-\x1f]'), '_');
  final results = <SignerResult>[];
  for (var depth = 0; depth < 8; depth++) {
    checkAsn1Limits(bytes);
    final parser = ASN1Parser(bytes);
    final envelope = (parser.nextObject() as ASN1Sequence).elements!;
    if (parser.hasNext() ||
        envelope.length != 2 ||
        oid(envelope.first) != '1.2.840.113549.1.7.2') {
      throw const FormatException('Il file non è una busta CMS SignedData');
    }
    final sd = (children(envelope[1]).single as ASN1Sequence).elements!;
    final content = (sd[2] as ASN1Sequence).elements!;
    if (content.length != 2) {
      throw const FormatException(
        'Firma separata: manca il documento originale',
      );
    }
    final payload = octets(content[1]);
    final certs = <X509>[];
    for (final field in sd.skip(3)) {
      if (field.tag == 0xa0) {
        for (final c in children(field)) {
          if (c is ASN1Sequence) {
            try {
              final cert = X509(c);
              if (!certs.any((existing) => same(existing.der, cert.der))) {
                certs.add(cert);
              }
            } catch (_) {
              /* Report missing certificate below. */
            }
          }
        }
      }
    }
    final signers = (sd.last as ASN1Set).elements!;
    if (signers.length > 100 || certs.length > 100) {
      throw const FormatException('Troppi firmatari o certificati');
    }
    for (final signer in signers) {
      results.add(
        verifySigner(
          signer as ASN1Sequence,
          certs,
          payload,
          oid(content.first),
        ),
      );
    }
    bytes = payload;
    name = name.replaceFirst(RegExp(r'\.p7m$', caseSensitive: false), '');
    if (!isSignedData(bytes)) {
      name = name.replaceAll(RegExp(r'(\.p7m)+$', caseSensitive: false), '');
      return P7mDocument(bytes, documentName(name, bytes), results);
    }
  }
  throw const FormatException('Troppe buste P7M annidate');
}

SignerResult verifySigner(
  ASN1Sequence signer,
  List<X509> certs,
  Uint8List payload,
  String contentType,
) {
  var name = 'Firmatario non identificato';
  DateTime? expiry;
  Uint8List? certificate;
  Uint8List? signature;
  final timestampTokens = <Uint8List>[];
  SignerResult result(
    String name,
    bool? integrity,
    String detail, [
    DateTime? expires,
  ]) => SignerResult(
    name,
    integrity,
    detail,
    expires,
    certificate,
    certs.map((c) => c.der).toList(),
    timestampTokens,
    signature,
  );
  try {
    final s = signer.elements!;
    final sid = s[1];
    // Match BOTH issuer and serial. Never select the first certificate.
    final matches = certs
        .where((c) => matchesSignerCertificate(sid, c))
        .toList();
    if (matches.length != 1) {
      return result(
        name,
        null,
        'Certificato assente o identificatore non supportato',
      );
    }
    final cert = matches.single;
    certificate = cert.der;
    if (cert.publicKeyBytes.length > 16384) {
      return result(name, null, 'Chiave oltre i limiti supportati');
    }
    name = cert.subject.map((e) => '${e.value}').join(', ');
    expiry = cert.notAfter;
    final hashName = hashes[algorithm(s[2])];
    if (hashName == null) {
      return result(name, null, 'Algoritmo hash non supportato', expiry);
    }
    var index = 3;
    var signed = payload;
    if (s[index].tag == 0xa0) {
      final attrs = s[index++];
      final encodedAttributes = children(attrs)
          .map((a) => a.encodedBytes!)
          .toList();
      for (var n = 1; n < encodedAttributes.length; n++) {
        if (compareBytes(encodedAttributes[n - 1], encodedAttributes[n]) > 0) {
          return result(
            name,
            false,
            'Attributi firmati non in ordine DER',
            expiry,
          );
        }
      }
      requireDer(attrs.encodedBytes!);
      final digests = <ASN1Object>[];
      final types = <ASN1Object>[];
      var digestCount = 0;
      var typeCount = 0;
      final attributeIds = <String>{};
      for (final a in children(attrs)) {
        final fields = (a as ASN1Sequence).elements!;
        if (fields.length != 2 || !attributeIds.add(oid(fields.first))) {
          return result(
            name,
            false,
            'Attributi firmati duplicati o malformati',
            expiry,
          );
        }
        final values = (fields[1] as ASN1Set).elements!;
        if (oid(fields[0]) == '1.2.840.113549.1.9.4') {
          digestCount++;
          digests.addAll(values);
        }
        if (oid(fields[0]) == '1.2.840.113549.1.9.3') {
          typeCount++;
          types.addAll(values);
        }
      }
      if (digestCount != 1 ||
          typeCount != 1 ||
          digests.length != 1 ||
          types.length != 1 ||
          oid(types.single) != contentType ||
          !same(octets(digests.single), Digest(hashName).process(payload))) {
        return result(
          name,
          false,
          'Digest o attributi firmati non validi',
          expiry,
        );
      }
      signed = Uint8List.fromList(attrs.encodedBytes!);
      if (signed[1] == 0x80) {
        return result(name, null, 'Attributi BER non supportati', expiry);
      }
      signed[0] = 0x31;
    } else if (contentType != '1.2.840.113549.1.7.1') {
      return result(
        name,
        false,
        'Attributi firmati obbligatori assenti',
        expiry,
      );
    }
    final sigAlgorithm = s[index++] as ASN1Sequence;
    final sigAlg = algorithm(sigAlgorithm);
    final signatureBytes = octets(s[index]);
    signature = signatureBytes;
    for (final item in s.skip(index + 1)) {
      if (item.tag == 0xa1) {
        for (final attr in children(item)) {
          final fields = (attr as ASN1Sequence).elements!;
          if (oid(fields.first) == '1.2.840.113549.1.9.16.2.14') {
            for (final token in (fields[1] as ASN1Set).elements!) {
              if (timestampTokens.length >= 4) {
                throw const FormatException('Troppe marche temporali');
              }
              timestampTokens.add(token.encodedBytes!);
            }
          }
        }
      }
    }
    bool ok;
    const ecHashes = {
      '1.2.840.10045.4.1': 'SHA-1',
      '1.2.840.10045.4.3.2': 'SHA-256',
      '1.2.840.10045.4.3.3': 'SHA-384',
      '1.2.840.10045.4.3.4': 'SHA-512',
    };
    if (sigAlgorithm.elements!.length > 2 ||
        (ecHashes.containsKey(sigAlg) && sigAlgorithm.elements!.length != 1) ||
        ((sigAlg == '1.2.840.113549.1.1.1' || rsaHashes.containsKey(sigAlg)) &&
            sigAlgorithm.elements!.length == 2 &&
            sigAlgorithm.elements![1] is! ASN1Null)) {
      return result(name, false, 'Parametri di firma non validi', expiry);
    }
    if (cert.publicKeyAlgorithmOI.objectIdentifierAsString ==
            '1.2.840.113549.1.1.1' &&
        (cert.publicKey.modulus!.bitLength < 1024 ||
            cert.publicKey.modulus!.bitLength > 8192)) {
      return result(
        name,
        null,
        'Dimensione della chiave RSA non supportata',
        expiry,
      );
    }
    if (ecHashes[sigAlg] == hashName &&
        cert.publicKeyAlgorithmOI.objectIdentifierAsString ==
            '1.2.840.10045.2.1') {
      final tbs = (cert.asn1.elements!.first as ASN1Sequence).elements!;
      final offset = tbs.first.tag == 0xa0 ? 0 : -1;
      final spki = (tbs[offset + 6] as ASN1Sequence).elements!;
      final keyAlg = (spki.first as ASN1Sequence).elements!;
      const curves = {
        '1.2.840.10045.3.1.7': 'prime256v1',
        '1.3.132.0.34': 'secp384r1',
        '1.3.132.0.35': 'secp521r1',
      };
      final curve = curves[oid(keyAlg[1])];
      if (curve == null) {
        return result(name, null, 'Curva EC non supportata', expiry);
      }
      final domain = ECDomainParameters(curve);
      final publicKey = ECPublicKey(
        domain.curve.decodePoint(cert.publicKeyBytes),
        domain,
      );
      final sigParser = ASN1Parser(signatureBytes);
      final integers = (sigParser.nextObject() as ASN1Sequence).elements!;
      if (sigParser.hasNext() || integers.length != 2) {
        return result(name, false, 'Firma EC malformata', expiry);
      }
      final verifier = Signer('$hashName/ECDSA');
      verifier.init(false, PublicKeyParameter<ECPublicKey>(publicKey));
      ok = verifier.verifySignature(
        signed,
        ECSignature(
          (integers[0] as ASN1Integer).integer!,
          (integers[1] as ASN1Integer).integer!,
        ),
      );
    } else if (sigAlg == '1.2.840.113549.1.1.10' &&
        cert.publicKeyAlgorithmOI.objectIdentifierAsString ==
            '1.2.840.113549.1.1.1') {
      var pssHash = 'SHA-1';
      var mgfHash = 'SHA-1';
      var saltLength = 20;
      var trailer = 1;
      final seen = <int>{};
      if (sigAlgorithm.elements!.length != 2) {
        return result(name, null, 'Parametri RSA-PSS assenti', expiry);
      }
      for (final p in (sigAlgorithm.elements![1] as ASN1Sequence).elements!) {
        if (!seen.add(p.tag!)) {
          return result(name, false, 'Parametri RSA-PSS duplicati', expiry);
        }
        final value = children(p).single;
        switch (p.tag) {
          case 0xa0:
            pssHash = hashes[algorithm(value)] ?? '';
          case 0xa1:
            final mgf = (value as ASN1Sequence).elements!;
            if (oid(mgf.first) != '1.2.840.113549.1.1.8') {
              return result(name, null, 'MGF non supportata', expiry);
            }
            mgfHash = hashes[algorithm(mgf[1])] ?? '';
          case 0xa2:
            saltLength = (value as ASN1Integer).integer!.toInt();
          case 0xa3:
            trailer = (value as ASN1Integer).integer!.toInt();
          default:
            return result(name, false, 'Parametri RSA-PSS sconosciuti', expiry);
        }
      }
      if (pssHash != hashName ||
          mgfHash.isEmpty ||
          saltLength < 0 ||
          saltLength > 512 ||
          trailer != 1) {
        return result(name, false, 'Parametri RSA-PSS incompatibili', expiry);
      }
      final verifier = PSSSigner(RSAEngine(), Digest(pssHash), Digest(mgfHash));
      verifier.init(
        false,
        ParametersWithSaltConfiguration(
          PublicKeyParameter<RSAPublicKey>(cert.publicKey),
          SecureRandom('Fortuna'),
          saltLength,
        ),
      );
      ok = verifier.verifySignature(signed, PSSSignature(signatureBytes));
    } else if ((sigAlg == '1.2.840.113549.1.1.1' ||
            rsaHashes[sigAlg] == hashName) &&
        cert.publicKeyAlgorithmOI.objectIdentifierAsString ==
            '1.2.840.113549.1.1.1') {
      final verifier = Signer('$hashName/RSA');
      verifier.init(false, PublicKeyParameter<RSAPublicKey>(cert.publicKey));
      ok = verifier.verifySignature(signed, RSASignature(signatureBytes));
    } else {
      return result(
        name,
        null,
        'Algoritmo di firma non supportato: $sigAlg',
        expiry,
      );
    }
    return result(
      name,
      ok,
      ok
          ? 'Firma e integrità del documento verificate'
          : 'Firma crittografica non valida',
      expiry,
    );
  } catch (_) {
    return result(
      name,
      null,
      'Verifica incompleta: struttura non supportata',
      expiry,
    );
  }
}

bool isSignedData(Uint8List bytes) {
  if (bytes.isEmpty || bytes.first != 0x30) return false;
  try {
    checkAsn1Limits(bytes);
    final p = ASN1Parser(bytes);
    final fields = (p.nextObject() as ASN1Sequence).elements!;
    return !p.hasNext() &&
        fields.length == 2 &&
        fields.first is ASN1ObjectIdentifier &&
        oid(fields.first) == '1.2.840.113549.1.7.2';
  } catch (_) {
    return false;
  }
}

String documentName(String name, Uint8List bytes) {
  if (name.isEmpty) name = 'documento';
  if (bytes.length >= 5 && String.fromCharCodes(bytes.take(5)) == '%PDF-') {
    if (!name.toLowerCase().endsWith('.pdf')) name += '.pdf';
  } else if (bytes.length >= 8 &&
      same(bytes.sublist(0, 8), [137, 80, 78, 71, 13, 10, 26, 10])) {
    if (!name.toLowerCase().endsWith('.png')) name += '.png';
  } else if (bytes.length >= 3 && same(bytes.sublist(0, 3), [255, 216, 255])) {
    if (!RegExp(r'\.jpe?g$', caseSensitive: false).hasMatch(name)) {
      name += '.jpg';
    }
  } else if (!name.contains('.')) {
    name += '.bin';
  }
  return name;
}

Map<String, Uint8List> certificateExtensions(X509 cert) {
  final tbs = (cert.asn1.elements!.first as ASN1Sequence).elements!;
  final out = <String, Uint8List>{};
  for (final item in tbs) {
    if (item.tag == 0xa3) {
      for (final ext in (children(item).single as ASN1Sequence).elements!) {
        final fields = (ext as ASN1Sequence).elements!;
        final id = oid(fields.first);
        if (out.containsKey(id)) {
          throw const FormatException('Estensione certificato duplicata');
        }
        out[id] = octets(fields.last);
      }
    }
  }
  return out;
}

bool matchesSignerCertificate(ASN1Object sid, X509 cert) {
  if (sid is ASN1Sequence) {
    final fields = sid.elements!;
    final issuer = cert.asn1Issuer.elements!.first;
    return fields.length == 2 &&
        fields[1] is ASN1Integer &&
        (fields[1] as ASN1Integer).integer == cert.serialNumber &&
        same(fields.first.encode(), issuer.encode());
  }
  if (sid.tag == 0x80) {
    final ski = certificateExtensions(cert)['2.5.29.14'];
    return ski != null &&
        same(sid.valueBytes!, octets(ASN1Parser(ski).nextObject()));
  }
  return false;
}

bool? verifyDetachedSignature(
  X509 cert,
  ASN1Sequence alg,
  Uint8List body,
  Uint8List signature,
) {
  final id = algorithm(alg);
  var digest =
      rsaHashes[id] ??
      const {
        '1.2.840.10045.4.1': 'SHA-1',
        '1.2.840.10045.4.3.2': 'SHA-256',
        '1.2.840.10045.4.3.3': 'SHA-384',
        '1.2.840.10045.4.3.4': 'SHA-512',
      }[id];
  if (id == '1.2.840.113549.1.1.10') {
    digest = 'SHA-1';
    if (alg.elements!.length == 2) {
      for (final p in (alg.elements![1] as ASN1Sequence).elements!) {
        if (p.tag == 0xa0) digest = hashes[algorithm(children(p).single)];
      }
    }
  }
  if (digest == null) return null;
  final digestOid = hashes.entries
      .firstWhere((entry) => entry.value == digest)
      .key;
  final signer = ASN1Sequence(
    elements: [
      ASN1Integer(BigInt.one),
      ASN1Parser(cert.asn1Issuer.encode()).nextObject(),
      ASN1Sequence(
        elements: [ASN1ObjectIdentifier.fromIdentifierString(digestOid)],
      ),
      alg,
      ASN1OctetString(octets: signature),
    ],
  );
  return verifySigner(
    ASN1Parser(signer.encode()).nextObject() as ASN1Sequence,
    [cert],
    body,
    '1.2.840.113549.1.7.1',
  ).integrity;
}

/// Bounded BER/DER preflight before the recursive ASN.1 library is invoked.
void checkAsn1Limits(Uint8List bytes) {
  var nodes = 0;
  int scan(int start, int end, int depth, bool indefinite) {
    if (depth > 32) {
      throw const FormatException('Struttura ASN.1 troppo profonda');
    }
    var offset = start;
    while (offset < end) {
      if (offset + 2 > end) throw const FormatException('ASN.1 troncato');
      final tag = bytes[offset++];
      final first = bytes[offset++];
      if (tag == 0 && first == 0) {
        if (!indefinite) {
          throw const FormatException('Terminatore ASN.1 inatteso');
        }
        return offset;
      }
      if (++nodes > 100000 || tag & 31 == 31) {
        throw const FormatException('Struttura ASN.1 non supportata');
      }
      if (first == 0x80) {
        if (tag & 32 == 0) {
          throw const FormatException('Lunghezza indefinita primitiva');
        }
        offset = scan(offset, end, depth + 1, true);
      } else {
        var length = first;
        if (first & 128 != 0) {
          final count = first & 127;
          if (count == 0 || count > 4 || offset + count > end) {
            throw const FormatException('Lunghezza ASN.1 non valida');
          }
          length = 0;
          for (var i = 0; i < count; i++) {
            length = (length << 8) | bytes[offset++];
          }
        }
        final next = offset + length;
        if (next > end) throw const FormatException('ASN.1 troncato');
        if (tag & 32 != 0) scan(offset, next, depth + 1, false);
        offset = next;
      }
    }
    if (indefinite) throw const FormatException('ASN.1 senza terminatore');
    return offset;
  }

  scan(0, bytes.length, 0, false);
}

int compareBytes(List<int> a, List<int> b) {
  for (var i = 0; i < a.length && i < b.length; i++) {
    if (a[i] != b[i]) return a[i] - b[i];
  }
  return a.length - b.length;
}

/// Signed attributes must use canonical DER, including SET ordering.
void requireDer(Uint8List bytes) {
  void scan(int start, int end) {
    var i = start;
    while (i < end) {
      final tlvStart = i;
      final tag = bytes[i++];
      final first = bytes[i++];
      if (first == 0x80) {
        throw const FormatException('Attributi BER non ammessi');
      }
      var length = first;
      if (first & 128 != 0) {
        final count = first & 127;
        if (bytes[i] == 0) {
          throw const FormatException('Lunghezza DER non minima');
        }
        length = 0;
        for (var j = 0; j < count; j++) {
          length = (length << 8) | bytes[i++];
        }
        if (length < 128) {
          throw const FormatException('Lunghezza DER non minima');
        }
      }
      final next = i + length;
      if (tag == 2 &&
          length > 1 &&
          ((bytes[i] == 0 && bytes[i + 1] & 128 == 0) ||
              (bytes[i] == 255 && bytes[i + 1] & 128 != 0))) {
        throw const FormatException('Intero DER non minimo');
      }
      if (tag == 1 && (length != 1 || ![0, 255].contains(bytes[i]))) {
        throw const FormatException('Booleano DER non valido');
      }
      if (tag == 0x31) {
        final fields = children(
          ASN1Object.fromBytes(Uint8List.sublistView(bytes, tlvStart, next)),
        );
        for (var j = 1; j < fields.length; j++) {
          if (compareBytes(
                fields[j - 1].encodedBytes!,
                fields[j].encodedBytes!,
              ) >
              0) {
            throw const FormatException('SET non in ordine DER');
          }
        }
      }
      if (tag & 32 != 0) scan(i, next);
      i = next;
    }
  }

  checkAsn1Limits(bytes);
  scan(0, bytes.length);
}
