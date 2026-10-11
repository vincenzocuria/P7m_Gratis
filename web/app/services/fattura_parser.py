from lxml import etree
from typing import Optional, Dict, Any
import re


class FatturaParser:
    """Parser per fatture elettroniche XML FatturaPA."""
    
    NAMESPACES = {
        'p': 'http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2',
        'p11': 'http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.1',
        'p10': 'http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.0'
    }
    
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
            
            ns = None
            for prefix, uri in self.NAMESPACES.items():
                if uri in root.tag:
                    ns = {'p': uri}
                    break
            
            if ns is None:
                ns = {'p': self.NAMESPACES['p']}
            
            fattura = {}
            
            header = root.find('.//p:FatturaElettronicaHeader', ns)
            if header is not None:
                fattura['cedente'] = self._extract_cedente(header, ns)
                fattura['cessionario'] = self._extract_cessionario(header, ns)
            
            body = root.find('.//p:FatturaElettronicaBody', ns)
            if body is not None:
                fattura['dati_generali'] = self._extract_dati_generali(body, ns)
                fattura['riepilogo'] = self._extract_riepilogo(body, ns)
                fattura['linee'] = self._extract_linee(body, ns)
            
            return fattura
            
        except Exception as e:
            return None
    
    def _get_text(self, element, path: str, ns: dict, default: str = '') -> str:
        """Estrae il testo da un elemento XML."""
        node = element.find(path, ns)
        return node.text if node is not None and node.text else default
    
    def _extract_cedente(self, header, ns) -> Dict[str, str]:
        """Estrae i dati del cedente/prestatore."""
        cedente_elem = header.find('.//p:CedentePrestatore', ns)
        if cedente_elem is None:
            return {}
        
        dati_anag = cedente_elem.find('.//p:DatiAnagrafici', ns)
        sede = cedente_elem.find('.//p:Sede', ns)
        
        result = {}
        
        if dati_anag is not None:
            result['partita_iva'] = self._get_text(dati_anag, './/p:IdFiscaleIVA/p:IdCodice', ns)
            result['codice_fiscale'] = self._get_text(dati_anag, './/p:CodiceFiscale', ns)
            
            anagrafica = dati_anag.find('.//p:Anagrafica', ns)
            if anagrafica is not None:
                denominazione = self._get_text(anagrafica, './/p:Denominazione', ns)
                if denominazione:
                    result['denominazione'] = denominazione
                else:
                    nome = self._get_text(anagrafica, './/p:Nome', ns)
                    cognome = self._get_text(anagrafica, './/p:Cognome', ns)
                    result['denominazione'] = f"{nome} {cognome}".strip()
            
            result['regime_fiscale'] = self._get_text(dati_anag, './/p:RegimeFiscale', ns)
        
        if sede is not None:
            indirizzo = self._get_text(sede, './/p:Indirizzo', ns)
            cap = self._get_text(sede, './/p:CAP', ns)
            comune = self._get_text(sede, './/p:Comune', ns)
            provincia = self._get_text(sede, './/p:Provincia', ns)
            nazione = self._get_text(sede, './/p:Nazione', ns)
            
            result['indirizzo'] = indirizzo
            result['cap'] = cap
            result['comune'] = comune
            result['provincia'] = provincia
            result['nazione'] = nazione
        
        return result
    
    def _extract_cessionario(self, header, ns) -> Dict[str, str]:
        """Estrae i dati del cessionario/committente."""
        cessionario_elem = header.find('.//p:CessionarioCommittente', ns)
        if cessionario_elem is None:
            return {}
        
        dati_anag = cessionario_elem.find('.//p:DatiAnagrafici', ns)
        sede = cessionario_elem.find('.//p:Sede', ns)
        
        result = {}
        
        if dati_anag is not None:
            result['partita_iva'] = self._get_text(dati_anag, './/p:IdFiscaleIVA/p:IdCodice', ns)
            result['codice_fiscale'] = self._get_text(dati_anag, './/p:CodiceFiscale', ns)
            
            anagrafica = dati_anag.find('.//p:Anagrafica', ns)
            if anagrafica is not None:
                denominazione = self._get_text(anagrafica, './/p:Denominazione', ns)
                if denominazione:
                    result['denominazione'] = denominazione
                else:
                    nome = self._get_text(anagrafica, './/p:Nome', ns)
                    cognome = self._get_text(anagrafica, './/p:Cognome', ns)
                    result['denominazione'] = f"{nome} {cognome}".strip()
        
        if sede is not None:
            indirizzo = self._get_text(sede, './/p:Indirizzo', ns)
            cap = self._get_text(sede, './/p:CAP', ns)
            comune = self._get_text(sede, './/p:Comune', ns)
            provincia = self._get_text(sede, './/p:Provincia', ns)
            nazione = self._get_text(sede, './/p:Nazione', ns)
            
            result['indirizzo'] = indirizzo
            result['cap'] = cap
            result['comune'] = comune
            result['provincia'] = provincia
            result['nazione'] = nazione
        
        return result
    
    def _extract_dati_generali(self, body, ns) -> Dict[str, str]:
        """Estrae i dati generali del documento."""
        dati_gen = body.find('.//p:DatiGenerali/p:DatiGeneraliDocumento', ns)
        if dati_gen is None:
            return {}
        
        result = {
            'tipo_documento': self._get_text(dati_gen, './/p:TipoDocumento', ns),
            'numero': self._get_text(dati_gen, './/p:Numero', ns),
            'data': self._get_text(dati_gen, './/p:Data', ns),
            'divisa': self._get_text(dati_gen, './/p:Divisa', ns),
            'importo_totale': self._get_text(dati_gen, './/p:ImportoTotaleDocumento', ns),
        }
        
        causale_elems = dati_gen.findall('.//p:Causale', ns)
        if causale_elems:
            result['causale'] = ' '.join([elem.text for elem in causale_elems if elem.text])
        
        return result
    
    def _extract_riepilogo(self, body, ns) -> list:
        """Estrae il riepilogo IVA."""
        riepilogo_elems = body.findall('.//p:DatiBeniServizi/p:DatiRiepilogo', ns)
        risultato = []
        
        for elem in riepilogo_elems:
            riepilogo = {
                'aliquota_iva': self._get_text(elem, './/p:AliquotaIVA', ns),
                'imponibile': self._get_text(elem, './/p:ImponibileImporto', ns),
                'imposta': self._get_text(elem, './/p:Imposta', ns),
                'natura': self._get_text(elem, './/p:Natura', ns),
            }
            risultato.append(riepilogo)
        
        return risultato
    
    def _extract_linee(self, body, ns) -> list:
        """Estrae le linee di dettaglio."""
        linee_elems = body.findall('.//p:DatiBeniServizi/p:DettaglioLinee', ns)
        risultato = []
        
        for elem in linee_elems:
            linea = {
                'numero_linea': self._get_text(elem, './/p:NumeroLinea', ns),
                'descrizione': self._get_text(elem, './/p:Descrizione', ns),
                'quantita': self._get_text(elem, './/p:Quantita', ns),
                'unita_misura': self._get_text(elem, './/p:UnitaMisura', ns),
                'prezzo_unitario': self._get_text(elem, './/p:PrezzoUnitario', ns),
                'prezzo_totale': self._get_text(elem, './/p:PrezzoTotale', ns),
                'aliquota_iva': self._get_text(elem, './/p:AliquotaIVA', ns),
            }
            risultato.append(linea)
        
        return risultato
