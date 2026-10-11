import time
from collections import defaultdict
from typing import Dict


class RateLimiter:
    """Rate limiter semplice basato su IP."""
    
    def __init__(self, max_requests: int = 20, window_seconds: int = 3600):
        """
        Inizializza il rate limiter.
        
        Args:
            max_requests: Numero massimo di richieste per finestra temporale
            window_seconds: Durata della finestra temporale in secondi (default: 1 ora)
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = defaultdict(list)
    
    def check_rate_limit(self, client_ip: str) -> bool:
        """
        Verifica se il client può fare una richiesta.
        
        Args:
            client_ip: Indirizzo IP del client
        
        Returns:
            True se la richiesta è permessa, False altrimenti
        """
        now = time.time()
        
        self.requests[client_ip] = [
            timestamp for timestamp in self.requests[client_ip]
            if now - timestamp < self.window_seconds
        ]
        
        if len(self.requests[client_ip]) >= self.max_requests:
            return False
        
        self.requests[client_ip].append(now)
        return True
    
    def cleanup(self):
        """Pulisce le entry vecchie."""
        now = time.time()
        to_delete = []
        
        for ip, timestamps in self.requests.items():
            self.requests[ip] = [
                timestamp for timestamp in timestamps
                if now - timestamp < self.window_seconds
            ]
            if not self.requests[ip]:
                to_delete.append(ip)
        
        for ip in to_delete:
            del self.requests[ip]
