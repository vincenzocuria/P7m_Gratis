# 🛡️ P7M Viewer PA

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt6-green.svg)](https://pypi.org/project/PySide6/)
[![Design](https://img.shields.io/badge/Design-Material%203%20Expressive-purple.svg)](#)
[![Author](https://img.shields.io/badge/Author-Vincenzo%20Curia%20(vcuria.app)-0055ff.svg)](https://vcuria.app)
[![License](https://img.shields.io/badge/license-MIT-brightgreen.svg)](LICENSE)

**P7M Viewer PA v2.0** è un'applicazione desktop moderna, gratuita e ad altissime prestazioni per la visualizzazione immediata, la validazione crittografica eIDAS ed il controllo dei file firmati digitalmente (**`.p7m`** / **`.p7s`**).

Sviluppato da **[Vincenzo Curia](https://vcuria.app)**, offre un'interfaccia utente curata nei dettagli con il linguaggio **Material Design 3 Expressive**, consentendo a cittadini, professionisti e funzionari della Pubblica Amministrazione di verificare ed estrarre in un solo clic il contenuto di documenti firmati CAdES / PKCS#7 (PDF, Fatture Elettroniche XML, immagini e documenti di testo).

---

## ✨ Caratteristiche Principali (v2.0.0 Major Update)

- 🔐 **Motore Nativo di Validazione Crittografica (eIDAS & ETSI)**:
  - **Verifica Matematica della Firma**: Calcolo ed accertamento dell'impronta SHA-256/SHA-512 del payload rispetto all'attributo `messageDigest` e verifica della firma asimmetrica RSA / ECDSA sui `signedAttributes`.
  - **Accredito QTSP (eIDAS / AgID)**: Controllo dell'emittente del certificato rispetto ai Prestatori di Servizi Fiduciari Qualificati accreditati (InfoCert, Aruba, Namirial, Poste Italiane, Actalis, Intesa, ecc.).
  - **Stato di Revoca (AIA / OCSP / CRL)**: Verifica online degli endpoint OCSP e CRL con gestione offline aggraziata.
  - **Marca Temporale (CAdES-T / RFC 3161)**: Estrazione dei token di attestazione temporale e verifica della firma della TSA per la data e ora certa.
- 📄 **Estrazione Istantanea Busta CAdES / PKCS#7**: Decodifica nativa in memoria dei file `.p7m` con recupero immediato del payload e visualizzazione dei metadati del firmatario (Nome, Codice Fiscale, Organizzazione, CA emittente, periodo di validità).
- 🎨 **Material Design 3 Expressive UI**: Interfaccia reattiva ed elegante con supporto completo ai temi **Chiaro**, **Scuro** e **Automatico (di Sistema)**.
- 📐 **Visualizzatore PDF Vettoriale Integrato**: Integrazione con QtPDF per anteprime di qualità nativa, zoom regolabile, adattamento larghezza e stampa diretta del documento.
- 🌳 **Visualizzatore XML Formattato & Albero Strutturato**: Perfetto per le **Fatture Elettroniche PA (FPA12 / FPR12)** e determine. Include syntax highlighting colorato ed un albero esplorabile di tutti i tag ed attributi XML.
- 🔄 **Controllo Automatico e Manuale degli Aggiornamenti**: Integrazione automatica tramite background thread con l'API GitHub Releases di [`vincenzocuria/P7m_Gratis`](https://github.com/vincenzocuria/P7m_Gratis), per notificare la presenza di nuove versioni ed installer.
- 🕒 **Dashboard File Recenti**: Schermata di benvenuto interattiva con zona **Drag & Drop** e scorciatoie per riaprire rapidamente gli ultimi documenti consultati.
- 🔗 **Associazione File Windows (.p7m)**: Funzione integrata a menu per registrare l'estensione nel registro di Windows ed aprire i file con un doppio clic da Esplora File.
- 🖨️ **Stampa Documento Integrata**: Supporto alla stampa diretta per documenti PDF, XML, immagini e testo.

---

## 🚀 Guida all'Uso e Requisiti

### Requisiti
- **Windows 10 / 11**
- **Python 3.10+** (in caso di esecuzione da codice sorgente)

### Esecuzione da Codice Sorgente

1. **Clona il repository**:
   ```bash
   git clone https://github.com/vincenzocuria/P7m_Gratis.git
   cd P7m_Gratis
   ```

2. **Installa le dipendenze**:
   ```bash
   pip install PySide6 asn1crypto pycryptodome cryptography
   ```

3. **Avvia l'applicazione**:
   ```bash
   python main.py
   ```

---

## 📦 Compilazione ed Installer Executable (.exe)

Il progetto include gli script pronti all'uso per generare l'eseguibile standalone ed il pacchetto di installazione Windows:

1. **Generazione pacchetto PyInstaller**:
   ```bash
   python build_exe.py
   ```
   *L'eseguibile verrà generato nella cartella `dist/P7MViewer.exe`.*

2. **Creazione dell'Installer Windows (InnoSetup)**:
   Assicurati che **Inno Setup 6** sia installato e compila il file di setup:
   ```bash
   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
   ```
   *L'installer `P7MViewer_Setup_v2.0.exe` verrà salvato nella cartella `dist/`.*

---

## 🔄 Sistema di Aggiornamento Automatico

P7M Viewer PA verifica automaticamente la presenza di nuove versioni all'avvio. Puoi anche effettuare la verifica manuale in qualsiasi momento dal menu:
**`?` ➔ `🔄 Controlla Aggiornamenti...`**

Qualora sia disponibile una nuova versione su GitHub, l'applicazione fornirà il link diretto per scaricare l'installer aggiornato.

---

## ⚖️ Avviso di Non Validità Legale

P7M Viewer PA estrae ed esamina la struttura sintattica del contenitore PKCS#7 / CAdES e ne mostra il contenuto originale ed i metadati del certificato.

**Nota Legale**: Questo software è uno **strumento ad uso puramente informativo ed estrattivo**. NON possiede valore di giudizio legale formale ai sensi del CAD (Codice dell'Amministrazione Digitale), in quanto non interroga in tempo reale i servizi di verifica della revoca (CRL / OCSP) delle Autorità di Certificazione (CA) accreditate né le marche temporali per la validità con valore di prova legale. Per verifiche formali con valore legale si raccomanda l'uso di software accreditati AgID (es. ArubaSign, Dike, FirmaOK).

---

## 👨‍💻 Crediti ed Autore

Sviluppato con ❤️ da **Vincenzo Curia**.

- 🌐 **Sito Ufficiale**: [vcuria.app](https://vcuria.app)
- 🐙 **GitHub Repository**: [vincenzocuria/P7m_Gratis](https://github.com/vincenzocuria/P7m_Gratis)

---

## 📄 Licenza

Questo progetto è rilasciato sotto Licenza **MIT**. Consulta il file `LICENSE` per maggiori informazioni.
