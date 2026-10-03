# P7M Gratis mobile 1.2.0

App gratuita per Android e iOS: apre buste CAdES/PKCS#7, estrae il documento e mostra i risultati delle verifiche. Non richiede account, abbonamenti o pubblicità. I documenti vengono elaborati sul dispositivo.

## Uso

1. Premi **Apri un P7M o PDF** o apri/condividi un allegato con P7M Gratis.
2. Consulta il documento estratto: PDF, immagini, XML o testo. Altri formati possono essere salvati e aperti con l'app adatta.
3. Nella scheda **Firme**, leggi separatamente integrità, certificato, marca temporale e revoca.
4. Premi **Controlla revoca online** per contattare gli emittenti dei certificati. Il documento non viene caricato.
5. Usa **Salva** o **Condividi** per esportare il contenuto originale estratto.

I PDF semplici si aprono direttamente nell’anteprima: la UI indica che non sono buste P7M e non verifica eventuali firme PAdES. Dal pulsante **?** si trovano lo sviluppatore Vincenzo Curia, [vcuria.app](https://vcuria.app/) e il download della versione Windows.

## Verifiche

- Verifica ogni firmatario: RSA PKCS#1, RSA-PSS con parametri espliciti, ECDSA P-256/P-384/P-521; SHA-1/256/384/512. SHA-1 viene riconosciuto per documenti storici, non consigliato per nuove firme.
- Controlla digest del contenuto, contentType, unicità degli attributi firmati e codifica DER. Abbina il certificato per issuer+seriale o SKI, senza scegliere arbitrariamente il primo.
- Valida la catena PKIX usando le radici del dispositivo e gli intermedi inclusi nella busta: date, firme della catena, vincoli e keyUsage. I certificati incorporati non diventano radici fidate. Non scarica intermedi AIA.
- Controlla revoca con OCSP autenticato o CRL complete e dirette: firma della risposta, autorizzazione del responder, CertID, thisUpdate e nextUpdate. Controlla anche gli intermedi della catena disponibile. Errori, rete assente o risposte non supportate restano **non accertati**.
- Per i token RFC 3161 controlla firma CMS, impronta della firma originale, EKU critico esclusivo TSA, validità del certificato e catena alla data della marca. La revoca storica TSA non è disponibile: la validità storica complessiva resta **non accertata**.

Un segno positivo compare solo con integrità, catena e revoca accertate. Questi controlli non equivalgono a una certificazione legale: **qualificazione eIDAS non accertata**, perché non è integrata una TSL autenticata e storicizzata. Un certificato legittimo può non essere presente nel trust store del telefono; la UI indica esplicitamente la mancata fiducia locale. La scadenza odierna non dimostra da sola che una firma storica fosse invalida.

## Compatibilità e limiti

- Android 7/API 24 o successivo; iOS 15 o successivo.
- Limite 50 MB; fino a 8 buste annidate, riconosciute dal contenuto anziché dal nome del file.
- Elaborazione crittografica in isolate, ASN.1 con limiti di profondità e complessità; allegati ricevuti durante l'elaborazione vengono gestiti in coda (il più recente resta in attesa).
- Anteprima testuale fino a 500 KB. I byte esportati non vengono troncati.
- Firme separate senza originale e verifica PAdES non supportate. Algoritmi non supportati non producono un esito positivo.
- CRL delta, indirette o parziali e responder delegati senza OCSP no-check restano non accertati.
- Endpoint pubblici HTTP(S), porte 80/443, senza redirect. DNS risolto e verificato prima della connessione; indirizzi locali/privati rifiutati. Le risposte sono limitate a 16 MB e le richieste hanno timeout.

## Build e firma

Flutter 3.47.1 / Dart 3.13.1; dipendenze fissate in pubspec.lock.

```sh
flutter pub get
flutter analyze
flutter test
flutter build apk --release
flutter build appbundle --release
# macOS:
flutter build ios --no-codesign
```

Per Android release configura `android/key.properties`, escluso dal repository, con storeFile, storePassword, keyAlias e keyPassword. La build di rilascio non usa chiavi debug. Conserva la chiave privata: deve firmare anche gli aggiornamenti. Il backup è consegnato separatamente al proprietario e non fa parte delle release pubbliche.

La pipeline verifica Android e compila iOS su macOS. L'archivio iOS senza firma è un prodotto della compilazione, **non installabile su iPhone**: per IPA/TestFlight/App Store servono account, certificati e provisioning Apple del proprietario. Le build riuscite e i test automatici non sostituiscono la prova su tutti i dispositivi reali.

## Test

La suite copre firme integre e alterate, RSA/ECDSA/PSS, identificatori dei firmatari, attributi mancanti/duplicati, buste annidate con nomi errati, input ASN.1 ostile, OCSP e CRL autentici/revocati/scaduti/manomessi, responder delegati, timestamp con impronta errata, coda allegati e schermi piccoli. Il test Java usa l'esatto validatore PKIX Android con radici sintetiche iniettate e controlla anche firme di certificato alterate e date invalide.

I campioni sono sintetici, senza dati personali o chiavi private. `tool/generate_validation_fixtures.py` permette di rigenerare i campioni di certificati/revoca/marche con le dipendenze Python del repository. La libreria pkcs7 viene usata per leggere X.509; le sue funzioni verify/verifyChain non vengono chiamate.

## Guida, privacy e assistenza

Il menu **?** include guida facoltativa, informativa completa offline, informativa pubblica, support@vcuria.app, versione e licenze open source. Il controllo online richiede conferma esplicita dopo la descrizione dei dati trasmessi.

Le esportazioni usano copie con nomi limitati a 180 byte in una directory privata dedicata. Le copie gestite più vecchie di 24 ore vengono eliminate al successivo avvio; non esiste un timer in background. Il comando di chiusura/pulizia invalida le verifiche in corso, chiude l’anteprima e rimuove i temporanei gestiti senza cancellare originali o file salvati. Durante esportazione o verifica online la pulizia è disabilitata. Su Android la cache del selettore è pulita dopo la lettura; su iOS la pulizia del selettore avviene solo con il comando esplicito, perché il plugin svuota la directory temporanea privata.

Informativa pubblica: https://vincenzocuria.github.io/P7m_Gratis/privacy.html
