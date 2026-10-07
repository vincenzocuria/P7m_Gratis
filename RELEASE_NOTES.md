## P7M Viewer PA 2.2.0

Verifica le firme PAdES, XAdES e ASiC insieme alle buste CAdES già supportate.

- **PAdES:** controlla la firma CMS sul ByteRange quando il SubFilter è `adbe.pkcs7.detached` o `ETSI.CAdES.detached` e il range copre l'intero PDF. Un indizio senza CMS resta non verificato.
- **XAdES / XML-DSig:** verifica firma, impronte dei riferimenti e, se presente, l'impronta del certificato. XPath, XSLT e riferimenti HTTP non sono accettati.
- **ASiC-S / ASiC-E:** apre il contenitore, verifica la firma CAdES detached o XAdES e, nel profilo E, le impronte del manifest.
- **CAdES detached (`.p7s`):** usa il documento omonimo nella stessa cartella oppure quello selezionato.

### Download

- **P7MViewer_Setup.exe**: installer per utente Windows. È il pacchetto che il controllo aggiornamenti scarica all'avvio.
- **P7MViewer_Portable_v2.2.0.zip**: estrarre tutta la cartella e avviare P7MViewer.exe.
- **SHA256SUMS.txt**: impronte dei pacchetti.

### Limiti espliciti

Qualifica eIDAS non verificata; revoca storica TSA e revoca degli intermedi non accertate. OCSP/CRL non supportati o non autenticabili restano sconosciuti. Non è una validazione completa eIDAS.

### Verifica

Test di PAdES, XAdES, ASiC-S/E e firme detached, insieme alla suite di estrazione, sicurezza e validazione. Compilazione Windows x64 pubblicata su GitHub Releases.
