## P7M Viewer PA 2.3.0 - Documenti Word

Apre e mostra i documenti Word firmati, compresi i vecchi `.doc` (Word 97-2003).

- **Word 97-2003 (`.doc`):** il documento estratto viene riconosciuto e salvato con l'estensione `.doc` e non più come `.bin`. Il testo è mostrato direttamente nell'app.
- **Word `.docx` e OpenDocument `.odt`:** anteprima del testo nell'app.
- **Altri formati Office:** `.xls`, `.ppt`, `.rtf`, `.ods` e `.odp` vengono riconosciuti e salvati con l'estensione corretta.
- **Apri con app predefinita:** nuovo pulsante nella barra in alto, sempre disponibile. Apre il documento estratto con il programma installato sul PC (Word, LibreOffice, Acrobat…) per vedere impaginazione e immagini.

### Download

- **P7MViewer_Setup.exe**: installer per utente Windows. È il pacchetto che il controllo aggiornamenti scarica all'avvio.
- **P7MViewer_Portable_v2.3.0.zip**: estrarre tutta la cartella e avviare P7MViewer.exe.
- **SHA256SUMS.txt**: impronte dei pacchetti.

### Limiti espliciti

L'anteprima mostra solo il testo: impaginazione, immagini e oggetti incorporati restano visibili con il programma predefinito. Documenti Word cifrati con password non hanno anteprima. Qualifica eIDAS non verificata; non è una validazione completa eIDAS.

### Verifica

Test del lettore `.doc` (testo compresso e Unicode, codici di campo, mini stream, file danneggiati o cifrati), di `.docx`, `.odt` e del riconoscimento dei formati Office, insieme alla suite di firme, sicurezza e validazione già esistente.
