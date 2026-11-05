import sys
import os
from pathlib import Path

root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from p7m_decoder import P7MDecoder


class P7MProcessor:
    """Wrapper per il decoder P7M esistente."""
    
    def __init__(self):
        self.decoder = P7MDecoder()
    
    def process(self, content: bytes, filename: str) -> dict:
        """
        Elabora un file P7M e restituisce i risultati.
        
        Args:
            content: Contenuto del file in bytes
            filename: Nome del file originale
        
        Returns:
            Dizionario con i risultati dell'elaborazione
        """
        try:
            result = self.decoder.decode_file(content)
            
            if not result.get('success'):
                return {
                    'success': False,
                    'error': result.get('error', 'Errore sconosciuto durante la decodifica')
                }
            
            return {
                'success': True,
                'payload': result['payload'],
                'suggested_filename': result['suggested_filename'],
                'mime_type': result['mime_type'],
                'ext': result['ext'],
                'payload_size': result['payload_size'],
                'sha256': result['sha256'],
                'signer_info': result['signer_info'],
                'all_signers': result.get('all_signers', []),
                'signature_format': result.get('signature_format'),
                'error': result.get('error')
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Errore durante l\'elaborazione: {str(e)}'
            }
