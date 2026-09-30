import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:pkcs7/pkcs7.dart' show X509;
import 'package:pointycastle/asn1.dart';

import 'p7m.dart';
import 'revocation.dart';

class CertificateAssessment {
  final bool? trusted;
  final String detail;
  final List<Uint8List> chain;
  final RevocationStatus revocation;
  final String revocationDetail;
  const CertificateAssessment({
    this.trusted,
    this.detail = 'Certificato non verificato',
    this.chain = const [],
    this.revocation = RevocationStatus.unknown,
    this.revocationDetail = 'Revoca non controllata: usa il controllo online',
  });
  CertificateAssessment withRevocation(
    RevocationStatus status,
    String message,
  ) => CertificateAssessment(
    trusted: trusted,
    detail: detail,
    chain: chain,
    revocation: status,
    revocationDetail: message,
  );
}

class CertificateService {
  static const _channel = MethodChannel('app.vcuria.p7m/files');
  static Future<CertificateAssessment> assess(
    SignerResult signer, {
    DateTime? at,
  }) async {
    final leaf = signer.certificate;
    if (leaf == null) {
      return const CertificateAssessment(
        detail: 'Certificato del firmatario assente',
      );
    }
    try {
      final cert = X509.fromDer(leaf);
      final now = at ?? DateTime.now();
      if (cert.notBefore.isAfter(now) || cert.notAfter.isBefore(now)) {
        return const CertificateAssessment(
          trusted: false,
          detail: 'Certificato scaduto o non ancora valido alla data odierna',
        );
      }
      final usage = certificateExtensions(cert)['2.5.29.15'];
      if (usage != null &&
          ((ASN1Parser(usage).nextObject() as ASN1BitString)
                      .stringValues!
                      .first &
                  0xc0) ==
              0) {
        return const CertificateAssessment(
          trusted: false,
          detail: 'Certificato non abilitato alla firma di documenti',
        );
      }
      final answer = await _channel
          .invokeMapMethod<String, dynamic>('verifyTrust', {
            'leaf': leaf,
            'certificates': signer.certificates,
            'time': now.millisecondsSinceEpoch,
          })
          .timeout(const Duration(seconds: 15));
      return CertificateAssessment(
        trusted: answer?['trusted'] as bool?,
        detail: answer?['detail'] as String? ?? 'Validazione non completata',
        chain: (answer?['chain'] as List? ?? []).cast<Uint8List>(),
      );
    } catch (_) {
      return const CertificateAssessment(
        detail: 'Verifica della catena non disponibile',
      );
    }
  }

  static Future<CertificateAssessment> revocation(
    SignerResult signer,
    CertificateAssessment current,
  ) async {
    try {
      if (signer.certificate == null) return current;
      var chain = current.chain.map(X509.fromDer).toList();
      if (chain.length < 2) {
        final leaf = X509.fromDer(signer.certificate!);
        final issuers = signer.certificates
            .map(X509.fromDer)
            .where((c) => !same(c.der, leaf.der) && directlyIssued(leaf, c))
            .toList();
        if (issuers.length != 1) {
          return current.withRevocation(
            RevocationStatus.unknown,
            'Emittente non disponibile: revoca non accertata',
          );
        }
        chain = [leaf, issuers.single];
      }
      final statuses = <RevocationStatus>[];
      final deadline = DateTime.now().add(const Duration(seconds: 35));
      for (var i = 0; i < chain.length - 1; i++) {
        statuses.add(await _check(chain[i], chain[i + 1], deadline));
        if (statuses.last == RevocationStatus.revoked) {
          return current.withRevocation(
            RevocationStatus.revoked,
            'Certificato del firmatario o della catena revocato: risposta firmata verificata',
          );
        }
      }
      final complete =
          current.trusted == true &&
          statuses.isNotEmpty &&
          statuses.every((s) => s == RevocationStatus.good);
      return current.withRevocation(
        complete ? RevocationStatus.good : RevocationStatus.unknown,
        complete
            ? 'Nessuna revoca rilevata nella catena: risposte firmate e aggiornate'
            : 'Revoca non completamente accertata: catena, rete o risposta non disponibile',
      );
    } catch (_) {
      return current.withRevocation(
        RevocationStatus.unknown,
        'Controllo di revoca non completato',
      );
    }
  }

  static Future<RevocationStatus> _check(
    X509 leaf,
    X509 issuer,
    DateTime deadline,
  ) async {
    for (final ocsp in [true, false]) {
      for (final url in endpoints(leaf, ocsp)) {
        if (DateTime.now().isAfter(deadline)) return RevocationStatus.unknown;
        try {
          final response = await fetchRevocation(
            url,
            ocsp ? ocspRequest(leaf, issuer) : null,
            deadline,
          );
          final status = await compute(validateRevocationResponse, (
            response,
            leaf.der,
            issuer.der,
            ocsp,
          ));
          if (status != RevocationStatus.unknown) return status;
        } catch (_) {
          /* Unknown remains unknown; try the next authenticated source. */
        }
      }
    }
    return RevocationStatus.unknown;
  }
}
