## P7M Viewer PA 2.1.1

Apre i file con firme CAdES annidate, come `documento.pdf.p7m.p7m`, e mostra il documento interno.

- Scarta fino a 8 buste SignedData. Il PDF, l'XML, il testo o l'immagine arrivano all'anteprima invece di restare `application/octet-stream`.
- I firmatari di ogni busta entrano nel riepilogo. Il pannello continua a mostrare il primo, con gli altri nel tooltip.
- Oltre 8 buste l'apertura si ferma, senza presentare la busta residua come file sconosciuto.
- Il nome esportato perde tutti i suffissi `.p7m`.

### Download

- **P7MViewer_Setup.exe**: installer per utente Windows. È il pacchetto che il controllo aggiornamenti scarica all'avvio.
- **P7MViewer_Portable_v2.1.1.zip**: estrarre tutta la cartella e avviare P7MViewer.exe.
- **SHA256SUMS.txt**: impronte dei pacchetti.

### Limiti espliciti

Qualifica eIDAS non verificata; revoca storica TSA e revoca degli intermedi non accertate; PAdES solo rilevato. OCSP/CRL non supportati o non autenticabili restano sconosciuti. Non è una validazione completa eIDAS.

### Verifica

Test della doppia busta, del limite di 8 livelli e della suite di estrazione, sicurezza e validazione. Compilazione Windows x64 pubblicata su GitHub Releases.
