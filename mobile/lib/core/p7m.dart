import 'dart:typed_data';

import 'package:pkcs7/pkcs7.dart' show X509;
import 'package:pointycastle/export.dart';
import 'package:pointycastle/asn1.dart';

class SignerResult {
  final String name, detail;
  final bool? integrity;
  final DateTime? expires;
  const SignerResult(this.name, this.integrity, this.detail, [this.expires]);
}

class P7mDocument {
  final Uint8List bytes;
  final String name;
  final List<SignerResult> signers;
  const P7mDocument(this.bytes, this.name, this.signers);
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
    if (!name.toLowerCase().endsWith('.p7m')) {
      return P7mDocument(bytes, name, results);
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
  try {
    final s = signer.elements!;
    final sid = s[1];
    // Match BOTH issuer and serial. Never select the first certificate.
    final matches = certs
        .where(
          (c) =>
              sid is ASN1Sequence && same(sid.encode(), c.asn1Issuer.encode()),
        )
        .toList();
    if (matches.length != 1) {
      return SignerResult(
        name,
        null,
        'Certificato assente o identificatore non supportato',
      );
    }
    final cert = matches.single;
    name = cert.subject.map((e) => '${e.value}').join(', ');
    expiry = cert.notAfter;
    final hashName = hashes[algorithm(s[2])];
    if (hashName == null) {
      return SignerResult(name, null, 'Algoritmo hash non supportato', expiry);
    }
    var index = 3;
    var signed = payload;
    if (s[index].tag == 0xa0) {
      final attrs = s[index++];
      final digests = <ASN1Object>[];
      final types = <ASN1Object>[];
      var digestCount = 0;
      var typeCount = 0;
      for (final a in children(attrs)) {
        final fields = (a as ASN1Sequence).elements!;
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
        return SignerResult(
          name,
          false,
          'Digest o attributi firmati non validi',
          expiry,
        );
      }
      signed = Uint8List.fromList(attrs.encodedBytes!);
      if (signed[1] == 0x80) {
        return SignerResult(name, null, 'Attributi BER non supportati', expiry);
      }
      signed[0] = 0x31;
    } else if (contentType != '1.2.840.113549.1.7.1') {
      return SignerResult(
        name,
        false,
        'Attributi firmati obbligatori assenti',
        expiry,
      );
    }
    final sigAlgorithm = s[index++] as ASN1Sequence;
    final sigAlg = algorithm(sigAlgorithm);
    final signatureBytes = octets(s[index]);
    bool ok;
    const ecHashes = {
      '1.2.840.10045.4.1': 'SHA-1',
      '1.2.840.10045.4.3.2': 'SHA-256',
      '1.2.840.10045.4.3.3': 'SHA-384',
      '1.2.840.10045.4.3.4': 'SHA-512',
    };
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
        return SignerResult(name, null, 'Curva EC non supportata', expiry);
      }
      final domain = ECDomainParameters(curve);
      final publicKey = ECPublicKey(
        domain.curve.decodePoint(cert.publicKeyBytes),
        domain,
      );
      final sigParser = ASN1Parser(signatureBytes);
      final integers = (sigParser.nextObject() as ASN1Sequence).elements!;
      if (sigParser.hasNext() || integers.length != 2) {
        return SignerResult(name, false, 'Firma EC malformata', expiry);
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
        return SignerResult(name, null, 'Parametri RSA-PSS assenti', expiry);
      }
      for (final p in (sigAlgorithm.elements![1] as ASN1Sequence).elements!) {
        if (!seen.add(p.tag!)) {
          return SignerResult(
            name,
            false,
            'Parametri RSA-PSS duplicati',
            expiry,
          );
        }
        final value = children(p).single;
        switch (p.tag) {
          case 0xa0:
            pssHash = hashes[algorithm(value)] ?? '';
          case 0xa1:
            final mgf = (value as ASN1Sequence).elements!;
            if (oid(mgf.first) != '1.2.840.113549.1.1.8') {
              return SignerResult(name, null, 'MGF non supportata', expiry);
            }
            mgfHash = hashes[algorithm(mgf[1])] ?? '';
          case 0xa2:
            saltLength = (value as ASN1Integer).integer!.toInt();
          case 0xa3:
            trailer = (value as ASN1Integer).integer!.toInt();
          default:
            return SignerResult(
              name,
              false,
              'Parametri RSA-PSS sconosciuti',
              expiry,
            );
        }
      }
      if (pssHash != hashName ||
          mgfHash.isEmpty ||
          saltLength < 0 ||
          saltLength > 512 ||
          trailer != 1) {
        return SignerResult(
          name,
          false,
          'Parametri RSA-PSS incompatibili',
          expiry,
        );
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
      return SignerResult(
        name,
        null,
        'Algoritmo di firma non supportato: $sigAlg',
        expiry,
      );
    }
    return SignerResult(
      name,
      ok,
      ok
          ? 'Firma e integrità del documento verificate'
          : 'Firma crittografica non valida',
      expiry,
    );
  } catch (_) {
    return SignerResult(
      name,
      null,
      'Verifica incompleta: struttura non supportata',
      expiry,
    );
  }
}
