from lxml import etree
from typing import Optional, Dict, Any
import re


class FatturaParser:
    """Parser per fatture elettroniche XML FatturaPA."""
    
    def parse(self, xml_content: bytes) -> Optional[Dict[str, Any]]:
        """
        Estrae i dati principali da una fattura elettronica XML.
        
        Args:
            xml_content: Contenuto XML della fattura
        
        Returns:
            Dizionario con i dati della fattura o None se non è una FatturaPA
        """
        try:
            parser = etree.XMLParser(
                resolve_entities=False,
                no_network=True,
                huge_tree=False
            )
            root = etree.fromstring(xml_content, parser=parser)
            
            if 'FatturaElettronica' not in root.tag:
                return None
            
            fattura = {}
            
            header = root.find('.//{*}FatturaElettronicaHeader')
            if header is not None:
                fattura['cedente'] = self._extract_cedente(header)
                fattura['cessionario'] = self._extract_cessionario(header)
            
            body = root.find('.//{*}FatturaElettronicaBody')
            if body is not None:
                fattura['dati_generali'] = self._extract_dati_generali(body)
                fattura['riepilogo'] = self._extract_riepilogo(body)
                fattura['linee'] = self._extract_linee(body)
            
            return fattura
            
        except Exception as e:
            return None
    
    def _get_text(self, element, tag: str, default: str = '') -> str:
        """Estrae il testo da un elemento XML usando wildcard namespace."""
        node = element.find(f'.//{{{element.nsmap.get(element.prefix) or "*"}}}{tag}') if element.nsmap else element.find(f'.//{{{element.nsmap.get(None) or "*"}}}{tag}')
        if node is None:
            node = element.find(f'.//*[local-name()="{tag}"]')
        return node.text if node is not None and node.text else default
    
    def _find_element(self, parent, path: str):
        """Trova un elemento usando wildcard namespace."""
        parts = path.split('/')
        current = parent
        for part in parts:
            if not part or part == '.':
                continue
            if part == '..':
                current = current.getparent()
                continue
            found = None
            for child in current:
                if child.tag.endswith(f'}}{part}') or child.tag == part:
                    found = child
                    break
            if found is None:
                return None
            current = found
        return current
    
    def _extract_cedente(self, header) -> Dict[str, str]:
        """Estrae i dati del cedente/prestatore."""
        result = {}
        
        for elem in header.iter():
            if elem.tag.endswith('}CedentePrestatore') or elem.tag == 'CedentePrestatore':
                cedente_elem = elem
                break
        else:
            return result
        
        for elem in cedente_elem.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            
            if tag == 'IdCodice' and elem.getparent().tag.endswith('IdFiscaleIVA'):
                result['partita_iva'] = elem.text or ''
            elif tag == 'CodiceFiscale' and elem.getparent().tag.endswith('DatiAnagrafici'):
                result['codice_fiscale'] = elem.text or ''
            elif tag == 'Denominazione':
                result['denominazione'] = elem.text or ''
            elif tag == 'Nome':
                nome = elem.text or ''
                cognome = ''
                for sibling in elem.getparent():
                    if sibling.tag.endswith('Cognome'):
                        cognome = sibling.text or ''
                if nome and not result.get('denominazione'):
                    result['denominazione'] = f"{nome} {cognome}".strip()
            elif tag == 'RegimeFiscale':
                result['regime_fiscale'] = elem.text or ''
            elif tag == 'Indirizzo' and elem.getparent().tag.endswith('Sede'):
                result['indirizzo'] = elem.text or ''
            elif tag == 'CAP' and elem.getparent().tag.endswith('Sede'):
                result['cap'] = elem.text or ''
            elif tag == 'Comune' and elem.getparent().tag.endswith('Sede'):
                result['comune'] = elem.text or ''
            elif tag == 'Provincia' and elem.getparent().tag.endswith('Sede'):
                result['provincia'] = elem.text or ''
            elif tag == 'Nazione' and elem.getparent().tag.endswith('Sede'):
                result['nazione'] = elem.text or ''
        
        return result
    
    def _extract_cessionario(self, header) -> Dict[str, str]:
        """Estrae i dati del cessionario/committente."""
        result = {}
        
        for elem in header.iter():
            if elem.tag.endswith('}CessionarioCommittente') or elem.tag == 'CessionarioCommittente':
                cessionario_elem = elem
                break
        else:
            return result
        
        for elem in cessionario_elem.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            
            if tag == 'IdCodice' and elem.getparent().tag.endswith('IdFiscaleIVA'):
                result['partita_iva'] = elem.text or ''
            elif tag == 'CodiceFiscale' and elem.getparent().tag.endswith('DatiAnagrafici'):
                result['codice_fiscale'] = elem.text or ''
            elif tag == 'Denominazione':
                result['denominazione'] = elem.text or ''
            elif tag == 'Nome':
                nome = elem.text or ''
                cognome = ''
                for sibling in elem.getparent():
                    if sibling.tag.endswith('Cognome'):
                        cognome = sibling.text or ''
                if nome and not result.get('denominazione'):
                    result['denominazione'] = f"{nome} {cognome}".strip()
            elif tag == 'Indirizzo' and elem.getparent().tag.endswith('Sede'):
                result['indirizzo'] = elem.text or ''
            elif tag == 'CAP' and elem.getparent().tag.endswith('Sede'):
                result['cap'] = elem.text or ''
            elif tag == 'Comune' and elem.getparent().tag.endswith('Sede'):
                result['comune'] = elem.text or ''
            elif tag == 'Provincia' and elem.getparent().tag.endswith('Sede'):
                result['provincia'] = elem.text or ''
            elif tag == 'Nazione' and elem.getparent().tag.endswith('Sede'):
                result['nazione'] = elem.text or ''
        
        return result
    
    def _extract_dati_generali(self, body) -> Dict[str, str]:
        """Estrae i dati generali del documento."""
        result = {}
        causale_parts = []
        
        for elem in body.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            
            if tag == 'TipoDocumento' and elem.getparent().tag.endswith('DatiGeneraliDocumento'):
                result['tipo_documento'] = elem.text or ''
            elif tag == 'Numero' and elem.getparent().tag.endswith('DatiGeneraliDocumento'):
                result['numero'] = elem.text or ''
            elif tag == 'Data' and elem.getparent().tag.endswith('DatiGeneraliDocumento'):
                result['data'] = elem.text or ''
            elif tag == 'Divisa':
                result['divisa'] = elem.text or ''
            elif tag == 'ImportoTotaleDocumento':
                result['importo_totale'] = elem.text or ''
            elif tag == 'Causale':
                if elem.text:
                    causale_parts.append(elem.text)
        
        if causale_parts:
            result['causale'] = ' '.join(causale_parts)
        
        return result
    
    def _extract_riepilogo(self, body) -> list:
        """Estrae il riepilogo IVA."""
        risultato = []
        current_riepilogo = None
        
        for elem in body.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            
            if tag == 'DatiRiepilogo':
                if current_riepilogo is not None:
                    risultato.append(current_riepilogo)
                current_riepilogo = {}
            elif current_riepilogo is not None:
                if tag == 'AliquotaIVA':
                    current_riepilogo['aliquota_iva'] = elem.text or ''
                elif tag == 'ImponibileImporto':
                    current_riepilogo['imponibile'] = elem.text or ''
                elif tag == 'Imposta':
                    current_riepilogo['imposta'] = elem.text or ''
                elif tag == 'Natura':
                    current_riepilogo['natura'] = elem.text or ''
        
        if current_riepilogo is not None:
            risultato.append(current_riepilogo)
        
        return risultato
    
    def _extract_linee(self, body) -> list:
        """Estrae le linee di dettaglio."""
        risultato = []
        current_linea = None
        
        for elem in body.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            
            if tag == 'DettaglioLinee':
                if current_linea is not None:
                    risultato.append(current_linea)
                current_linea = {}
            elif current_linea is not None:
                if tag == 'NumeroLinea':
                    current_linea['numero_linea'] = elem.text or ''
                elif tag == 'Descrizione':
                    current_linea['descrizione'] = elem.text or ''
                elif tag == 'Quantita':
                    current_linea['quantita'] = elem.text or ''
                elif tag == 'UnitaMisura':
                    current_linea['unita_misura'] = elem.text or ''
                elif tag == 'PrezzoUnitario':
                    current_linea['prezzo_unitario'] = elem.text or ''
                elif tag == 'PrezzoTotale':
                    current_linea['prezzo_totale'] = elem.text or ''
                elif tag == 'AliquotaIVA':
                    current_linea['aliquota_iva'] = elem.text or ''
        
        if current_linea is not None:
            risultato.append(current_linea)
        
        return risultato
