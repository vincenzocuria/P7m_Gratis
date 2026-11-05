import sys
import os
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.p7m_processor import P7MProcessor


class TestP7MProcessor(unittest.TestCase):
    """Test per il processore P7M."""
    
    def setUp(self):
        self.processor = P7MProcessor()
        self.fixtures_dir = Path(__file__).parent.parent.parent.parent / 'mobile' / 'test' / 'fixtures'
        self.samples_dir = Path(__file__).parent.parent.parent.parent / 'samples'
    
    def test_process_valid_p7m(self):
        """Test elaborazione di un file P7M valido."""
        fixture_path = self.fixtures_dir / 'valid.p7m'
        
        if not fixture_path.exists():
            self.skipTest(f"Fixture {fixture_path} non trovato")
        
        with open(fixture_path, 'rb') as f:
            content = f.read()
        
        result = self.processor.process(content, 'valid.p7m')
        
        self.assertTrue(result['success'])
        self.assertIn('payload', result)
        self.assertIsNotNone(result['payload'])
        self.assertIn('signer_info', result)
    
    def test_process_fattura_p7m(self):
        """Test elaborazione di una fattura elettronica."""
        fattura_path = self.samples_dir / 'fattura_FPA12.xml.p7m'
        
        if not fattura_path.exists():
            self.skipTest(f"Sample {fattura_path} non trovato")
        
        with open(fattura_path, 'rb') as f:
            content = f.read()
        
        result = self.processor.process(content, 'fattura_FPA12.xml.p7m')
        
        self.assertTrue(result['success'])
        self.assertEqual(result['mime_type'], 'text/xml')
        self.assertIn(b'FatturaElettronica', result['payload'][:1000])
    
    def test_process_nested_p7m(self):
        """Test elaborazione di file P7M annidato."""
        fixture_path = self.fixtures_dir / 'nested.p7m'
        
        if not fixture_path.exists():
            self.skipTest(f"Fixture {fixture_path} non trovato")
        
        with open(fixture_path, 'rb') as f:
            content = f.read()
        
        result = self.processor.process(content, 'nested.p7m')
        
        self.assertTrue(result['success'])
        self.assertIsNotNone(result['payload'])
    
    def test_process_invalid_file(self):
        """Test elaborazione di un file non P7M."""
        content = b'This is not a P7M file'
        
        result = self.processor.process(content, 'invalid.p7m')
        
        self.assertFalse(result['success'])
        self.assertIn('error', result)


if __name__ == '__main__':
    unittest.main()
