import os
import datetime
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

def generate_key_and_cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IT"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Comune di Antigravity PA"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Servizi Demografici"),
        x509.NameAttribute(NameOID.COMMON_NAME, "MARIO ROSSI"),
        x509.NameAttribute(NameOID.SERIAL_NUMBER, "TINIT-RSSMRA80A01H501Z"),
    ])
    
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    return key, cert

def create_p7m(data_bytes: bytes, key, cert) -> bytes:
    """Creates a PKCS7 encapsulated SignedData envelope (.p7m)"""
    builder = pkcs7.PKCS7SignatureBuilder()
    builder = builder.set_data(data_bytes)
    builder = builder.add_signer(cert, key, hashes.SHA256())
    return builder.sign(serialization.Encoding.DER, options=[])

def main():
    print("Generazione file .p7m di test in corso...")
    os.makedirs("samples", exist_ok=True)
    key, cert = generate_key_and_cert()

    # 1. Sample PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=16)
    pdf.cell(200, 10, text="COMUNE DI PROVA - DETERMINA N. 142/2026", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", size=12)
    pdf.ln(10)
    pdf.multi_cell(0, 10, text="Oggetto: Approvazione atti di gara per la manutenzione stradale.\n\n"
                               "Il Responsabile del Servizio Tecnico VISTI gli atti...\n"
                               "DETERMINA di approvare il progetto esecutivo.\n\n"
                               "Documento firmato digitalmente ai sensi del CAD.")
    pdf_bytes = bytes(pdf.output())
    p7m_pdf = create_p7m(pdf_bytes, key, cert)
    with open("samples/determina_142.pdf.p7m", "wb") as f:
        f.write(p7m_pdf)
    print("Creato samples/determina_142.pdf.p7m")

    # 2. Sample XML (Fattura Elettronica PA)
    xml_str = """<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPA12" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <DatiTrasmissione>
      <IdTrasmittente>
        <IdPaese>IT</IdPaese>
        <IdCodice>01234567890</IdCodice>
      </IdTrasmittente>
      <ProgressivoInvio>00001</ProgressivoInvio>
      <FormatoTrasmissione>FPA12</FormatoTrasmissione>
      <CodiceDestinatario>UF1234</CodiceDestinatario>
    </DatiTrasmissione>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>12345678901</IdCodice>
        </IdFiscaleIVA>
        <Anagrafica>
          <Denominazione>Forniture &amp; Servizi SRL</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
    </CedentePrestatore>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento>
        <Divisa>EUR</Divisa>
        <Data>2026-08-01</Data>
        <Numero>45/2026</Numero>
        <ImportoTotaleDocumento>1250.00</ImportoTotaleDocumento>
      </DatiGeneraliDocumento>
    </DatiGenerali>
  </FatturaElettronicaBody>
</p:FatturaElettronica>"""
    xml_bytes = xml_str.encode('utf-8')
    p7m_xml = create_p7m(xml_bytes, key, cert)
    with open("samples/fattura_FPA12.xml.p7m", "wb") as f:
        f.write(p7m_xml)
    print("Creato samples/fattura_FPA12.xml.p7m")

    # 3. Sample TXT
    txt_bytes = ("VERBALE DI DELIBERAZIONE DELLA GIUNTA COMUNALE\n"
                 "Anno 2026 - Verbale N. 88\n\n"
                 "L'anno 2026 addì 7 del mese di Agosto, la Giunta si è riunita...\n"
                 "Presenti: Rossi Mario (Sindaco), Bianchi Anna (Assessore).\n"
                 "Approvato all'unanimità.").encode('utf-8')
    p7m_txt = create_p7m(txt_bytes, key, cert)
    with open("samples/verbale_giunta.txt.p7m", "wb") as f:
        f.write(p7m_txt)
    print("Creato samples/verbale_giunta.txt.p7m")

    # 4. Sample PNG Image
    img = Image.new('RGB', (600, 300), color=(30, 41, 59))
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 580, 280], outline=(59, 130, 246), width=4)
    d.text((40, 60), "Timbro e Firma Digitale", fill=(255, 255, 255))
    d.text((40, 120), "Certificato: Mario Rossi (MARIO ROSSI)", fill=(148, 163, 184))
    d.text((40, 160), "Comune di Antigravity PA", fill=(148, 163, 184))
    
    import io
    img_buf = io.BytesIO()
    img.save(img_buf, format='PNG')
    p7m_img = create_p7m(img_buf.getvalue(), key, cert)
    with open("samples/certificato_allegato.png.p7m", "wb") as f:
        f.write(p7m_img)
    print("Creato samples/certificato_allegato.png.p7m")

    print("\nGenerazione completata con successo!")

if __name__ == "__main__":
    main()
