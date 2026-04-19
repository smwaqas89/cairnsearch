"""Encryption manager for data at rest."""
import base64
import hashlib
import os
import secrets
from pathlib import Path
from typing import Optional, Union
import logging


logger = logging.getLogger(__name__)


class EncryptionManager:
    """
    Manages encryption for data at rest.
    
    Features:
    - AES-256 encryption
    - Key derivation from password
    - Secure key storage
    - File encryption/decryption
    """
    
    SALT_SIZE = 16
    KEY_SIZE = 32  # 256 bits
    NONCE_SIZE = 12
    TAG_SIZE = 16
    
    def __init__(self, key: Optional[bytes] = None, password: Optional[str] = None):
        """
        Initialize encryption manager.
        
        Args:
            key: Encryption key (32 bytes for AES-256)
            password: Password to derive key from
        """
        if key:
            self.key = key
        elif password:
            # Derive key from password using PBKDF2
            salt = self._get_or_create_salt()
            self.key = self._derive_key(password, salt)
        else:
            # Generate random key
            self.key = secrets.token_bytes(self.KEY_SIZE)
    
    def _get_or_create_salt(self) -> bytes:
        """Get or create salt for key derivation."""
        salt_file = Path.home() / ".local" / "share" / "cairnsearch" / ".salt"
        
        if salt_file.exists():
            return salt_file.read_bytes()
        
        salt_file.parent.mkdir(parents=True, exist_ok=True)
        salt = secrets.token_bytes(self.SALT_SIZE)
        salt_file.write_bytes(salt)
        
        # Set restrictive permissions
        os.chmod(salt_file, 0o600)
        
        return salt
    
    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive encryption key from password."""
        import hashlib
        
        # PBKDF2 with SHA-256
        return hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            iterations=100000,
            dklen=self.KEY_SIZE
        )
    
    def encrypt(self, data: Union[str, bytes]) -> bytes:
        """
        Encrypt data using AES-256-GCM.
        
        Args:
            data: Data to encrypt (string or bytes)
            
        Returns:
            Encrypted data with nonce prepended
        """
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            logger.warning("cryptography package not installed, using fallback")
            return self._encrypt_fallback(data)
        
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        # Generate random nonce
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        
        # Encrypt
        aesgcm = AESGCM(self.key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        
        # Return nonce + ciphertext
        return nonce + ciphertext
    
    def decrypt(self, encrypted_data: bytes) -> bytes:
        """
        Decrypt data encrypted with AES-256-GCM.
        
        Args:
            encrypted_data: Encrypted data with nonce prepended
            
        Returns:
            Decrypted data
        """
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            return self._decrypt_fallback(encrypted_data)
        
        # Extract nonce and ciphertext
        nonce = encrypted_data[:self.NONCE_SIZE]
        ciphertext = encrypted_data[self.NONCE_SIZE:]
        
        # Decrypt
        aesgcm = AESGCM(self.key)
        return aesgcm.decrypt(nonce, ciphertext, None)
    
    def _encrypt_fallback(self, data: Union[str, bytes]) -> bytes:
        """Fallback encryption using XOR (NOT secure, just for compatibility)."""
        logger.warning("Using insecure fallback encryption!")
        
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        # Simple XOR with key (NOT cryptographically secure)
        key_extended = (self.key * ((len(data) // len(self.key)) + 1))[:len(data)]
        encrypted = bytes(a ^ b for a, b in zip(data, key_extended))
        
        return b'FALLBACK:' + base64.b64encode(encrypted)
    
    def _decrypt_fallback(self, encrypted_data: bytes) -> bytes:
        """Fallback decryption."""
        if not encrypted_data.startswith(b'FALLBACK:'):
            raise ValueError("Not fallback encrypted data")
        
        encrypted = base64.b64decode(encrypted_data[9:])
        key_extended = (self.key * ((len(encrypted) // len(self.key)) + 1))[:len(encrypted)]
        
        return bytes(a ^ b for a, b in zip(encrypted, key_extended))
    
    def encrypt_file(self, input_path: Path, output_path: Optional[Path] = None) -> Path:
        """
        Encrypt a file.
        
        Args:
            input_path: Path to file to encrypt
            output_path: Output path (default: input_path + .enc)
            
        Returns:
            Path to encrypted file
        """
        input_path = Path(input_path)
        output_path = output_path or input_path.with_suffix(input_path.suffix + '.enc')
        
        data = input_path.read_bytes()
        encrypted = self.encrypt(data)
        output_path.write_bytes(encrypted)
        
        return output_path
    
    def decrypt_file(self, input_path: Path, output_path: Optional[Path] = None) -> Path:
        """
        Decrypt a file.
        
        Args:
            input_path: Path to encrypted file
            output_path: Output path (default: remove .enc suffix)
            
        Returns:
            Path to decrypted file
        """
        input_path = Path(input_path)
        
        if output_path is None:
            if input_path.suffix == '.enc':
                output_path = input_path.with_suffix('')
            else:
                output_path = input_path.with_suffix('.dec')
        
        encrypted = input_path.read_bytes()
        decrypted = self.decrypt(encrypted)
        output_path.write_bytes(decrypted)
        
        return output_path
    
    def encrypt_string(self, text: str) -> str:
        """Encrypt string and return base64-encoded result."""
        encrypted = self.encrypt(text)
        return base64.b64encode(encrypted).decode('ascii')
    
    def decrypt_string(self, encrypted_text: str) -> str:
        """Decrypt base64-encoded encrypted string."""
        encrypted = base64.b64decode(encrypted_text.encode('ascii'))
        return self.decrypt(encrypted).decode('utf-8')
    
    @staticmethod
    def generate_key() -> bytes:
        """Generate a new random encryption key."""
        return secrets.token_bytes(EncryptionManager.KEY_SIZE)
    
    @staticmethod
    def key_to_string(key: bytes) -> str:
        """Convert key to base64 string for storage."""
        return base64.b64encode(key).decode('ascii')
    
    @staticmethod
    def string_to_key(key_string: str) -> bytes:
        """Convert base64 string back to key."""
        return base64.b64decode(key_string.encode('ascii'))
