#!/usr/bin/env python3
"""
ASTERISK MANAGER - Version Service System
Système de gestion professionnel avec création automatique des bases de données
"""

import os
import sys
import sqlite3
import hashlib
import hmac
import subprocess
import time
from datetime import datetime, timedelta
import string
import random
import getpass

# =============================================================================
# CONFIGURATION GLOBALE
# =============================================================================

class Config:
    DB_PATH = "/home/vps/asterisk/asterisk.db"
    SECRET_SEED = "asterisk_secure_deterministic_v1"
    ASTERISK_CONFIG_DIR = "/etc/asterisk"
    VENV_PATH = "/home/vps/asterisk"
    
    # Configuration des extensions
    EXTENSION_PREFIX = "601"
    EXTENSION_LENGTH = 9

# =============================================================================
# SYSTÈME D'AFFICHAGE FORCÉ
# =============================================================================

class Terminal:
    """Gestionnaire d'affichage terminal avec flush forcé"""
    
    @staticmethod
    def print(message, end='\n', flush=True):
        sys.stdout.write(message + end)
        if flush:
            sys.stdout.flush()
    
    @staticmethod
    def input(prompt):
        Terminal.print(prompt, end='', flush=True)
        return sys.stdin.readline().strip()
    
    @staticmethod
    def clear():
        os.system('clear')
        sys.stdout.flush()
    
    @staticmethod
    def getpass(prompt):
        """Saisie masquée pour les codes d'accès"""
        return getpass.getpass(prompt)

class Logger:
    """Système de logging avec affichage forcé"""
    
    @staticmethod
    def info(message):
        Terminal.print(f"ℹ️  {message}")
    
    @staticmethod
    def success(message):
        Terminal.print(f"✅ {message}")
    
    @staticmethod
    def error(message):
        Terminal.print(f"❌ {message}")
    
    @staticmethod
    def warning(message):
        Terminal.print(f"⚠️  {message}")
    
    @staticmethod
    def debug(message):
        Terminal.print(f"🔍 {message}")
    
    @staticmethod
    def title(message):
        Terminal.print(f"\n🎯 {message}")
        Terminal.print("=" * 60)

# =============================================================================
# GESTIONNAIRE DE BASES DE DONNÉES - CRÉATION AUTOMATIQUE
# =============================================================================

class DatabaseManager:
    """Gestionnaire complet des bases de données avec création automatique"""
    
    @staticmethod
    def ensure_all_databases():
        """Vérifier et créer toutes les bases de données si elles n'existent pas"""
        Logger.info("Vérification des bases de données...")
        
        databases = [
            ("Base principale", DatabaseManager._ensure_main_database),
            ("Codes d'accès", DatabaseManager._ensure_access_codes_database),
            ("Logs système", DatabaseManager._ensure_system_logs_database),
            ("CDR", DatabaseManager._ensure_cdr_database),
            ("Configuration", DatabaseManager._ensure_config_database),
        ]
        
        for db_name, db_function in databases:
            if db_function():
                Logger.success(f"{db_name} - OK")
            else:
                Logger.error(f"{db_name} - ÉCHEC")
        
        return True
    
    @staticmethod
    def _ensure_main_database():
        """Créer la base de données principale si elle n'existe pas"""
        try:
            db_path = Config.DB_PATH
            db_dir = os.path.dirname(db_path)
            
            # Créer le répertoire si nécessaire
            if not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
                Logger.info(f"Répertoire créé: {db_dir}")
            
            Logger.info("Création de la base de données principale...")
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Table des utilisateurs
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    context TEXT DEFAULT "from-internal",
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table des codes d'accès
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS access_codes (
                    id INTEGER PRIMARY KEY,
                    code TEXT UNIQUE NOT NULL,
                    month_year TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table du statut système
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_status (
                    id INTEGER PRIMARY KEY,
                    asterisk_running INTEGER DEFAULT 0,
                    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Données initiales
            cursor.execute('INSERT OR IGNORE INTO system_status (id, asterisk_running) VALUES (1, 0)')
            
            # GÉNÉRATION AUTOMATIQUE DU CODE D'ACCÈS DÈS LA CRÉATION
            current_date = datetime.now()
            month_year = f"{current_date.month:02d}-{current_date.year}"
            
            code_generator = DeterministicCodeGenerator()
            current_code = code_generator.get_current_code()
            
            if current_date.month == 12:
                next_month = datetime(current_date.year + 1, 1, 1)
            else:
                next_month = datetime(current_date.year, current_date.month + 1, 1)
            
            expires_at = next_month - timedelta(days=1)
            expires_at = expires_at.replace(hour=23, minute=59, second=59)
            
            cursor.execute('''
                INSERT OR REPLACE INTO access_codes (id, code, month_year, expires_at, is_active)
                VALUES (1, ?, ?, ?, 1)
            ''', (current_code, month_year, expires_at))
            
            conn.commit()
            conn.close()
            
            # Permissions
            os.chmod(db_path, 0o644)
            Logger.info("Base principale créée avec succès")
            Logger.info(f"🔐 Code d'accès généré automatiquement pour {month_year} et stocké en base")
            return True
            
        except Exception as e:
            Logger.error(f"Erreur création base principale: {e}")
            return False
    
    @staticmethod
    def _ensure_access_codes_database():
        """Créer la base des codes d'accès si elle n'existe pas"""
        try:
            db_path = "/home/vps/asterisk/access_codes.db"
            db_dir = os.path.dirname(db_path)
            
            if not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            
            if os.path.exists(db_path):
                Logger.debug("Base codes d'accès existe déjà")
                return True
            
            Logger.info("Création de la base des codes d'accès...")
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS access_codes_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    month_year TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS access_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code_attempt TEXT NOT NULL,
                    success INTEGER DEFAULT 0,
                    ip_address TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            os.chmod(db_path, 0o644)
            Logger.info("Base codes d'accès créée avec succès")
            return True
            
        except Exception as e:
            Logger.error(f"Erreur création base codes accès: {e}")
            return False
    
    @staticmethod
    def _ensure_system_logs_database():
        """Créer la base des logs système si elle n'existe pas"""
        try:
            db_path = "/home/vps/asterisk/system_logs.db"
            db_dir = os.path.dirname(db_path)
            
            if not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            
            if os.path.exists(db_path):
                Logger.debug("Base logs système existe déjà")
                return True
            
            Logger.info("Création de la base des logs système...")
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    module TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS error_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    resolved INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            os.chmod(db_path, 0o644)
            Logger.info("Base logs système créée avec succès")
            return True
            
        except Exception as e:
            Logger.error(f"Erreur création base logs système: {e}")
            return False
    
    @staticmethod
    def _ensure_cdr_database():
        """Créer la base CDR si elle n'existe pas"""
        try:
            db_path = "/home/vps/asterisk/cdr.db"
            db_dir = os.path.dirname(db_path)
            
            if not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            
            if os.path.exists(db_path):
                Logger.debug("Base CDR existe déjà")
                return True
            
            Logger.info("Création de la base CDR...")
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cdr (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    calldate TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    src TEXT NOT NULL,
                    dst TEXT NOT NULL,
                    duration INTEGER DEFAULT 0,
                    disposition TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            os.chmod(db_path, 0o644)
            Logger.info("Base CDR créée avec succès")
            return True
            
        except Exception as e:
            Logger.error(f"Erreur création base CDR: {e}")
            return False
    
    @staticmethod
    def _ensure_config_database():
        """Créer la base de configuration si elle n'existe pas"""
        try:
            db_path = "/home/vps/asterisk/config.db"
            db_dir = os.path.dirname(db_path)
            
            if not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            
            if os.path.exists(db_path):
                Logger.debug("Base configuration existe déjà")
                return True
            
            Logger.info("Création de la base de configuration...")
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    description TEXT
                )
            ''')
            
            # Paramètres par défaut
            default_settings = [
                ('max_users', '100', 'Nombre maximum d utilisateurs'),
                ('auto_backup', '1', 'Sauvegarde automatique'),
                ('log_retention_days', '30', 'Rétention des logs'),
            ]
            
            for key, value, description in default_settings:
                cursor.execute('''
                    INSERT OR IGNORE INTO system_settings (key, value, description)
                    VALUES (?, ?, ?)
                ''', (key, value, description))
            
            conn.commit()
            conn.close()
            os.chmod(db_path, 0o644)
            Logger.info("Base configuration créée avec succès")
            return True
            
        except Exception as e:
            Logger.error(f"Erreur création base configuration: {e}")
            return False

    @staticmethod
    def get_current_access_code():
        """Récupérer le code d'accès actuel depuis la base de données"""
        try:
            conn = sqlite3.connect(Config.DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT code, month_year, expires_at FROM access_codes 
                WHERE id = 1 AND is_active = 1
            ''')
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'code': result[0],
                    'month_year': result[1],
                    'expires_at': datetime.strptime(result[2], '%Y-%m-%d %H:%M:%S') if isinstance(result[2], str) else result[2]
                }
            return None
            
        except Exception as e:
            Logger.error(f"Erreur récupération code accès: {e}")
            return None

    @staticmethod
    def update_access_code(new_code, month_year, expires_at):
        """Mettre à jour le code d'accès dans la base de données"""
        try:
            conn = sqlite3.connect(Config.DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE access_codes 
                SET code = ?, month_year = ?, expires_at = ?, created_at = CURRENT_TIMESTAMP
                WHERE id = 1
            ''', (new_code, month_year, expires_at))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            Logger.error(f"Erreur mise à jour code accès: {e}")
            return False

# =============================================================================
# INSTALLATEUR AUTOMATIQUE SYSTÈME
# =============================================================================

class SystemInstaller:
    """Installateur automatique avec création des bases de données"""
    
    @staticmethod
    def check_and_install_packages():
        """Vérifier et installer les paquets nécessaires"""
        Logger.info("Vérification des paquets système...")
        
        required_packages = {
            'asterisk': 'Asterisk PBX',
            'sqlite3': 'Base de données SQLite',
        }
        
        missing_packages = []
        
        for package, description in required_packages.items():
            try:
                result = subprocess.run(
                    ['dpkg', '-l', package], 
                    capture_output=True, 
                    text=True
                )
                if result.returncode != 0:
                    missing_packages.append((package, description))
                    Logger.warning(f"{package} ({description}) - Manquant")
                else:
                    Logger.success(f"{package} ({description}) - Installé")
            except Exception as e:
                Logger.error(f"Erreur vérification {package}: {e}")
        
        if missing_packages:
            Logger.info(f"Installation de {len(missing_packages)} paquet(s) manquant(s)...")
            return SystemInstaller.install_packages(missing_packages)
        else:
            Logger.success("Tous les paquets nécessaires sont installés")
            return True
    
    @staticmethod
    def install_packages(missing_packages):
        """Installer les paquets manquants"""
        try:
            Logger.info("Mise à jour des dépôts...")
            subprocess.run(['apt', 'update'], check=True, capture_output=True)
            
            packages_to_install = [pkg[0] for pkg in missing_packages]
            Logger.info(f"Installation: {', '.join(packages_to_install)}")
            
            subprocess.run(
                ['apt', 'install', '-y'] + packages_to_install,
                check=True,
                capture_output=True
            )
            
            Logger.success("Tous les paquets installés avec succès")
            return True
            
        except subprocess.CalledProcessError as e:
            Logger.error(f"Erreur lors de l'installation: {e}")
            return False
        except Exception as e:
            Logger.error(f"Erreur inattendue: {e}")
            return False
    
    @staticmethod
    def configure_firewall_alternative():
        """Configuration alternative du firewall"""
        Logger.info("Configuration du firewall avec iptables...")
        
        try:
            # Règles iptables pour Asterisk
            iptables_rules = [
                ['iptables', '-A', 'INPUT', '-p', 'tcp', '--dport', '5060', '-j', 'ACCEPT'],
                ['iptables', '-A', 'INPUT', '-p', 'udp', '--dport', '5060', '-j', 'ACCEPT'],
                ['iptables', '-A', 'INPUT', '-p', 'tcp', '--dport', '5061', '-j', 'ACCEPT'],
                ['iptables', '-A', 'INPUT', '-p', 'udp', '--dport', '5061', '-j', 'ACCEPT'],
                ['iptables', '-A', 'INPUT', '-p', 'udp', '--dport', '10000:20000', '-j', 'ACCEPT'],
                ['iptables', '-A', 'INPUT', '-p', 'tcp', '--dport', '5038', '-j', 'ACCEPT'],
            ]
            
            for rule in iptables_rules:
                try:
                    subprocess.run(rule, check=True, capture_output=True)
                    Logger.success(f"Règle ajoutée: {' '.join(rule)}")
                except subprocess.CalledProcessError:
                    Logger.warning(f"Impossible d'ajouter la règle: {' '.join(rule)}")
            
            return True
            
        except Exception as e:
            Logger.error(f"Erreur configuration firewall: {e}")
            return False
    
    @staticmethod
    def setup_asterisk():
        """Configuration d'Asterisk avec service systemd"""
        Logger.info("Configuration du service Asterisk...")
        
        try:
            # Créer les répertoires nécessaires
            directories = [
                '/etc/asterisk',
                '/var/log/asterisk', 
                '/var/run/asterisk',
                '/var/spool/asterisk',
                '/var/lib/asterisk'
            ]
            
            for directory in directories:
                os.makedirs(directory, exist_ok=True)
            
            # Configuration minimale d'Asterisk
            basic_config = """
[directories]
astetcdir => /etc/asterisk
astmoddir => /usr/lib/asterisk/modules
astvarlibdir => /var/lib/asterisk
astdbdir => /var/lib/asterisk
astkeydir => /var/lib/asterisk
astdatadir => /var/lib/asterisk
astagidir => /var/lib/asterisk/agi-bin
astspooldir => /var/spool/asterisk
astrundir => /var/run/asterisk
astlogdir => /var/log/asterisk

[options]
verbose = 3
debug = 0
maxfiles = 100000
"""
            
            with open('/etc/asterisk/asterisk.conf', 'w') as f:
                f.write(basic_config)
            
            # Redémarrer et activer le service Asterisk
            subprocess.run(['systemctl', 'daemon-reload'], check=True, capture_output=True)
            subprocess.run(['systemctl', 'enable', 'asterisk'], check=True, capture_output=True)
            subprocess.run(['systemctl', 'start', 'asterisk'], check=True, capture_output=True)
            
            time.sleep(3)
            
            # Vérifier le statut du service
            result = subprocess.run(['systemctl', 'is-active', 'asterisk'], capture_output=True, text=True)
            if result.returncode == 0:
                Logger.success("Service Asterisk configuré et démarré avec succès")
                return True
            else:
                Logger.error("Service Asterisk non actif")
                return False
            
        except Exception as e:
            Logger.error(f"Erreur configuration Asterisk: {e}")
            return False
    
    @staticmethod
    def full_system_install():
        """Installation complète du système"""
        Logger.title("INSTALLATION AUTOMATIQUE DU SYSTÈME")
        
        steps = [
            ("Vérification des paquets", SystemInstaller.check_and_install_packages),
            ("Configuration du firewall", SystemInstaller.configure_firewall_alternative),
            ("Configuration d'Asterisk", SystemInstaller.setup_asterisk),
            ("Création des bases de données", DatabaseManager.ensure_all_databases)
        ]
        
        for step_name, step_function in steps:
            Logger.info(f"{step_name}...")
            if step_function():
                Logger.success(f"{step_name} - TERMINÉ")
            else:
                Logger.warning(f"{step_name} - ÉCHEC PARTIEL")
            
            time.sleep(2)
        
        Logger.success("INSTALLATION TERMINÉE!")
        return True

# =============================================================================
# VÉRIFICATEUR SYSTÈME
# =============================================================================

class SystemChecker:
    """Vérificateur de l'état du système"""
    
    @staticmethod
    def check_system_requirements():
        """Vérifier les prérequis système"""
        Logger.info("Diagnostic du système...")
        
        checks = [
            ("Système Linux", SystemChecker._check_linux),
            ("Privilèges root", SystemChecker._check_root),
            ("Paquet Asterisk", SystemChecker._check_asterisk_package),
            ("Bases de données", SystemChecker._check_databases),
            ("Service Asterisk", SystemChecker._check_asterisk_service),
        ]
        
        for check_name, check_function in checks:
            if check_function():
                Logger.success(check_name)
            else:
                Logger.warning(check_name)
        
        return True
    
    @staticmethod
    def _check_linux():
        return sys.platform.startswith('linux')
    
    @staticmethod
    def _check_root():
        return os.geteuid() == 0
    
    @staticmethod
    def _check_asterisk_package():
        try:
            result = subprocess.run(['dpkg', '-l', 'asterisk'], capture_output=True, text=True)
            return result.returncode == 0
        except:
            return False
    
    @staticmethod
    def _check_databases():
        """Vérifier que les bases de données existent"""
        databases = [
            Config.DB_PATH,
            "/home/vps/asterisk/access_codes.db",
            "/home/vps/asterisk/system_logs.db",
            "/home/vps/asterisk/cdr.db",
            "/home/vps/asterisk/config.db"
        ]
        
        for db_path in databases:
            if not os.path.exists(db_path):
                return False
        return True
    
    @staticmethod
    def _check_asterisk_service():
        try:
            result = subprocess.run(['systemctl', 'is-active', 'asterisk'], 
                                  capture_output=True, text=True)
            return result.returncode == 0
        except:
            return False

# =============================================================================
# GESTIONNAIRE ASTERISK
# =============================================================================

class AsteriskManager:
    """Gestionnaire Asterisk avec service systemd"""
    
    @staticmethod
    def is_running():
        try:
            result = subprocess.run(['systemctl', 'is-active', 'asterisk'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except:
            return False
    
    @staticmethod
    def start():
        Logger.info("Démarrage du service Asterisk...")
        try:
            result = subprocess.run(['service', 'asterisk', 'start'], 
                                  capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                for i in range(10):
                    time.sleep(1)
                    if AsteriskManager.is_running():
                        Logger.success("Service Asterisk démarré avec succès")
                        return True
                return True
            else:
                Logger.error(f"Échec du démarrage: {result.stderr}")
                return False
                
        except Exception as e:
            Logger.error(f"Erreur démarrage: {e}")
            return False
    
    @staticmethod
    def stop():
        Logger.info("Arrêt du service Asterisk...")
        try:
            result = subprocess.run(['service', 'asterisk', 'stop'], 
                                  capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                for i in range(10):
                    time.sleep(1)
                    if not AsteriskManager.is_running():
                        Logger.success("Service Asterisk arrêté avec succès")
                        return True
                return True
            else:
                Logger.error(f"Échec de l'arrêt: {result.stderr}")
                return False
                
        except Exception as e:
            Logger.error(f"Erreur arrêt: {e}")
            return False
    
    @staticmethod
    def restart():
        Logger.info("Redémarrage du service Asterisk...")
        try:
            result = subprocess.run(['service', 'asterisk', 'restart'], 
                                  capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                for i in range(10):
                    time.sleep(1)
                    if AsteriskManager.is_running():
                        Logger.success("Service Asterisk redémarré avec succès")
                        return True
                return True
            else:
                Logger.error(f"Échec du redémarrage: {result.stderr}")
                return False
                
        except Exception as e:
            Logger.error(f"Erreur redémarrage: {e}")
            return False
    
    @staticmethod
    def reload():
        Logger.info("Rechargement de la configuration Asterisk...")
        try:
            result = subprocess.run(['service', 'asterisk', 'reload'], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                Logger.success("Configuration Asterisk rechargée")
                return True
            else:
                Logger.error(f"Échec rechargement: {result.stderr}")
                return False
                
        except Exception as e:
            Logger.error(f"Erreur rechargement: {e}")
            return False

# =============================================================================
# ALGORITHME DÉTERMINISTE COMMUN
# =============================================================================

class DeterministicCodeGenerator:
    """Générateur déterministe de codes"""
    
    def __init__(self, secret_seed=Config.SECRET_SEED):
        self.secret_seed = secret_seed
        self.month_names = {
            1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
            5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août", 
            9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
        }
    
    def get_current_period(self):
        current_date = datetime.now()
        return f"{current_date.month:02d}-{current_date.year}"
    
    def generate_deterministic_code(self, month_year=None, length=8):
        if month_year is None:
            month_year = self.get_current_period()
        
        hmac_obj = hmac.new(
            self.secret_seed.encode('utf-8'),
            month_year.encode('utf-8'),
            hashlib.sha256
        )
        
        hash_bytes = hmac_obj.digest()
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        code_chars = []
        
        for i in range(length):
            byte_val = hash_bytes[i % len(hash_bytes)] + i
            code_chars.append(chars[byte_val % len(chars)])
        
        return ''.join(code_chars)
    
    def get_current_code(self):
        month_year = self.get_current_period()
        return self.generate_deterministic_code(month_year)

# =============================================================================
# GESTIONNAIRE DE CODES MASQUÉS
# =============================================================================

class HiddenAccessCodeManager(DeterministicCodeGenerator):
    
    def __init__(self):
        super().__init__(Config.SECRET_SEED)
    
    def get_current_code_with_expiry(self):
        current_date = datetime.now()
        month_year = self.get_current_period()
        code = self.get_current_code()
        
        if current_date.month == 12:
            next_month = datetime(current_date.year + 1, 1, 1)
        else:
            next_month = datetime(current_date.year, current_date.month + 1, 1)
        
        expires_at = next_month - timedelta(days=1)
        expires_at = expires_at.replace(hour=23, minute=59, second=59)
        
        return code, expires_at
    
    def display_code_status(self):
        """Afficher le statut du code sans révéler le code"""
        current_date = datetime.now()
        code_data = DatabaseManager.get_current_access_code()
        
        if not code_data:
            Terminal.print("❌ Aucun code d'accès trouvé")
            return None, None
        
        code = code_data['code']
        expires_at = code_data['expires_at']
        month_year = code_data['month_year']
        
        days_remaining = (expires_at - current_date).days
        month_num = int(month_year.split('-')[0])
        month_name = self.month_names.get(month_num, "Inconnu")
        year = month_year.split('-')[1]
        
        Terminal.print(f"🔐 Code d'accès {month_name} {year}: *** MASQUÉ ***")
        Terminal.print(f"   Expire le: {expires_at.strftime('%d/%m/%Y')}")
        Terminal.print(f"   Jours restants: {days_remaining}")
        
        return code, expires_at
    
    def validate_code(self, input_code):
        expected_code_data = DatabaseManager.get_current_access_code()
        if not expected_code_data:
            return False
        
        expected_code = expected_code_data['code']
        return input_code == expected_code
    
    def is_code_expired(self):
        code_data = DatabaseManager.get_current_access_code()
        if not code_data:
            return True
        
        expires_at = code_data['expires_at']
        return datetime.now() > expires_at

# =============================================================================
# SYSTÈME DE VALIDATION DE CODE D'ACCÈS
# =============================================================================

class AccessValidator:
    """Système de validation de code d'accès répétitif"""
    
    def __init__(self):
        self.code_manager = HiddenAccessCodeManager()
        self.asterisk_manager = AsteriskManager()
        self.max_attempts = 3
    
    def check_and_validate_access(self):
        """Vérifier et valider l'accès avec système répétitif"""
        Terminal.clear()
        Terminal.print("╔══════════════════════════════════════════════════════════════╗")
        Terminal.print("║                   ASTERISK MANAGER - V2.0                   ║")
        Terminal.print("║          Système de validation par code d'accès             ║")
        Terminal.print("╚══════════════════════════════════════════════════════════════╝")
        Terminal.print("")
        
        # Vérifier si le code a expiré
        if self.code_manager.is_code_expired():
            return self._handle_expired_code()
        else:
            return self._validate_current_code()
    
    def _handle_expired_code(self):
        """Gérer le cas où le code a expiré"""
        Terminal.print("🔒 CODE D'ACCÈS EXPIRÉ!")
        Terminal.print("Le système est bloqué jusqu'à la saisie du nouveau code mensuel.")
        Terminal.print("")
        
        # Arrêter Asterisk pour bloquer le système
        self.asterisk_manager.stop()
        
        # Générer et stocker le nouveau code
        current_date = datetime.now()
        month_year = self.code_manager.get_current_period()
        new_code = self.code_manager.get_current_code()
        
        if current_date.month == 12:
            next_month = datetime(current_date.year + 1, 1, 1)
        else:
            next_month = datetime(current_date.year, current_date.month + 1, 1)
        
        expires_at = next_month - timedelta(days=1)
        expires_at = expires_at.replace(hour=23, minute=59, second=59)
        
        # Mettre à jour la base de données
        DatabaseManager.update_access_code(new_code, month_year, expires_at)
        
        month_name = self.code_manager.month_names[current_date.month]
        Terminal.print(f"📅 Nouveau code généré pour {month_name} {current_date.year}")
        Terminal.print("🔐 Veuillez saisir le nouveau code d'accès:")
        
        return self._prompt_for_code(unlimited_attempts=True)
    
    def _validate_current_code(self):
        """Valider le code actuel"""
        code_data = DatabaseManager.get_current_access_code()
        if not code_data:
            Terminal.print("❌ Erreur: Aucun code d'accès trouvé")
            return False
        
        month_year = code_data['month_year']
        month_num = int(month_year.split('-')[0])
        month_name = self.code_manager.month_names.get(month_num, "Inconnu")
        year = month_year.split('-')[1]
        
        Terminal.print(f"📅 Période: {month_name} {year}")
        Terminal.print("🔐 Veuillez saisir le code d'accès pour continuer:")
        
        return self._prompt_for_code(unlimited_attempts=False)
    
    def _prompt_for_code(self, unlimited_attempts=False):
        """Demander le code à l'utilisateur"""
        attempts = 0
        max_attempts = 9999 if unlimited_attempts else self.max_attempts
        
        while attempts < max_attempts:
            try:
                entered_code = Terminal.getpass("Code d'accès: ").strip().upper()
                attempts += 1
                
                if self.code_manager.validate_code(entered_code):
                    Terminal.print("✅ Code correct! Accès autorisé...")
                    
                    if unlimited_attempts:
                        # Redémarrer Asterisk si on était en mode expiré
                        if self.asterisk_manager.start():
                            Terminal.print("✅ Système débloqué et Asterisk redémarré")
                        else:
                            Terminal.print("❌ Erreur lors du redémarrage d'Asterisk")
                    
                    time.sleep(1)
                    return True
                else:
                    remaining_attempts = max_attempts - attempts
                    if remaining_attempts > 0:
                        Terminal.print(f"❌ Code incorrect. Il vous reste {remaining_attempts} tentative(s).")
                    else:
                        Terminal.print("❌ Trop de tentatives échouées. Accès refusé.")
                        return False
                        
            except KeyboardInterrupt:
                Terminal.print("\n❌ Saisie annulée. Accès refusé.")
                return False
        
        return False

# =============================================================================
# GESTIONNAIRE D'UTILISATEURS
# =============================================================================

class UserManager:
    
    def __init__(self):
        # S'assurer que la base existe
        DatabaseManager._ensure_main_database()
    
    def generate_phone_number(self):
        try:
            conn = sqlite3.connect(Config.DB_PATH)
            cursor = conn.cursor()
            
            while True:
                random_digits = ''.join(random.choice(string.digits) for _ in range(6))
                phone_number = f"{Config.EXTENSION_PREFIX}{random_digits}"
                
                cursor.execute("SELECT id FROM users WHERE numero = ?", (phone_number,))
                if not cursor.fetchone():
                    conn.close()
                    return phone_number
                    
        except Exception as e:
            Logger.error(f"Erreur génération numéro: {e}")
            return None
    
    def add_user(self, password, context="from-internal"):
        try:
            phone_number = self.generate_phone_number()
            if not phone_number:
                return False
            
            conn = sqlite3.connect(Config.DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute(
                "INSERT INTO users (numero, password, context) VALUES (?, ?, ?)",
                (phone_number, password, context)
            )
            
            conn.commit()
            conn.close()
            
            Logger.success(f"Utilisateur ajouté: {phone_number}")
            return phone_number
            
        except Exception as e:
            Logger.error(f"Erreur ajout utilisateur: {e}")
            return False
    
    def list_users(self):
        try:
            conn = sqlite3.connect(Config.DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("SELECT numero, context, created_at FROM users ORDER BY created_at DESC")
            users = cursor.fetchall()
            
            conn.close()
            return users
            
        except Exception as e:
            Logger.error(f"Erreur liste utilisateurs: {e}")
            return []
    
    def delete_user(self, phone_number):
        try:
            conn = sqlite3.connect(Config.DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM users WHERE numero = ?", (phone_number,))
            conn.commit()
            conn.close()
            
            Logger.success(f"Utilisateur {phone_number} supprimé")
            return True
            
        except Exception as e:
            Logger.error(f"Erreur suppression utilisateur: {e}")
            return False

# =============================================================================
# CONFIGURATEUR ASTERISK
# =============================================================================

class AsteriskConfigurator:
    
    def __init__(self):
        self.user_manager = UserManager()
    
    def configure_asterisk(self):
        Logger.info("Configuration d'Asterisk en cours...")
        
        try:
            os.makedirs(Config.ASTERISK_CONFIG_DIR, exist_ok=True)
            
            self._create_pjsip_config()
            self._create_extensions_config()
            
            AsteriskManager.reload()
            
            Logger.success("Configuration Asterisk terminée")
            return True
            
        except Exception as e:
            Logger.error(f"Erreur configuration Asterisk: {e}")
            return False
    
    def _create_pjsip_config(self):
        pjsip_conf = """
[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:5060

[transport-tcp]
type=transport
protocol=tcp
bind=0.0.0.0:5060

; Template pour les endpoints
[endpoint-template](!)
type=endpoint
context=from-internal
disallow=all
allow=ulaw,alaw,g722
transport=transport-udp
force_rport=yes
rewrite_contact=yes
direct_media=no

; Template pour l'authentification
[auth-template](!)
type=auth
auth_type=userpass

; Template pour les AOR
[aor-template](!)
type=aor
max_contacts=1
remove_existing=yes

"""
        
        users = self.user_manager.list_users()
        for user in users:
            phone_number, context, _ = user
            pjsip_conf += f"""
; Configuration pour {phone_number}
[{phone_number}]
type=endpoint
context=from-internal
disallow=all
allow=ulaw,alaw,g722
auth={phone_number}
aors={phone_number}
transport=transport-udp
force_rport=yes
rewrite_contact=yes
direct_media=no

[{phone_number}]
type=auth
auth_type=userpass
password={phone_number}
username={phone_number}

[{phone_number}]
type=aor
max_contacts=1
remove_existing=yes

"""
        
        with open(os.path.join(Config.ASTERISK_CONFIG_DIR, "pjsip.conf"), "w") as f:
            f.write(pjsip_conf)
    
    def _create_extensions_config(self):
        extensions_conf = """
[general]
static=yes
writeprotect=no

[from-internal]
exten => _6XXX,1,NoOp(Appel de ${CALLERID(num)} vers ${EXTEN})
same => n,Dial(PJSIP/${EXTEN},30)
same => n,Hangup()

; Test vocal
exten => 1000,1,Answer()
same => n,Playback(hello)
same => n,Hangup()

; Utilisateurs générés automatiquement
"""
        
        users = self.user_manager.list_users()
        for user in users:
            phone_number, context, _ = user
            extensions_conf += f"exten => {phone_number},1,Dial(PJSIP/{phone_number})\n"
        
        with open(os.path.join(Config.ASTERISK_CONFIG_DIR, "extensions.conf"), "w") as f:
            f.write(extensions_conf)

# =============================================================================
# INTERFACE UTILISATEUR COMPLÈTE
# =============================================================================

class CompleteMenuManager:
    
    def __init__(self):
        self.code_manager = HiddenAccessCodeManager()
        self.user_manager = UserManager()
        self.asterisk_manager = AsteriskManager()
        self.configurator = AsteriskConfigurator()
        self.access_validator = AccessValidator()
    
    def show_header(self):
        Terminal.clear()
        Terminal.print("╔══════════════════════════════════════════════════════════════╗")
        Terminal.print("║              ASTERISK MANAGER - SERVICE SYSTEMD             ║")
        Terminal.print("║          Système de validation par code d'accès             ║")
        Terminal.print("╚══════════════════════════════════════════════════════════════╝")
        Terminal.print("")
    
    def main_menu(self):
        # VALIDATION OBLIGATOIRE DU CODE D'ACCÈS AVANT LE MENU
        if not self.access_validator.check_and_validate_access():
            Terminal.print("❌ Accès refusé. Le système reste bloqué.")
            sys.exit(1)
        
        # Menu principal après validation réussie
        while True:
            self.show_header()
            
            status = "✅ EN COURS" if self.asterisk_manager.is_running() else "❌ ARRÊTÉ"
            Terminal.print(f"Statut Asterisk: {status}")
            
            self.code_manager.display_code_status()
            
            users = self.user_manager.list_users()
            Terminal.print(f"Utilisateurs configurés: {len(users)}")
            
            Terminal.print(f"\nMENU PRINCIPAL:")
            Terminal.print("1. 🔧 Configuration Asterisk Automatique")
            Terminal.print("2. 👥 Gestion des utilisateurs")
            Terminal.print("3. 📞 Gestion des numéros 601")
            Terminal.print("4. 🚀 Contrôle Asterisk (Start/Stop/Restart)")
            Terminal.print("5. 🔐 Gestion des codes d'accès")
            Terminal.print("6. 🔍 Vérification système")
            Terminal.print("7. ⚙️  Installation/Réparation système")
            Terminal.print("8. 🗄️  Gestion des bases de données")
            Terminal.print("9. 🔄 Revalider le code d'accès")
            Terminal.print("0. 🚪 Quitter")
            
            choice = Terminal.input("\nVotre choix: ")
            
            if choice == "1":
                self.configuration_menu()
            elif choice == "2":
                self.users_menu()
            elif choice == "3":
                self.numbers_menu()
            elif choice == "4":
                self.asterisk_control_menu()
            elif choice == "5":
                self.access_codes_menu()
            elif choice == "6":
                self.system_check_menu()
            elif choice == "7":
                self.system_install_menu()
            elif choice == "8":
                self.database_management_menu()
            elif choice == "9":
                # Revalidation du code
                if not self.access_validator.check_and_validate_access():
                    Terminal.print("❌ Revalidation échouée. Retour au menu principal.")
                    Terminal.input("Appuyez sur Entrée pour continuer...")
            elif choice == "0":
                Terminal.print("Au revoir!")
                sys.exit(0)
            else:
                Terminal.print("❌ Choix invalide")
                Terminal.input("Appuyez sur Entrée pour continuer...")
    
    def configuration_menu(self):
        self.show_header()
        Terminal.print("🔧 CONFIGURATION ASTERISK AUTOMATIQUE")
        Terminal.print("")
        
        Terminal.print("Cette configuration va:")
        Terminal.print("✅ Créer les fichiers de configuration Asterisk")
        Terminal.print("✅ Configurer les utilisateurs existants")
        Terminal.print("✅ Recharger la configuration Asterisk")
        Terminal.print("")
        
        confirm = Terminal.input("Confirmer la configuration? (o/N): ").strip().lower()
        
        if confirm == 'o' or confirm == 'oui':
            if self.configurator.configure_asterisk():
                Terminal.print("✅ Configuration terminée avec succès")
            else:
                Terminal.print("❌ Échec de la configuration")
        else:
            Terminal.print("❌ Configuration annulée")
        
        Terminal.input("\nAppuyez sur Entrée pour continuer...")
    
    def users_menu(self):
        while True:
            self.show_header()
            Terminal.print("👥 GESTION DES UTILISATEURS")
            Terminal.print("")
            
            users = self.user_manager.list_users()
            if users:
                Terminal.print("Utilisateurs existants:")
                for i, user in enumerate(users, 1):
                    numero, context, created_at = user
                    Terminal.print(f"  {i}. {numero} (Contexte: {context}) - Créé le: {created_at}")
            else:
                Terminal.print("Aucun utilisateur configuré")
            
            Terminal.print(f"\n1. ➕ Ajouter un utilisateur")
            Terminal.print("2. 🗑️  Supprimer un utilisateur")
            Terminal.print("3. 🔄 Reconfigurer Asterisk")
            Terminal.print("0. ↩️  Retour")
            
            choice = Terminal.input("\nVotre choix: ")
            
            if choice == "1":
                self.add_user_menu()
            elif choice == "2":
                self.delete_user_menu(users)
            elif choice == "3":
                self.configurator.configure_asterisk()
                Terminal.print("✅ Asterisk reconfiguré avec les utilisateurs actuels")
                Terminal.input("Appuyez sur Entrée pour continuer...")
            elif choice == "0":
                return
            else:
                Terminal.print("❌ Choix invalide")
                Terminal.input("Appuyez sur Entrée pour continuer...")
    
    def add_user_menu(self):
        self.show_header()
        Terminal.print("➕ AJOUT D'UTILISATEUR")
        Terminal.print("")
        
        password = Terminal.input("Mot de passe pour l'utilisateur: ")
        context = Terminal.input("Contexte [from-internal]: ") or "from-internal"
        
        if password:
            phone_number = self.user_manager.add_user(password, context)
            if phone_number:
                Terminal.print(f"✅ Utilisateur créé: {phone_number}")
                Terminal.print("🔄 Mise à jour de la configuration Asterisk...")
                self.configurator.configure_asterisk()
            else:
                Terminal.print("❌ Erreur lors de la création de l'utilisateur")
        else:
            Terminal.print("❌ Le mot de passe est obligatoire")
        
        Terminal.input("\nAppuyez sur Entrée pour continuer...")
    
    def delete_user_menu(self, users):
        if not users:
            Terminal.print("❌ Aucun utilisateur à supprimer")
            Terminal.input("Appuyez sur Entrée pour continuer...")
            return
        
        self.show_header()
        Terminal.print("🗑️  SUPPRESSION D'UTILISATEUR")
        Terminal.print("")
        
        Terminal.print("Utilisateurs existants:")
        for i, user in enumerate(users, 1):
            numero, context, _ = user
            Terminal.print(f"  {i}. {numero}")
        
        try:
            choice = int(Terminal.input("\nNuméro de l'utilisateur à supprimer (0 pour annuler): "))
            if choice == 0:
                return
            
            if 1 <= choice <= len(users):
                phone_number = users[choice-1][0]
                confirm = Terminal.input(f"Confirmer la suppression de {phone_number}? (o/N): ").strip().lower()
                
                if confirm == 'o' or confirm == 'oui':
                    if self.user_manager.delete_user(phone_number):
                        Terminal.print("🔄 Mise à jour de la configuration Asterisk...")
                        self.configurator.configure_asterisk()
                else:
                    Terminal.print("❌ Suppression annulée")
            else:
                Terminal.print("❌ Choix invalide")
        except ValueError:
            Terminal.print("❌ Veuillez entrer un numéro valide")
        
        Terminal.input("\nAppuyez sur Entrée pour continuer...")
    
    def numbers_menu(self):
        self.show_header()
        Terminal.print("📞 GESTION DES NUMÉROS 601")
        Terminal.print("")
        
        users = self.user_manager.list_users()
        if users:
            Terminal.print("Numéros 601 attribués:")
            for user in users:
                numero, context, created_at = user
                Terminal.print(f"  📞 {numero} (Contexte: {context})")
        else:
            Terminal.print("Aucun numéro 601 attribué")
        
        Terminal.print(f"\nFormat: {Config.EXTENSION_PREFIX}XXXXXX (9 chiffres)")
        Terminal.print("Génération automatique à chaque nouvel utilisateur")
        
        Terminal.input("\nAppuyez sur Entrée pour continuer...")
    
    def asterisk_control_menu(self):
        while True:
            self.show_header()
            Terminal.print("🚀 CONTRÔLE ASTERISK")
            Terminal.print("")
            
            status = "✅ EN COURS" if self.asterisk_manager.is_running() else "❌ ARRÊTÉ"
            Terminal.print(f"Statut actuel: {status}")
            
            Terminal.print(f"\n1. ▶️  Démarrer Asterisk (service start)")
            Terminal.print("2. ⏹️  Arrêter Asterisk (service stop)")
            Terminal.print("3. 🔄 Redémarrer Asterisk (service restart)")
            Terminal.print("4. 🔃 Recharger configuration (service reload)")
            Terminal.print("5. 📊 Statut détaillé")
            Terminal.print("0. ↩️  Retour")
            
            choice = Terminal.input("\nVotre choix: ")
            
            if choice == "1":
                self.asterisk_manager.start()
            elif choice == "2":
                self.asterisk_manager.stop()
            elif choice == "3":
                self.asterisk_manager.restart()
            elif choice == "4":
                self.asterisk_manager.reload()
            elif choice == "5":
                self.show_asterisk_status()
            elif choice == "0":
                return
            else:
                Terminal.print("❌ Choix invalide")
            
            Terminal.input("\nAppuyez sur Entrée pour continuer...")
    
    def show_asterisk_status(self):
        self.show_header()
        Terminal.print("📊 STATUT DÉTAILLÉ ASTERISK")
        Terminal.print("")
        
        if self.asterisk_manager.is_running():
            Terminal.print("✅ Asterisk est en cours d'exécution")
            
            try:
                result = subprocess.run(['systemctl', 'status', 'asterisk'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    lines = result.stdout.split('\n')
                    for line in lines[:10]:
                        if line.strip():
                            Terminal.print(f"   {line}")
            except Exception as e:
                Terminal.print(f"❌ Erreur récupération statut: {e}")
        else:
            Terminal.print("❌ Asterisk n'est pas en cours d'exécution")
    
    def access_codes_menu(self):
        while True:
            self.show_header()
            Terminal.print("🔐 GESTION DES CODES D'ACCÈS")
            Terminal.print("")
            
            self.code_manager.display_code_status()
            
            Terminal.print(f"\n1. 🔄 Régénérer le code")
            Terminal.print("2. ✅ Valider un code")
            Terminal.print("3. 🔍 Afficher le code actuel (DEBUG)")
            Terminal.print("0. ↩️  Retour")
            
            choice = Terminal.input("\nVotre choix: ")
            
            if choice == "1":
                self.regenerate_code()
            elif choice == "2":
                self.validate_code_menu()
            elif choice == "3":
                self.show_current_code_debug()
            elif choice == "0":
                return
            else:
                Terminal.print("❌ Choix invalide")
                Terminal.input("Appuyez sur Entrée pour continuer...")
    
    def regenerate_code(self):
        current_date = datetime.now()
        month_year = self.code_manager.get_current_period()
        new_code = self.code_manager.generate_deterministic_code(month_year)
        
        if current_date.month == 12:
            next_month = datetime(current_date.year + 1, 1, 1)
        else:
            next_month = datetime(current_date.year, current_date.month + 1, 1)
        
        expires_at = next_month - timedelta(days=1)
        expires_at = expires_at.replace(hour=23, minute=59, second=59)
        
        if DatabaseManager.update_access_code(new_code, month_year, expires_at):
            month_name = self.code_manager.month_names[current_date.month]
            Terminal.print(f"✅ Code {month_name} {current_date.year} régénéré et stocké")
            Terminal.print(f"🔐 Code: *** MASQUÉ ***")
        else:
            Terminal.print("❌ Erreur lors de la régénération du code")
        
        Terminal.input("\nAppuyez sur Entrée pour continuer...")
    
    def validate_code_menu(self):
        self.show_header()
        Terminal.print("🔐 VALIDATION DE CODE")
        Terminal.print("")
        
        test_code = Terminal.getpass("Code à valider: ").strip().upper()
        
        if self.code_manager.validate_code(test_code):
            Terminal.print("✅ Code valide!")
        else:
            Terminal.print("❌ Code invalide")
        
        Terminal.input("\nAppuyez sur Entrée pour continuer...")
    
    def show_current_code_debug(self):
        """Fonction de debug pour afficher le code actuel (à usage administratif)"""
        self.show_header()
        Terminal.print("🔍 AFFICHAGE DU CODE (DEBUG)")
        Terminal.print("")
        
        code_data = DatabaseManager.get_current_access_code()
        if code_data:
            month_year = code_data['month_year']
            month_num = int(month_year.split('-')[0])
            month_name = self.code_manager.month_names.get(month_num, "Inconnu")
            year = month_year.split('-')[1]
            
            Terminal.print(f"📅 Période: {month_name} {year}")
            Terminal.print(f"🔑 Code: {code_data['code']}")
            Terminal.print(f"⏰ Expire le: {code_data['expires_at'].strftime('%d/%m/%Y à %H:%M:%S')}")
        else:
            Terminal.print("❌ Aucun code trouvé")
        
        Terminal.input("\nAppuyez sur Entrée pour continuer...")
    
    def system_check_menu(self):
        self.show_header()
        Terminal.print("🔍 VÉRIFICATION SYSTÈME")
        Terminal.print("")
        
        asterisk_ok = self.asterisk_manager.is_running()
        Terminal.print(f"Asterisk: {'✅' if asterisk_ok else '❌'} {'EN COURS' if asterisk_ok else 'ARRÊTÉ'}")
        
        code_expired = self.code_manager.is_code_expired()
        Terminal.print(f"Code d'accès: {'❌ EXPIRÉ' if code_expired else '✅ VALIDE'}")
        
        users = self.user_manager.list_users()
        Terminal.print(f"Utilisateurs: {len(users)} configuré(s)")
        
        try:
            conn = sqlite3.connect(Config.DB_PATH)
            conn.close()
            Terminal.print("Base de données: ✅ ACCESSIBLE")
        except:
            Terminal.print("Base de données: ❌ INACCESSIBLE")
        
        Terminal.print(f"\nStatut global: {'✅ OPÉRATIONNEL' if asterisk_ok and not code_expired else '❌ PROBLÈME'}")
        
        Terminal.input("\nAppuyez sur Entrée pour continuer...")
    
    def system_install_menu(self):
        self.show_header()
        Terminal.print("⚙️  INSTALLATION ET RÉPARATION SYSTÈME")
        Terminal.print("")
        
        Terminal.print("Options disponibles:")
        Terminal.print("1. 🔍 Vérifier l'état du système")
        Terminal.print("2. 📦 Installer les paquets manquants")
        Terminal.print("3. 🔥 Configurer le firewall (alternative)")
        Terminal.print("4. 📞 Configurer le service Asterisk")
        Terminal.print("5. 🚀 Installation complète automatique")
        Terminal.print("0. ↩️  Retour")
        
        choice = Terminal.input("\nVotre choix: ")
        
        if choice == "1":
            SystemChecker.check_system_requirements()
        elif choice == "2":
            SystemInstaller.check_and_install_packages()
        elif choice == "3":
            SystemInstaller.configure_firewall_alternative()
        elif choice == "4":
            SystemInstaller.setup_asterisk()
        elif choice == "5":
            SystemInstaller.full_system_install()
        elif choice == "0":
            return
        else:
            Terminal.print("❌ Choix invalide")
        
        Terminal.input("\nAppuyez sur Entrée pour continuer...")
    
    def database_management_menu(self):
        """Menu de gestion des bases de données"""
        self.show_header()
        Terminal.print("🗄️  GESTION DES BASES DE DONNÉES")
        Terminal.print("")
        
        # Vérifier le statut des bases
        databases = [
            ("Principale", Config.DB_PATH),
            ("Codes d'accès", "/home/vps/asterisk/access_codes.db"),
            ("Logs système", "/home/vps/asterisk/system_logs.db"),
            ("CDR", "/home/vps/asterisk/cdr.db"),
            ("Configuration", "/home/vps/asterisk/config.db")
        ]
        
        Terminal.print("📊 STATUT DES BASES:")
        for name, path in databases:
            if os.path.exists(path):
                size = os.path.getsize(path)
                size_kb = size / 1024
                Terminal.print(f"  ✅ {name}: {size_kb:.1f} KB")
            else:
                Terminal.print(f"  ❌ {name}: NON CRÉÉE")
        
        Terminal.print(f"\n🔧 OPTIONS:")
        Terminal.print("1. 🔄 Recréer toutes les bases")
        Terminal.print("2. 🗑️  Supprimer une base")
        Terminal.print("0. ↩️  Retour")
        
        choice = Terminal.input("\nVotre choix: ")
        
        if choice == "1":
            self.recreate_all_databases()
        elif choice == "2":
            self.delete_database_menu()
        elif choice == "0":
            return
        else:
            Terminal.print("❌ Choix invalide")
        
        Terminal.input("\nAppuyez sur Entrée pour continuer...")
    
    def recreate_all_databases(self):
        """Recréer toutes les bases de données"""
        self.show_header()
        Terminal.print("🔄 RECRÉATION DE TOUTES LES BASES")
        Terminal.print("")
        
        Terminal.print("Cette action va:")
        Terminal.print("✅ Recréer toutes les bases de données")
        Terminal.print("✅ Conserver la structure et les données")
        Terminal.print("✅ Régénérer les codes d'accès")
        Terminal.print("")
        
        confirm = Terminal.input("Confirmer la recréation? (o/N): ").strip().lower()
        
        if confirm in ['o', 'oui', 'y', 'yes']:
            if DatabaseManager.ensure_all_databases():
                Terminal.print("✅ Toutes les bases de données recréées avec succès")
            else:
                Terminal.print("❌ Erreur lors de la recréation")
        else:
            Terminal.print("❌ Recréation annulée")
    
    def delete_database_menu(self):
        """Menu de suppression d'une base de données"""
        self.show_header()
        Terminal.print("🗑️  SUPPRESSION D'UNE BASE DE DONNÉES")
        Terminal.print("")
        
        Terminal.print("⚠️  ATTENTION: Cette action est irréversible!")
        Terminal.print("")
        
        databases = [
            ("1", "Principale", Config.DB_PATH),
            ("2", "Codes d'accès", "/home/vps/asterisk/access_codes.db"),
            ("3", "Logs système", "/home/vps/asterisk/system_logs.db"),
            ("4", "CDR", "/home/vps/asterisk/cdr.db"),
            ("5", "Configuration", "/home/vps/asterisk/config.db")
        ]
        
        Terminal.print("📋 BASES DISPONIBLES:")
        for key, name, path in databases:
            exists = "✅" if os.path.exists(path) else "❌"
            Terminal.print(f"  {key}. {name} {exists}")
        
        choice = Terminal.input("\n🎯 Choisir la base à supprimer (0 pour annuler): ")
        
        if choice == "0":
            return
        
        for key, name, path in databases:
            if choice == key:
                if os.path.exists(path):
                    confirm = Terminal.input(f"❓ CONFIRMER la suppression de {name}? (écrire 'SUPPRIMER'): ")
                    if confirm == "SUPPRIMER":
                        try:
                            os.remove(path)
                            Terminal.print(f"✅ Base {name} supprimée")
                        except Exception as e:
                            Terminal.print(f"❌ Erreur suppression: {e}")
                    else:
                        Terminal.print("❌ Suppression annulée")
                else:
                    Terminal.print(f"❌ La base {name} n'existe pas")
                break
        else:
            Terminal.print("❌ Choix invalide")

# =============================================================================
# POINT D'ENTRÉE PRINCIPAL
# =============================================================================

def main():
    try:
        # Forcer le mode unbuffered
        sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None
        
        Terminal.print("🚀 ASTERISK MANAGER - SERVICE SYSTEMD")
        Terminal.print("   Système de validation par code d'accès mensuel")
        Terminal.print("   Code masqué - Stocké en base - Validation répétitive")
        Terminal.print("=" * 60)
        Terminal.print("")
        
        # Vérifier les privilèges root
        if os.geteuid() != 0:
            Terminal.print("❌ Ce script doit être exécuté en tant que root")
            Terminal.print("💡 Utilisez: sudo python3 asterisk_manager.py")
            sys.exit(1)
        
        # CRÉATION AUTOMATIQUE DES BASES DE DONNÉES
        Logger.info("Création automatique des bases de données...")
        DatabaseManager.ensure_all_databases()
        
        Terminal.print("")
        Logger.success("Système initialisé!")
        Logger.info("Démarrage du système de validation...")
        Terminal.print("")
        
        # Démarrer le gestionnaire de menu avec validation
        menu = CompleteMenuManager()
        menu.main_menu()
        
    except KeyboardInterrupt:
        Terminal.print(f"\n⏹️  Arrêt demandé par l'utilisateur")
    except Exception as e:
        Terminal.print(f"❌ Erreur critique: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
