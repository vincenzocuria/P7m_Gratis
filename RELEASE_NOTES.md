## P7M Viewer PA 2.3.1 - Correzione documenti Word

Correzione di sicurezza per l'anteprima dei documenti Word 97-2003 (`.doc`) introdotta nella 2.3.0.

- **`.doc` malformati:** un documento `.doc` danneggiato o costruito ad arte dentro un `.p7m` poteva bloccare il programma durante l'anteprima. Ora il file viene rifiutato: il documento resta estraibile e apribile con il programma predefinito, ma senza anteprima del testo.

### Download

- **P7MViewer_Setup.exe**: installer per utente Windows. È il pacchetto che il controllo aggiornamenti scarica all'avvio.
- **P7MViewer_Portable_v2.3.1.zip**: estrarre tutta la cartella e avviare P7MViewer.exe.
- **SHA256SUMS.txt**: impronte dei pacchetti.

### Limiti espliciti

L'anteprima mostra solo il testo: impaginazione, immagini e oggetti incorporati restano visibili con il programma predefinito. Documenti Word cifrati con password non hanno anteprima. Qualifica eIDAS non verificata; non è una validazione completa eIDAS.

### Verifica

Nuovo test di regressione con un `.doc` malformato, che deve terminare senza anteprima, insieme alla suite completa di documenti Office, firme, sicurezza e validazione.
