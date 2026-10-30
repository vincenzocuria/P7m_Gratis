from weasyprint import HTML, CSS
from io import BytesIO
from typing import Dict, Any


class PDFGenerator:
    """Generatore di PDF da fatture elettroniche."""
    
    def generate_invoice_pdf(self, fattura_data: Dict[str, Any], xml_content: bytes) -> bytes:
        """
        Genera un PDF da una fattura elettronica.
        
        Args:
            fattura_data: Dati della fattura estratti
            xml_content: Contenuto XML originale
        
        Returns:
            Bytes del PDF generato
        """
        html_content = self._generate_html(fattura_data)
        
        pdf_bytes = HTML(string=html_content).write_pdf(
            stylesheets=[CSS(string=self._get_css())]
        )
        
        return pdf_bytes
    
    def _generate_html(self, fattura: Dict[str, Any]) -> str:
        """Genera HTML per la fattura."""
        cedente = fattura.get('cedente', {})
        cessionario = fattura.get('cessionario', {})
        dati_gen = fattura.get('dati_generali', {})
        riepilogo = fattura.get('riepilogo', [])
        linee = fattura.get('linee', [])
        
        tipo_doc_map = {
            'TD01': 'Fattura',
            'TD02': 'Acconto/Anticipo su fattura',
            'TD03': 'Acconto/Anticipo su parcella',
            'TD04': 'Nota di credito',
            'TD05': 'Nota di debito',
            'TD06': 'Parcella',
        }
        
        tipo_doc = tipo_doc_map.get(dati_gen.get('tipo_documento', ''), dati_gen.get('tipo_documento', 'Documento'))
        
        html = f"""
        <!DOCTYPE html>
        <html lang="it">
        <head>
            <meta charset="UTF-8">
            <title>Fattura {dati_gen.get('numero', '')}</title>
        </head>
        <body>
            <div class="header">
                <h1>{tipo_doc} n. {dati_gen.get('numero', '')}</h1>
                <p>Data: {self._format_date(dati_gen.get('data', ''))}</p>
            </div>
            
            <div class="avviso">
                <strong>Attenzione:</strong> Questo è un documento di cortesia generato automaticamente.
                Non ha valore fiscale. L'originale è il file XML trasmesso al Sistema di Interscambio.
            </div>
            
            <div class="section">
                <h2>Cedente/Prestatore</h2>
                <p><strong>{cedente.get('denominazione', '')}</strong></p>
                {f"<p>P.IVA: {cedente.get('partita_iva', '')}</p>" if cedente.get('partita_iva') else ''}
                {f"<p>C.F.: {cedente.get('codice_fiscale', '')}</p>" if cedente.get('codice_fiscale') else ''}
                {f"<p>{cedente.get('indirizzo', '')}, {cedente.get('cap', '')} {cedente.get('comune', '')} ({cedente.get('provincia', '')})</p>" if cedente.get('indirizzo') else ''}
            </div>
            
            <div class="section">
                <h2>Cessionario/Committente</h2>
                <p><strong>{cessionario.get('denominazione', '')}</strong></p>
                {f"<p>P.IVA: {cessionario.get('partita_iva', '')}</p>" if cessionario.get('partita_iva') else ''}
                {f"<p>C.F.: {cessionario.get('codice_fiscale', '')}</p>" if cessionario.get('codice_fiscale') else ''}
                {f"<p>{cessionario.get('indirizzo', '')}, {cessionario.get('cap', '')} {cessionario.get('comune', '')} ({cessionario.get('provincia', '')})</p>" if cessionario.get('indirizzo') else ''}
            </div>
            
            {f'<div class="section"><p><strong>Causale:</strong> {dati_gen.get("causale", "")}</p></div>' if dati_gen.get('causale') else ''}
            
            <div class="section">
                <h2>Dettaglio</h2>
                <table>
                    <thead>
                        <tr>
                            <th>N.</th>
                            <th>Descrizione</th>
                            <th>Quantità</th>
                            <th>Prezzo Unit.</th>
                            <th>IVA %</th>
                            <th>Totale</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        for linea in linee:
            html += f"""
                        <tr>
                            <td>{linea.get('numero_linea', '')}</td>
                            <td>{linea.get('descrizione', '')}</td>
                            <td>{linea.get('quantita', '')} {linea.get('unita_misura', '')}</td>
                            <td>{self._format_currency(linea.get('prezzo_unitario', ''))}</td>
                            <td>{linea.get('aliquota_iva', '')}%</td>
                            <td>{self._format_currency(linea.get('prezzo_totale', ''))}</td>
                        </tr>
            """
        
        html += """
                    </tbody>
                </table>
            </div>
            
            <div class="section">
                <h2>Riepilogo IVA</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Aliquota IVA</th>
                            <th>Imponibile</th>
                            <th>Imposta</th>
                            <th>Natura</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        totale_imponibile = 0.0
        totale_imposta = 0.0
        
        for riepilogo_item in riepilogo:
            imponibile = float(riepilogo_item.get('imponibile', '0').replace(',', '.'))
            imposta = float(riepilogo_item.get('imposta', '0').replace(',', '.'))
            totale_imponibile += imponibile
            totale_imposta += imposta
            
            html += f"""
                        <tr>
                            <td>{riepilogo_item.get('aliquota_iva', '')}%</td>
                            <td>{self._format_currency(riepilogo_item.get('imponibile', ''))}</td>
                            <td>{self._format_currency(riepilogo_item.get('imposta', ''))}</td>
                            <td>{riepilogo_item.get('natura', '-')}</td>
                        </tr>
            """
        
        totale_documento = totale_imponibile + totale_imposta
        
        html += f"""
                    </tbody>
                </table>
            </div>
            
            <div class="totale">
                <p><strong>Totale Imponibile:</strong> {self._format_number(totale_imponibile)} €</p>
                <p><strong>Totale IVA:</strong> {self._format_number(totale_imposta)} €</p>
                <p class="totale-finale"><strong>TOTALE DOCUMENTO:</strong> {self._format_number(totale_documento)} €</p>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _get_css(self) -> str:
        """Restituisce il CSS per il PDF."""
        return """
        @page {
            size: A4;
            margin: 2cm;
        }
        
        body {
            font-family: Arial, sans-serif;
            font-size: 11pt;
            line-height: 1.4;
        }
        
        .header {
            text-align: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #333;
        }
        
        .header h1 {
            margin: 0 0 10px 0;
            font-size: 18pt;
        }
        
        .avviso {
            background-color: #fff3cd;
            border: 1px solid #ffc107;
            padding: 10px;
            margin-bottom: 20px;
            font-size: 9pt;
        }
        
        .section {
            margin-bottom: 20px;
        }
        
        .section h2 {
            font-size: 13pt;
            margin-bottom: 10px;
            color: #333;
            border-bottom: 1px solid #ddd;
            padding-bottom: 5px;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        
        table th {
            background-color: #f8f9fa;
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
            font-weight: bold;
        }
        
        table td {
            border: 1px solid #ddd;
            padding: 8px;
        }
        
        .totale {
            margin-top: 30px;
            text-align: right;
            font-size: 12pt;
        }
        
        .totale p {
            margin: 5px 0;
        }
        
        .totale-finale {
            font-size: 14pt;
            margin-top: 10px;
        }
        """
    
    def _format_date(self, date_str: str) -> str:
        """Formatta una data da YYYY-MM-DD a DD/MM/YYYY."""
        if not date_str or len(date_str) != 10:
            return date_str
        try:
            parts = date_str.split('-')
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
        except:
            return date_str
    
    def _format_currency(self, value: str) -> str:
        """Formatta un valore monetario."""
        if not value:
            return '0,00 €'
        try:
            num = float(value.replace(',', '.'))
            return f"{num:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.')
        except:
            return f"{value} €"
    
    def _format_number(self, value: float) -> str:
        """Formatta un numero."""
        return f"{value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
