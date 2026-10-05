# P7M Viewer PA 2.1.1

Viewer Windows gratuito per estrarre e consultare documenti CAdES/PKCS#7, PDF, XML, immagini e testo. Sviluppato da Vincenzo Curia.

## Verifiche e significato dei risultati

- **Integrità crittografica:** verifica firma CMS e digest del contenuto, attributi obbligatori e corrispondenza contentType. Supporta RSA PKCS#1 v1.5, RSA-PSS, ECDSA e DSA con digest SHA-1/256/384/512; gli algoritmi sconosciuti non hanno fallback SHA-256.
- **Certificato del firmatario:** corrispondenza di emittente e seriale o subjectKeyIdentifier. Nessun ripiego sul primo certificato.
- **Catena locale:** validazione PKIX tramite pyhanko-certvalidator e radici del sistema, con intermedi presenti nella busta. Non scarica intermedi AIA e non rappresenta un giudizio eIDAS. La revoca degli intermedi non è accertata.
- **Revoca del certificato firmatario:** richieste OCSP reali o CRL complete e dirette. Verifica firma della risposta, autorizzazione del responder, identificativo del certificato e freschezza. Errori, assenza di nextUpdate, CRL parziali/indirette, responder delegati senza OCSP no-check e formati non supportati restano **non verificati**. La raggiungibilità HTTP non indica assenza di revoca. Gli endpoint devono essere pubblici HTTP(S), senza redirect, sulle porte 80/443.
- **Marca RFC 3161:** verifica firma CMS del token, impronta della firma originale, EKU esclusivo TSA e catena alla data della marca. La revoca storica TSA non è disponibile: la validità complessiva e la prova di data certa restano **non accertate**, anche se firma e impronta sono corrette.
- **Qualifica eIDAS:** sempre **non verificata** finché non è disponibile una lista fiduciaria autenticata con storico del servizio. Nomi come Aruba, InfoCert o Comune non costituiscono prova.
- **PDF/PAdES:** rileva indizi di firma nel PDF, ma non valida le firme PAdES.
- **Documenti non firmati o recuperati tramite scansione:** estraibili e consultabili, senza esiti positivi di verifica.

Il riepilogo considera tutti i firmatari. Il pannello mostra il primo; il tooltip del nome riporta gli esiti di tutti. Un firmatario con firma errata o certificato revocato rende negativo il riepilogo. L'integrità matematica corretta non equivale a qualificazione o validità complessiva della firma.

## Interfaccia

Anteprima PDF QtPDF, XML formattato e ad albero, immagini e testo; esportazione, stampa, temi chiaro/scuro/automatico, file recenti e associazione Windows .p7m. Decodifica e rete avvengono in un worker: la finestra resta reattiva.

Le firme detached .p7s prive di contenuto richiedono il documento originale e non vengono validate da questo viewer. Il recupero raw è un'estrazione di emergenza, non prova che i byte siano l'originale firmato.

## Installazione da sorgenti

Windows 10/11 x64, Python 3.12:

```powershell
python -m pip install -r requirements.txt
python main.py
```

## Test e build

```powershell
python -m unittest discover -v
python -m pip install pyinstaller==6.22.2
python build_exe.py
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' installer.iss
```

L'applicazione è in `dist/P7MViewer/P7MViewer.exe`, il setup in `dist/P7MViewer_Setup.exe`. Il portable è uno ZIP dell'intera cartella `dist/P7MViewer`, non del solo exe. Non è necessario installare Python sul PC destinatario.

## Aggiornamenti

Controllo tramite GitHub Releases, con download del solo asset `P7MViewer_Setup.exe`. Il SHA-256 fornito dall'API GitHub viene verificato prima dell'esecuzione. Asset senza digest e versioni prerelease/malformate non vengono installati. Il digest protegge da corruzione o sostituzione nel download; non sostituisce una firma Authenticode del publisher.

La 2.1.1 apre le buste CAdES annidate (`.p7m.p7m`) fino al documento interno. All'avvio l'app installata confronta la propria versione con GitHub Releases e, se trova una stabile più recente con `P7MViewer_Setup.exe`, propone l'installer. La 2.1.0 resta la release che ha tolto gli esiti positivi non dimostrati.

## Ambito

Strumento informativo. I risultati indicano esattamente i controlli eseguiti e quelli non disponibili; non costituiscono una validazione completa eIDAS/CAdES/PAdES o una valutazione giuridica.

Repository: https://github.com/vincenzocuria/P7m_Gratis
