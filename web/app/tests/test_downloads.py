import sys
import os
import unittest
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import io

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from app.main import app, save_temp_data, load_temp_data, generate_invoice_filename, download_storage, DOWNLOAD_TTL_SECONDS


class TestDownloads(unittest.TestCase):
    """Test per il sistema di download."""
    
    def setUp(self):
        self.client = TestClient(app)
        # Pulisci storage prima di ogni test
        download_storage.clear()
    
    def tearDown(self):
        # Pulisci storage dopo ogni test
        download_storage.clear()
    
    def test_save_and_load_temp_data(self):
        """Test salvataggio e caricamento dati temporanei IN MEMORIA."""
        test_data = {
            'type': 'single',
            'filename': 'test.pdf',
            'xml_payload': b'<xml>test</xml>',
            'fattura_data': {'numero': '123'}
        }
        
        download_id = save_temp_data(test_data)
        self.assertIsNotNone(download_id)
        self.assertIsInstance(download_id, str)
        
        # Verifica che sia in memoria, non su disco
        self.assertIn(download_id, download_storage)
        
        loaded_data = load_temp_data(download_id)
        self.assertIsNotNone(loaded_data)
        self.assertEqual(loaded_data['type'], 'single')
        self.assertEqual(loaded_data['filename'], 'test.pdf')
    
    def test_load_nonexistent_temp_data(self):
        """Test caricamento di dati inesistenti."""
        result = load_temp_data('nonexistent-id')
        self.assertIsNone(result)
    
    def test_download_deleted_after_first_access(self):
        """Test che i dati vengono cancellati dopo il primo download."""
        test_data = {
            'type': 'single',
            'filename': 'test.pdf',
            'xml_payload': b'<xml>test</xml>',
            'fattura_data': {'numero': '123'}
        }
        
        download_id = save_temp_data(test_data)
        
        # Primo accesso con mark_downloaded=True
        first_load = load_temp_data(download_id, mark_downloaded=True)
        self.assertIsNotNone(first_load)
        
        # Verifica che sia marcato come scaricato
        self.assertTrue(download_storage[download_id]['downloaded'])
        
        # Secondo accesso dovrebbe fallire (già scaricato)
        second_load = load_temp_data(download_id, mark_downloaded=False)
        self.assertIsNone(second_load)
    
    def test_ttl_expiration(self):
        """Test che i dati scadono dopo il TTL (10 minuti)."""
        test_data = {
            'type': 'single',
            'filename': 'test.pdf',
            'xml_payload': b'<xml>test</xml>',
            'fattura_data': {'numero': '123'}
        }
        
        download_id = save_temp_data(test_data)
        
        # Simula scadenza modificando il timestamp
        download_storage[download_id]['created_at'] = time.time() - (DOWNLOAD_TTL_SECONDS + 1)
        
        # Tentativo di caricamento dopo scadenza
        loaded_data = load_temp_data(download_id)
        self.assertIsNone(loaded_data)
        
        # Verifica che sia stato rimosso dallo storage
        self.assertNotIn(download_id, download_storage)
    
    def test_ttl_not_expired(self):
        """Test che i dati NON scadono prima del TTL."""
        test_data = {
            'type': 'single',
            'filename': 'test.pdf',
            'xml_payload': b'<xml>test</xml>',
            'fattura_data': {'numero': '123'}
        }
        
        download_id = save_temp_data(test_data)
        
        # Simula tempo appena prima della scadenza
        download_storage[download_id]['created_at'] = time.time() - (DOWNLOAD_TTL_SECONDS - 10)
        
        # Dovrebbe ancora essere caricabile
        loaded_data = load_temp_data(download_id)
        self.assertIsNotNone(loaded_data)
        self.assertEqual(loaded_data['filename'], 'test.pdf')
    
    def test_generate_invoice_filename(self):
        """Test generazione nome file fattura."""
        fattura_data = {
            'dati_generali': {
                'numero': '123/2024',
                'data': '2024-01-15'
            },
            'cedente': {
                'denominazione': 'Test S.r.l.'
            }
        }
        
        filename = generate_invoice_filename(fattura_data)
        self.assertIn('Fattura_123-2024', filename)
        self.assertIn('20240115', filename)
        self.assertIn('Test_Srl', filename)
        self.assertTrue(filename.endswith('.pdf'))
    
    def test_generate_invoice_filename_with_special_chars(self):
        """Test generazione nome file con caratteri speciali."""
        fattura_data = {
            'dati_generali': {
                'numero': '456',
                'data': '2024-03-20'
            },
            'cedente': {
                'denominazione': 'Società & Partners (Italia)!'
            }
        }
        
        filename = generate_invoice_filename(fattura_data)
        self.assertNotIn('&', filename)
        self.assertNotIn('(', filename)
        self.assertNotIn('!', filename)
    
    def test_download_endpoint_not_found(self):
        """Test endpoint download con ID inesistente o scaduto."""
        response = self.client.get('/api/download/pdf?download_id=invalid-id')
        self.assertEqual(response.status_code, 404)
        self.assertIn('non trovato', response.json()['detail'].lower())
    
    def test_download_endpoint_already_downloaded(self):
        """Test endpoint download con file già scaricato una volta."""
        test_data = {
            'type': 'single',
            'filename': 'test.xml',
            'xml_payload': b'<xml>test</xml>',
            'fattura_data': {
                'dati_generali': {'numero': '1', 'data': '2024-01-01'},
                'cedente': {'denominazione': 'Test'}
            },
            'pdf_bytes': b'%PDF-1.4 fake pdf content'
        }
        
        download_id = save_temp_data(test_data)
        
        # Primo download (dovrebbe funzionare)
        response1 = self.client.get(f'/api/download/pdf?download_id={download_id}')
        self.assertEqual(response1.status_code, 200)
        
        # Secondo download (dovrebbe fallire - già scaricato)
        time.sleep(0.1)  # Piccola pausa per permettere al sistema di processare
        response2 = self.client.get(f'/api/download/pdf?download_id={download_id}')
        self.assertEqual(response2.status_code, 404)
    
    def test_download_pdf_success(self):
        """Test download PDF singolo."""
        test_data = {
            'type': 'single',
            'filename': 'test.xml',
            'xml_payload': b'<xml>test</xml>',
            'fattura_data': {
                'dati_generali': {'numero': '1', 'data': '2024-01-01'},
                'cedente': {'denominazione': 'Test'}
            },
            'pdf_bytes': b'%PDF-1.4 fake pdf content'
        }
        
        download_id = save_temp_data(test_data)
        response = self.client.get(f'/api/download/pdf?download_id={download_id}')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'application/pdf')
        self.assertIn('attachment', response.headers['content-disposition'])
    
    def test_download_xml_success(self):
        """Test download XML singolo."""
        test_data = {
            'type': 'single_xml',
            'filename': 'test.xml',
            'xml_payload': b'<?xml version="1.0"?><root>test</root>'
        }
        
        download_id = save_temp_data(test_data)
        response = self.client.get(f'/api/download/xml?download_id={download_id}')
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/xml', response.headers['content-type'])
        self.assertIn('attachment', response.headers['content-disposition'])
    
    def test_download_batch_success(self):
        """Test download batch ZIP."""
        test_data = {
            'type': 'batch',
            'fatture': [
                {
                    'fattura_data': {
                        'dati_generali': {'numero': '1', 'data': '2024-01-01'},
                        'cedente': {'denominazione': 'Test1', 'partita_iva': '12345'},
                        'cessionario': {'denominazione': 'Cliente1'},
                        'riepilogo': [{'aliquota_iva': '22', 'imponibile': '100.00', 'imposta': '22.00'}],
                        'linee': []
                    },
                    'pdf_bytes': b'%PDF-1.4 fake pdf 1',
                    'xml_payload': b'<xml>test1</xml>'
                },
                {
                    'fattura_data': {
                        'dati_generali': {'numero': '2', 'data': '2024-01-02'},
                        'cedente': {'denominazione': 'Test2', 'partita_iva': '67890'},
                        'cessionario': {'denominazione': 'Cliente2'},
                        'riepilogo': [{'aliquota_iva': '10', 'imponibile': '50.00', 'imposta': '5.00'}],
                        'linee': []
                    },
                    'pdf_bytes': b'%PDF-1.4 fake pdf 2',
                    'xml_payload': b'<xml>test2</xml>'
                }
            ]
        }
        
        download_id = save_temp_data(test_data)
        response = self.client.get(f'/api/download/batch?download_id={download_id}')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'application/zip')
        self.assertIn('Fatture_', response.headers['content-disposition'])
    
    def test_download_wrong_type_for_data(self):
        """Test download con tipo sbagliato per i dati."""
        test_data = {
            'type': 'single_xml',
            'filename': 'test.xml',
            'xml_payload': b'<xml>test</xml>'
        }
        
        download_id = save_temp_data(test_data)
        response = self.client.get(f'/api/download/pdf?download_id={download_id}')
        
        self.assertEqual(response.status_code, 400)
        self.assertIn('non è un PDF', response.json()['detail'])
    
    def test_download_invalid_type(self):
        """Test download con tipo non valido."""
        test_data = {
            'type': 'single',
            'filename': 'test.xml',
            'xml_payload': b'<xml>test</xml>',
            'fattura_data': {'numero': '1'},
            'pdf_bytes': b'fake pdf'
        }
        
        download_id = save_temp_data(test_data)
        response = self.client.get(f'/api/download/invalid_type?download_id={download_id}')
        
        self.assertEqual(response.status_code, 400)
        self.assertIn('non valido', response.json()['detail'].lower())


if __name__ == '__main__':
    unittest.main()
