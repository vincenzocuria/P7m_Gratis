## P7M Viewer PA 2.1.2

Il nome proposto in esportazione riceve l'estensione del contenuto anche quando il nome del file contiene punti.

- Nomi come `Contratto n. 12.p7m` o `05.10.2026.p7m` diventano `Contratto n. 12.pdf` e `05.10.2026.xml` quando il tipo è riconosciuto.
- Se il nome termina già con un'estensione nota (`.pdf`, `.xml`, `.png` e le altre gestite) non viene duplicata.
- I suffissi `.p7m` finali continuano a essere rimossi, anche se ripetuti.

### Download

- **P7MViewer_Setup.exe**: installer per utente Windows. È il pacchetto che il controllo aggiornamenti scarica all'avvio.
- **P7MViewer_Portable_v2.1.2.zip**: estrarre tutta la cartella e avviare P7MViewer.exe.
- **SHA256SUMS.txt**: impronte dei pacchetti.

### Limiti espliciti

Qualifica eIDAS non verificata; revoca storica TSA e revoca degli intermedi non accertate; PAdES solo rilevato. OCSP/CRL non supportati o non autenticabili restano sconosciuti. Non è una validazione completa eIDAS.

### Verifica

Test sui nomi con punti interni, date, estensione già presente e nome semplice, insieme alla suite di estrazione, sicurezza e validazione. Compilazione Windows x64 pubblicata su GitHub Releases.
