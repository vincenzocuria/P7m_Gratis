import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.rate_limiter import RateLimiter


class TestRateLimiter(unittest.TestCase):
    """Test per il rate limiter."""
    
    def test_rate_limit_allows_under_threshold(self):
        """Test che il rate limiter permette richieste sotto la soglia."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        
        for _ in range(5):
            self.assertTrue(limiter.check_rate_limit('127.0.0.1'))
    
    def test_rate_limit_blocks_over_threshold(self):
        """Test che il rate limiter blocca richieste oltre la soglia."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        
        for _ in range(3):
            self.assertTrue(limiter.check_rate_limit('127.0.0.1'))
        
        self.assertFalse(limiter.check_rate_limit('127.0.0.1'))
    
    def test_rate_limit_per_ip(self):
        """Test che il rate limiter è per IP."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        
        self.assertTrue(limiter.check_rate_limit('127.0.0.1'))
        self.assertTrue(limiter.check_rate_limit('127.0.0.1'))
        self.assertFalse(limiter.check_rate_limit('127.0.0.1'))
        
        self.assertTrue(limiter.check_rate_limit('192.168.1.1'))
        self.assertTrue(limiter.check_rate_limit('192.168.1.1'))
        self.assertFalse(limiter.check_rate_limit('192.168.1.1'))
    
    def test_cleanup(self):
        """Test pulizia delle entry vecchie."""
        limiter = RateLimiter(max_requests=5, window_seconds=1)
        
        limiter.check_rate_limit('127.0.0.1')
        self.assertIn('127.0.0.1', limiter.requests)
        
        import time
        time.sleep(1.1)
        
        limiter.cleanup()
        self.assertNotIn('127.0.0.1', limiter.requests)


if __name__ == '__main__':
    unittest.main()
