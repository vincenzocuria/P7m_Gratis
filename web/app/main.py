import os
import io
import zipfile
import tempfile
import hashlib
import uuid
import pickle
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import aiofiles

from app.services.p7m_processor import P7MProcessor
from app.services.fattura_parser import FatturaParser
from app.services.pdf_generator import PDFGenerator
from app.services.excel_generator import ExcelGenerator
from app.services.rate_limiter import RateLimiter

app = FastAPI(
    title="P7M.vcuria.app - Apertura file P7M e conversione fatture elettroniche",
    description="Strumento gratuito per aprire file .p7m e convertire fatture elettroniche in PDF ed Excel",
    version="1.0.0"
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

rate_limiter = RateLimiter()


def cleanup_old_temp_files():
    """Rimuove file temporanei più vecchi di 1 ora."""
    cutoff_time = datetime.now() - timedelta(hours=1)
    for temp_file in TEMP_DIR.glob("*.pkl"):
        try:
            if datetime.fromtimestamp(temp_file.stat().st_mtime) < cutoff_time:
                temp_file.unlink()
        except Exception:
            pass


def save_temp_data(data: Dict[str, Any]) -> str:
    """Salva temporaneamente i dati elaborati e restituisce un ID."""
    cleanup_old_temp_files()
    download_id = str(uuid.uuid4())
    temp_file = TEMP_DIR / f"{download_id}.pkl"
    with open(temp_file, 'wb') as f:
        pickle.dump(data, f)
    return download_id


def load_temp_data(download_id: str) -> Optional[Dict[str, Any]]:
    """Carica i dati temporanei per un ID."""
    temp_file = TEMP_DIR / f"{download_id}.pkl"
    if not temp_file.exists():
        return None
    try:
        with open(temp_file, 'rb') as f:
            return pickle.load(f)
    except Exception:
        return None


def generate_invoice_filename(fattura_data: Dict[str, Any]) -> str:
    """Genera un nome file sensato per la fattura."""
    dati_gen = fattura_data.get('dati_generali', {})
    cedente = fattura_data.get('cedente', {})
    
    numero = dati_gen.get('numero', 'N').replace('/', '-')
    data = dati_gen.get('data', '')
    if data and len(data) >= 10:
        data_parte = data[:10].replace('-', '')
    else:
        data_parte = 'NNNNNNNN'
    
    fornitore = cedente.get('denominazione', 'Fornitore')[:30]
    fornitore = re.sub(r'[^\w\s-]', '', fornitore).strip().replace(' ', '_')
    
    return f"Fattura_{numero}_{data_parte}_{fornitore}.pdf"

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_ZIP_SIZE = 50 * 1024 * 1024
MAX_BATCH_FILES = 20
TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET_KEY", "")
TURNSTILE_ENABLED = bool(TURNSTILE_SECRET)
TEMP_DIR = Path(tempfile.gettempdir()) / "p7m_web_temp"
TEMP_DIR.mkdir(exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "turnstile_enabled": TURNSTILE_ENABLED,
        "turnstile_site_key": os.getenv("TURNSTILE_SITE_KEY", "")
    })


@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})


@app.get("/faq", response_class=HTMLResponse)
async def faq(request: Request):
    return templates.TemplateResponse("faq.html", {"request": request})


@app.get("/download", response_class=HTMLResponse)
async def download_page(request: Request):
    return templates.TemplateResponse("download.html", {"request": request})


@app.get("/sitemap.xml")
async def sitemap():
    base_url = os.getenv("BASE_URL", "https://p7m.vcuria.app")
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>{base_url}/</loc>
        <changefreq>weekly</changefreq>
        <priority>1.0</priority>
    </url>
    <url>
        <loc>{base_url}/privacy</loc>
        <changefreq>monthly</changefreq>
        <priority>0.5</priority>
    </url>
    <url>
        <loc>{base_url}/faq</loc>
        <changefreq>monthly</changefreq>
        <priority>0.7</priority>
    </url>
    <url>
        <loc>{base_url}/download</loc>
        <changefreq>weekly</changefreq>
        <priority>0.8</priority>
    </url>
</urlset>"""
    return HTMLResponse(content=xml_content, media_type="application/xml")


@app.get("/robots.txt")
async def robots():
    base_url = os.getenv("BASE_URL", "https://p7m.vcuria.app")
    txt_content = f"""User-agent: *
Allow: /

Sitemap: {base_url}/sitemap.xml"""
    return HTMLResponse(content=txt_content, media_type="text/plain")


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/api/process")
async def process_file(
    request: Request,
    file: UploadFile = File(...),
    turnstile_token: Optional[str] = None
):
    client_ip = request.client.host
    
    if not rate_limiter.check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Troppi file caricati. Riprova tra qualche minuto.")
    
    if TURNSTILE_ENABLED and turnstile_token:
        if not await verify_turnstile(turnstile_token, client_ip):
            raise HTTPException(status_code=403, detail="Verifica Cloudflare Turnstile fallita.")
    
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File troppo grande. Massimo {MAX_FILE_SIZE // (1024*1024)} MB.")
    
    content = await file.read()
    
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File troppo grande. Massimo {MAX_FILE_SIZE // (1024*1024)} MB.")
    
    filename = file.filename or "documento.p7m"
    
    if filename.lower().endswith('.zip'):
        return await process_zip_batch(content, filename)
    else:
        return await process_single_file(content, filename)


async def process_single_file(content: bytes, filename: str):
    processor = P7MProcessor()
    result = processor.process(content, filename)
    
    if not result['success']:
        return JSONResponse(
            status_code=400,
            content={"error": result.get('error', 'Errore durante l\'elaborazione del file.')}
        )
    
    response_data = {
        "success": True,
        "filename": result['suggested_filename'],
        "mime_type": result['mime_type'],
        "size": result['payload_size'],
        "sha256": result['sha256'],
        "signature": {
            "signer_name": result['signer_info']['signer_name'],
            "organization": result['signer_info'].get('organization', ''),
            "valid_from": result['signer_info'].get('valid_from', '-'),
            "valid_to": result['signer_info'].get('valid_to', '-'),
            "is_expired": result['signer_info'].get('is_expired', False),
            "crypto_valid": result['signer_info'].get('crypto_valid'),
            "algorithm": result['signer_info'].get('algorithm', 'Non verificato'),
            "validation_error": result['signer_info'].get('validation_error')
        }
    }
    
    is_fattura = filename.lower().endswith('.xml.p7m') or (
        result['mime_type'] == 'text/xml' and b'FatturaElettronica' in result['payload'][:5000]
    )
    
    if is_fattura:
        fattura_parser = FatturaParser()
        fattura_data = fattura_parser.parse(result['payload'])
        if fattura_data:
            response_data['fattura'] = fattura_data
            
            pdf_gen = PDFGenerator()
            pdf_bytes = pdf_gen.generate_invoice_pdf(fattura_data, result['payload'])
            response_data['pdf_available'] = True
            response_data['pdf_size'] = len(pdf_bytes)
            
            temp_data = {
                'type': 'single',
                'filename': result['suggested_filename'],
                'xml_payload': result['payload'],
                'fattura_data': fattura_data,
                'pdf_bytes': pdf_bytes
            }
            download_id = save_temp_data(temp_data)
            response_data['download_id'] = download_id
    else:
        temp_data = {
            'type': 'single_xml',
            'filename': result['suggested_filename'],
            'xml_payload': result['payload']
        }
        download_id = save_temp_data(temp_data)
        response_data['download_id'] = download_id
    
    return JSONResponse(content=response_data)


async def process_zip_batch(content: bytes, filename: str):
    if len(content) > MAX_ZIP_SIZE:
        raise HTTPException(
            status_code=413, 
            detail=f"ZIP troppo grande. Massimo {MAX_ZIP_SIZE // (1024*1024)} MB."
        )
    
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            file_list = [f for f in zf.namelist() if not f.endswith('/')]
            
            if len(file_list) > MAX_BATCH_FILES:
                raise HTTPException(
                    status_code=413, 
                    detail=f"Troppi file nello ZIP. Massimo {MAX_BATCH_FILES} file per la versione gratuita."
                )
            
            processor = P7MProcessor()
            fattura_parser = FatturaParser()
            pdf_gen = PDFGenerator()
            results = []
            fatture_for_download = []
            
            for zip_file in file_list:
                if zf.getinfo(zip_file).file_size > MAX_FILE_SIZE:
                    results.append({
                        "filename": zip_file,
                        "success": False,
                        "error": "File troppo grande"
                    })
                    continue
                
                file_content = zf.read(zip_file)
                result = processor.process(file_content, zip_file)
                
                if result['success']:
                    item = {
                        "filename": zip_file,
                        "success": True,
                        "extracted_filename": result['suggested_filename'],
                        "mime_type": result['mime_type'],
                        "size": result['payload_size'],
                        "signer_name": result['signer_info']['signer_name']
                    }
                    
                    if result['mime_type'] == 'text/xml':
                        fattura_data = fattura_parser.parse(result['payload'])
                        if fattura_data:
                            item['fattura'] = fattura_data
                            pdf_bytes = pdf_gen.generate_invoice_pdf(fattura_data, result['payload'])
                            fatture_for_download.append({
                                'fattura_data': fattura_data,
                                'pdf_bytes': pdf_bytes,
                                'xml_payload': result['payload']
                            })
                    
                    results.append(item)
                else:
                    results.append({
                        "filename": zip_file,
                        "success": False,
                        "error": result.get('error', 'Errore sconosciuto')
                    })
            
            success_count = sum(1 for r in results if r['success'])
            fatture_count = sum(1 for r in results if r['success'] and 'fattura' in r)
            
            download_id = None
            if fatture_for_download:
                temp_data = {
                    'type': 'batch',
                    'fatture': fatture_for_download
                }
                download_id = save_temp_data(temp_data)
            
            response = {
                "success": True,
                "batch": True,
                "total_files": len(results),
                "success_count": success_count,
                "fatture_count": fatture_count,
                "results": results
            }
            
            if download_id:
                response['download_id'] = download_id
            
            return JSONResponse(content=response)
            
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="File ZIP non valido.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante l'elaborazione: {str(e)}")


@app.get("/api/download/{download_type}")
async def download_file(
    download_type: str,
    download_id: str = Query(..., description="ID del download")
):
    """
    Scarica file elaborati.
    
    - download_type='pdf': Scarica il PDF della fattura singola
    - download_type='xml': Scarica l'XML estratto dalla firma
    - download_type='batch': Scarica ZIP con PDF di tutte le fatture + Excel riepilogo
    """
    temp_data = load_temp_data(download_id)
    if not temp_data:
        raise HTTPException(status_code=404, detail="Download non trovato o scaduto.")
    
    if download_type == 'pdf':
        if temp_data['type'] == 'single':
            fattura_data = temp_data['fattura_data']
            pdf_bytes = temp_data['pdf_bytes']
            filename = generate_invoice_filename(fattura_data)
            
            return StreamingResponse(
                io.BytesIO(pdf_bytes),
                media_type='application/pdf',
                headers={'Content-Disposition': f'attachment; filename="{filename}"'}
            )
        else:
            raise HTTPException(status_code=400, detail="Questo download non è un PDF singolo.")
    
    elif download_type == 'xml':
        if temp_data['type'] in ['single', 'single_xml']:
            xml_payload = temp_data['xml_payload']
            filename = temp_data['filename']
            
            return StreamingResponse(
                io.BytesIO(xml_payload),
                media_type='application/xml',
                headers={'Content-Disposition': f'attachment; filename="{filename}"'}
            )
        else:
            raise HTTPException(status_code=400, detail="Questo download non è un XML singolo.")
    
    elif download_type == 'batch':
        if temp_data['type'] == 'batch':
            fatture = temp_data['fatture']
            
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for idx, fattura_item in enumerate(fatture):
                    fattura_data = fattura_item['fattura_data']
                    pdf_bytes = fattura_item['pdf_bytes']
                    filename = generate_invoice_filename(fattura_data)
                    zf.writestr(f"pdf/{filename}", pdf_bytes)
                
                excel_gen = ExcelGenerator()
                excel_bytes = excel_gen.generate_summary([f['fattura_data'] for f in fatture])
                zf.writestr("Riepilogo_Fatture.xlsx", excel_bytes)
            
            zip_buffer.seek(0)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            return StreamingResponse(
                zip_buffer,
                media_type='application/zip',
                headers={'Content-Disposition': f'attachment; filename="Fatture_{timestamp}.zip"'}
            )
        else:
            raise HTTPException(status_code=400, detail="Questo download non è un batch.")
    
    else:
        raise HTTPException(status_code=400, detail="Tipo di download non valido.")


async def verify_turnstile(token: str, remote_ip: str) -> bool:
    if not TURNSTILE_ENABLED:
        return True
    
    import httpx
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                json={
                    "secret": TURNSTILE_SECRET,
                    "response": token,
                    "remoteip": remote_ip
                },
                timeout=5.0
            )
            data = response.json()
            return data.get("success", False)
        except Exception:
            return False


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
