# P7M Gratis mobile — prima versione di sviluppo

App Flutter per Android e iOS. Nessun account, pubblicità, abbonamento o server che riceve i documenti. Estrazione e verifica crittografica avvengono sul dispositivo.

## Funzioni implementate

- Apertura dal selettore file di sistema; su Android anche da Apri con/Condividi per allegati CMS.
- Estrazione del documento, comprese fino a otto buste P7M annidate.
- Anteprima PDF, immagini, XML e testo; esportazione negli archivi di sistema e condivisione.
- Verifica di ogni firma RSA PKCS#1, RSA-PSS con parametri espliciti, ECDSA P-256/P-384/P-521; SHA-1/256/384/512.
- Controllo messageDigest e contentType, rifiuto degli attributi obbligatori mancanti o duplicati, associazione esatta del certificato per issuer e seriale.
- Limite di 50 MB, elaborazione crittografica in isolate per non bloccare l'interfaccia.

## Limiti della verifica e stato del prodotto

Questa è una versione di sviluppo, non ancora una release stabile. Una firma crittograficamente corretta **non** certifica l'identità o la validità legale del documento. La UI dichiara esplicitamente che catena di fiducia, revoca OCSP/CRL, marche temporali e qualificazione eIDAS non sono ancora controllate. Il certificato è incorporato e non viene considerato automaticamente attendibile. La scadenza mostrata è informativa.

Algoritmi e identificatori non supportati producono esito non verificato, mai un successo. Le firme separate richiedono l'originale e al momento vengono segnalate come non apribili. La verifica PAdES non è implementata. SHA-1 è verificabile per documenti storici, non è una raccomandazione per nuove firme. L'anteprima testuale è limitata ai primi 500 KB.

La APK debug è firmata con la chiave di sviluppo locale: serve per prove, non per pubblicazione su Google Play. Per una distribuzione Android stabile occorre una chiave di rilascio conservata dal proprietario. La build iOS e la prova su dispositivi richiedono macOS/Xcode; App Store/TestFlight richiedono anche l'account e i certificati Apple del proprietario. La gratuità per gli utenti è distinta dai costi degli account sviluppatore degli store.

## Sviluppo e verifica

Flutter 3.47.1 / Dart 3.13.1. Dipendenze fissate in pubspec.lock.

```sh
flutter pub get
flutter analyze
flutter test
flutter build apk --debug
# Solo su macOS:
flutter build ios --no-codesign
```

I campioni in test/fixtures sono sintetici. I test coprono firme RSA/ECDSA/PSS, più firmatari, buste annidate, contenuto e firma alterati, certificato errato, digest assente/duplicato, hash sconosciuto e buste senza firmatari. Non sostituiscono test su telefoni reali o un audit del motore.

## Lavoro necessario per la versione stabile

1. Validazione PKIX con trust store controllato, keyUsage/EKU e vincoli di catena; revoca autenticata con stato sconosciuto per errori di rete.
2. Verifica RFC 3161 e fonti TSL autentiche per qualificazione eIDAS.
3. Prove end-to-end su Android e iOS: allegati, Files/Drive, export, condivisione, PDF grandi, file ostili, rotazione e accessibilità.
4. Icona definitiva, localizzazione, chiavi di rilascio, privacy e distribuzione sugli store.

La libreria pkcs7 viene usata soltanto per leggere metadati X.509. Le sue funzioni verify/verifyChain non vengono utilizzate; il motore verifica esplicitamente firme e attributi con PointyCastle.
