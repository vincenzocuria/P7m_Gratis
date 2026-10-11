import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.fattura_parser import FatturaParser


class TestFatturaParser(unittest.TestCase):
    """Test per il parser di fatture elettroniche."""
    
    def setUp(self):
        self.parser = FatturaParser()
        self.samples_dir = Path(__file__).parent.parent.parent / 'samples'
    
    def test_parse_valid_fattura(self):
        """Test parsing di una fattura elettronica valida."""
        sample_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <FatturaElettronicaHeader>
    <DatiTrasmissione>
      <IdTrasmittente>
        <IdPaese>IT</IdPaese>
        <IdCodice>01234567890</IdCodice>
      </IdTrasmittente>
      <ProgressivoInvio>00001</ProgressivoInvio>
      <FormatoTrasmissione>FPR12</FormatoTrasmissione>
      <CodiceDestinatario>AAAAAA</CodiceDestinatario>
    </DatiTrasmissione>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>01234567890</IdCodice>
        </IdFiscaleIVA>
        <Anagrafica>
          <Denominazione>Fornitore Test SRL</Denominazione>
        </Anagrafica>
        <RegimeFiscale>RF01</RegimeFiscale>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Test 123</Indirizzo>
        <CAP>00100</CAP>
        <Comune>Roma</Comune>
        <Provincia>RM</Provincia>
        <Nazione>IT</Nazione>
      </Sede>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>IT</IdPaese>
          <IdCodice>09876543210</IdCodice>
        </IdFiscaleIVA>
        <Anagrafica>
          <Denominazione>Cliente Test SRL</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Cliente 456</Indirizzo>
        <CAP>20100</CAP>
        <Comune>Milano</Comune>
        <Provincia>MI</Provincia>
        <Nazione>IT</Nazione>
      </Sede>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento>
        <Divisa>EUR</Divisa>
        <Data>2026-10-01</Data>
        <Numero>123</Numero>
        <ImportoTotaleDocumento>122.00</ImportoTotaleDocumento>
        <Causale>Vendita prodotti</Causale>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <Descrizione>Prodotto Test</Descrizione>
        <Quantita>1.00</Quantita>
        <PrezzoUnitario>100.00</PrezzoUnitario>
        <PrezzoTotale>100.00</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
      <DatiRiepilogo>
        <AliquotaIVA>22.00</AliquotaIVA>
        <ImponibileImporto>100.00</ImponibileImporto>
        <Imposta>22.00</Imposta>
      </DatiRiepilogo>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>'''
        
        result = self.parser.parse(sample_xml)
        
        self.assertIsNotNone(result)
        self.assertIn('cedente', result)
        self.assertIn('cessionario', result)
        self.assertIn('dati_generali', result)
        self.assertIn('riepilogo', result)
        self.assertIn('linee', result)
        
        self.assertEqual(result['cedente']['denominazione'], 'Fornitore Test SRL')
        self.assertEqual(result['cedente']['partita_iva'], '01234567890')
        
        self.assertEqual(result['cessionario']['denominazione'], 'Cliente Test SRL')
        
        self.assertEqual(result['dati_generali']['tipo_documento'], 'TD01')
        self.assertEqual(result['dati_generali']['numero'], '123')
        self.assertEqual(result['dati_generali']['data'], '2026-10-01')
        
        self.assertEqual(len(result['riepilogo']), 1)
        self.assertEqual(result['riepilogo'][0]['aliquota_iva'], '22.00')
        
        self.assertEqual(len(result['linee']), 1)
        self.assertEqual(result['linee'][0]['descrizione'], 'Prodotto Test')
    
    def test_parse_non_fattura(self):
        """Test parsing di un XML non fattura."""
        non_fattura_xml = b'<?xml version="1.0"?><root><data>test</data></root>'
        
        result = self.parser.parse(non_fattura_xml)
        
        self.assertIsNone(result)
    
    def test_parse_invalid_xml(self):
        """Test parsing di XML non valido."""
        invalid_xml = b'This is not XML'
        
        result = self.parser.parse(invalid_xml)
        
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
