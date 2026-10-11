import os
import io
import zipfile
import tempfile
import hashlib
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Request, HTTPException
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

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_ZIP_SIZE = 50 * 1024 * 1024
MAX_BATCH_FILES = 20
TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET_KEY", "")
TURNSTILE_ENABLED = bool(TURNSTILE_SECRET)


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
        result['mime_type'] == 'text/xml' and b'FatturaElettronica' in content[:5000]
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
            results = []
            
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
                    
                    results.append(item)
                else:
                    results.append({
                        "filename": zip_file,
                        "success": False,
                        "error": result.get('error', 'Errore sconosciuto')
                    })
            
            success_count = sum(1 for r in results if r['success'])
            fatture_count = sum(1 for r in results if r['success'] and 'fattura' in r)
            
            return JSONResponse(content={
                "success": True,
                "batch": True,
                "total_files": len(results),
                "success_count": success_count,
                "fatture_count": fatture_count,
                "results": results
            })
            
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="File ZIP non valido.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante l'elaborazione: {str(e)}")


@app.post("/api/download/{type}")
async def download_file(
    type: str,
    request: Request
):
    pass


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
