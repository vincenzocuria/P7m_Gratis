# P7M Web Tool - Phase 1

Strumento web gratuito per aprire file .p7m e convertire fatture elettroniche in PDF ed Excel.

## Funzionalità (Phase 1)

- ✅ Upload singolo file .p7m (max 10 MB)
- ✅ Upload ZIP con fino a 20 file .p7m (max 50 MB)
- ✅ Estrazione contenuto e verifica firma digitale CAdES
- ✅ Conversione fatture elettroniche XML in PDF leggibili
- ✅ Generazione Excel riepilogativo per batch di fatture
- ✅ Rate limiting e protezione anti-abuso
- ✅ Privacy: nessun file salvato, elaborazione in memoria
- ✅ SEO: pagine server-rendered, sitemap.xml, robots.txt
- ✅ Pagine: Home, Privacy, FAQ, Download
- ✅ Cloudflare Turnstile (opzionale, via env var)

**Phase 1 = NO pagamenti, NO account utente, NO Stripe, NO invio email**

## Architettura

- **Backend**: FastAPI + Python 3.12
- **Frontend**: HTML/CSS/JavaScript vanilla (nessun framework)
- **Elaborazione P7M**: Riuso del decoder esistente (`p7m_decoder.py` e `services/`)
- **PDF**: WeasyPrint
- **Excel**: openpyxl
- **Deployment**: Dockerfile per Coolify

## Requisiti

- Python 3.12+
- Dipendenze di sistema per WeasyPrint: libpango, libcairo, libgdk-pixbuf

## Setup locale

```bash
cd web

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

export PORT=8000
export BASE_URL=http://localhost:8000

python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Apri http://localhost:8000

## Test

```bash
cd web
python -m pytest app/tests/ -v

# Oppure
python -m unittest discover -s app/tests -v
```

## Variabili d'ambiente

| Variabile | Descrizione | Default | Obbligatorio |
|-----------|-------------|---------|--------------|
| `PORT` | Porta HTTP | `8000` | No |
| `BASE_URL` | URL base del sito (per sitemap) | `https://p7m.vcuria.app` | Sì (prod) |
| `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile secret | - | No |
| `TURNSTILE_SITE_KEY` | Cloudflare Turnstile site key | - | No |

Se `TURNSTILE_SECRET_KEY` non è impostato, la verifica Turnstile è disabilitata (utile per sviluppo locale).

## Deploy su Coolify

1. **Crea un nuovo servizio su Coolify**:
   - Tipo: Docker
   - Repository: `https://github.com/vincenzocuria/P7m_Gratis`
   - Branch: `main` (o il tuo branch)
   - Dockerfile path: `web/Dockerfile`
   - Build context: `/` (root del repository)

2. **Configura le variabili d'ambiente**:
   ```
   PORT=8000
   BASE_URL=https://p7m.vcuria.app
   TURNSTILE_SECRET_KEY=<your-secret>
   TURNSTILE_SITE_KEY=<your-site-key>
   ```

3. **Configura il dominio**:
   - Aggiungi `p7m.vcuria.app` al servizio
   - Assicurati che il DNS punti al server Coolify

4. **Deploy**:
   - Coolify builderà automaticamente il container e lo avvierà sulla porta configurata
   - Healthcheck endpoint: `/health`

## Limiti Phase 1 (gratuiti)

- File singolo: max 10 MB
- ZIP: max 50 MB totali
- Batch: max 20 file per upload
- Rate limit: ~20 upload/ora per IP

Per batch più grandi, consigliare l'app desktop P7M Viewer.

## Privacy

- **Nessun file salvato**: elaborazione in RAM, cancellazione immediata
- **Log tecnici anonimi**: solo IP (per rate limiting), dimensione, esito, timestamp
- **Retention log**: max 7 giorni
- **Server**: UE (Coolify self-hosted)
- **Sub-responsabili**: Cloudflare (se proxy attivo)

Vedi `app/templates/privacy.html` per l'informativa completa.

## SEO

Pagine ottimizzate per query italiane:
- "aprire file p7m online"
- "convertire fattura p7m in pdf"
- "fatture xml p7m in excel"
- "zip fatture agenzia entrate in pdf"
- "verificare firma digitale p7m"

Meta tag, sitemap.xml, robots.txt, FAQ strutturate.

## Sicurezza

- HTTPS (Coolify/Cloudflare)
- Parser XML sicuro (no entità esterne, no network)
- Limiti dimensione file e profondità annidamento (anti zip-bomb)
- Rate limiting per IP
- Cloudflare Turnstile anti-bot
- Container senza privilegi

## Struttura

```
web/
├── app/
│   ├── main.py              # FastAPI app
│   ├── templates/           # HTML Jinja2
│   │   ├── index.html
│   │   ├── privacy.html
│   │   ├── faq.html
│   │   └── download.html
│   ├── static/
│   │   ├── css/style.css
│   │   └── js/app.js
│   ├── services/
│   │   ├── p7m_processor.py    # Wrapper per decoder esistente
│   │   ├── fattura_parser.py   # Parser FatturaPA XML
│   │   ├── pdf_generator.py    # PDF da fatture
│   │   ├── excel_generator.py  # Excel riepilogativo
│   │   └── rate_limiter.py     # Rate limiting
│   └── tests/
│       ├── test_p7m_processor.py
│       ├── test_fattura_parser.py
│       └── test_rate_limiter.py
├── Dockerfile
├── requirements.txt
└── README.md
```

## TODO Phase 2 (se richiesto)

- [ ] Supabase auth (magic link)
- [ ] Sistema crediti e tabelle su Supabase
- [ ] Stripe Checkout + webhook
- [ ] Email con Resend (magic link, ricevute)
- [ ] Download batch: ZIP di PDF rinominati + Excel
- [ ] Limite batch aumentato per utenti paganti

**Phase 2 si attiverà solo se Phase 1 riceve traffico misurabile.**

## Supporto

Per bug, domande o suggerimenti:
- Email: curiavincenzo86@gmail.com
- GitHub Issues: https://github.com/vincenzocuria/P7m_Gratis/issues

## Licenza

Stesso progetto P7M Viewer. Vedi LICENSE nel repository principale.
