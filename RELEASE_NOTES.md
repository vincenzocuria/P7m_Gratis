## P7M Viewer PA 2.1.0

Release correttiva di sicurezza per Windows x64. Aggiornamento consigliato a tutte le installazioni precedenti.

- Eliminati gli esiti positivi predefiniti: documenti non firmati, firme PAdES solo rilevate e recuperi raw restano non verificati.
- Corretto il crash all'import del modulo di revoca.
- Verifica CMS con attributi obbligatori, contentType, digest supportati e parametri RSA-PSS.
- Abbinamento esatto del certificato e validazione della catena locale.
- Revoca OCSP/CRL reale con autenticazione, freschezza e controlli del certificato; niente equivalenza tra HTTP 200 e certificato non revocato.
- Marche RFC 3161: verifica firma TSA e collegamento alla firma originale.
- Qualifica eIDAS e revoca storica TSA esplicitamente non accertate: nessuna deduzione da nomi di enti o CA.
- Riepilogo su tutti i firmatari; decodifica in background senza bloccare la finestra.
- Aggiornamenti limitati all'installer ufficiale con controllo SHA-256 prima dell'avvio.

### Download

- **P7MViewer_Setup.exe**: installer per utente Windows.
- **P7MViewer_Portable_v2.1.0.zip**: estrarre tutta la cartella e avviare P7MViewer.exe.
- **SHA256SUMS.txt**: impronte dei pacchetti.

### Limiti espliciti

Qualifica eIDAS non verificata; revoca storica TSA e revoca degli intermedi non accertate; PAdES solo rilevato. OCSP/CRL non supportati o non autenticabili restano sconosciuti. Non è una validazione completa eIDAS.

### Verifica

Test automatici di estrazione, manipolazione delle firme, certificati falsi, OCSP/CRL validi/scaduti/falsificati, marche temporali, riepilogo multifirma, reattività Qt e integrità degli aggiornamenti. Compilazione Windows x64 e prova del pacchetto compilato.
