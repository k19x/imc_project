import os
import time
import sqlite3
import hashlib
import signal
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Literal

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException, TimeoutException, WebDriverException, NoSuchElementException
)

# =========================
# Configurações
# =========================

BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(BASE_DIR / ".env")

CONTACT_NAME = os.getenv("CONTACT_NAME", "OPERACIONAL REGIONAL SP7")
CACHE_DIR = os.getenv("CACHE_DIR", str(BASE_DIR / "chrome_profile"))
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "mensagens.db"))
WHATSAPP_URL = os.getenv("WHATSAPP_URL", "https://web.whatsapp.com")
POLL_INTERVAL_SEC = float(os.getenv("POLL_INTERVAL_SEC", "2.0"))

# =========================
# Utilidades de data
# =========================

def normalize_input_date(s: str) -> Optional[str]:
    """
    Aceita 'YYYY-MM-DD', 'DD/MM/YYYY', 'hoje', 'ontem' -> retorna 'YYYY-MM-DD'.
    """
    if not s:
        return None
    s = s.strip().lower()
    if s == "hoje":
        return datetime.now().date().isoformat()
    if s == "ontem":
        return (datetime.now().date() - timedelta(days=1)).isoformat()
    # YYYY-MM-DD
    try:
        return datetime.strptime(s, "%Y-%m-%d").date().isoformat()
    except ValueError:
        pass
    # DD/MM/YYYY
    try:
        return datetime.strptime(s, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None

def parse_date_from_timestamp(ts_str: str) -> Optional[str]:
    """
    Converte "HH:MM, dd/mm/YYYY" -> "YYYY-MM-DD".
    """
    import re
    m = re.search(r"\b(\d{1,2}:\d{2}),\s*(\d{1,2}/\d{1,2}/\d{4})\b", ts_str or "")
    if not m:
        return None
    data_br = m.group(2)
    try:
        return datetime.strptime(data_br, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None

# =========================
# Banco de Dados (SQLite)
# =========================

class MessageStore:
    """
    Tabela 'mensagens':
      id TEXT PK (hash de texto+meta)
      sender TEXT
      timestamp TEXT  -> "HH:MM, dd/mm/YYYY"
      text TEXT
      date_ymd TEXT   -> "YYYY-MM-DD"
      direction TEXT  -> "in" | "out"
    """
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mensagens (
                id TEXT PRIMARY KEY,
                sender TEXT,
                timestamp TEXT,
                text TEXT,
                date_ymd TEXT,
                direction TEXT
            )
        """)
        # Migrações defensivas (se vier de versões antigas)
        try:
            cur.execute("ALTER TABLE mensagens ADD COLUMN date_ymd TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            cur.execute("ALTER TABLE mensagens ADD COLUMN direction TEXT")
        except sqlite3.OperationalError:
            pass
        self.conn.commit()

    @staticmethod
    def make_id(text: str, meta: str) -> str:
        return hashlib.sha256((text + "|" + (meta or "")).encode("utf-8")).hexdigest()

    def exists(self, text: str, meta: str) -> bool:
        mid = self.make_id(text, meta)
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM mensagens WHERE id = ?", (mid,))
        return cur.fetchone() is not None

    def add(self, sender: str, timestamp: str, text: str, meta: str, direction: Literal["in","out"]):
        mid = self.make_id(text, meta)
        date_ymd = parse_date_from_timestamp(timestamp) or ""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO mensagens (id, sender, timestamp, text, date_ymd, direction) VALUES (?, ?, ?, ?, ?, ?)",
            (mid, sender, timestamp, text, date_ymd, direction)
        )
        self.conn.commit()

    def count_today_incoming(self) -> int:
        hoje = datetime.now().date().isoformat()
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM mensagens WHERE date_ymd = ? AND direction = 'in'", (hoje,))
        return cur.fetchone()[0]

    def fetch_by_date(self, date_ymd: str, direction: Optional[Literal["in","out"]] = None):
        cur = self.conn.cursor()
        if direction in ("in", "out"):
            cur.execute("""
                SELECT sender, timestamp, text, direction
                FROM mensagens
                WHERE date_ymd = ? AND direction = ?
                ORDER BY timestamp
            """, (date_ymd, direction))
        else:
            cur.execute("""
                SELECT sender, timestamp, text, direction
                FROM mensagens
                WHERE date_ymd = ?
                ORDER BY timestamp
            """, (date_ymd,))
        return cur.fetchall()

# =========================
# Selenium helpers
# =========================

def iniciar_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument(f"--user-data-dir={CACHE_DIR}")  # mantém sessão/QR
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")
    # Mitiga ruído de GPU no Windows (opcional)
    options.add_argument("--disable-gpu")
    options.add_argument("--use-angle=d3d11")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(120)
    return driver

def esperar_login(driver: webdriver.Chrome, timeout: int = 120):
    driver.get(WHATSAPP_URL)
    WebDriverWait(driver, timeout).until(
        EC.any_of(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='grid']")),
            EC.presence_of_element_located((By.CSS_SELECTOR, "canvas[aria-label*='Scan me']")),
        )
    )
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='grid']"))
    )

def abrir_conversa(driver: webdriver.Chrome, nome_contato: str):
    # Busca caixa (o data-tab muda; tentamos alguns)
    search_box = None
    for css in [
        "div[contenteditable='true'][data-tab='3']",
        "div[contenteditable='true'][data-tab='6']",
        "div[contenteditable='true'][role='textbox']",
        "header div[contenteditable='true']",
        "div[contenteditable='true']",
    ]:
        try:
            search_box = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, css))
            )
            if search_box:
                break
        except TimeoutException:
            continue
    if not search_box:
        raise TimeoutException("Campo de busca não encontrado.")

    search_box.click()
    search_box.send_keys(Keys.CONTROL, "a")
    search_box.send_keys(Keys.BACK_SPACE)
    search_box.send_keys(nome_contato)
    time.sleep(0.6)
    # Estratégia simples: ENTER abre o primeiro resultado
    search_box.send_keys(Keys.ENTER)

    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='application']"))
    )
    print(f"✅ Conversa aberta: {nome_contato}")

def iterar_mensagens_recebidas(driver: webdriver.Chrome):
    return driver.find_elements(By.CSS_SELECTOR, "div.message-in")

def iterar_mensagens_enviadas(driver: webdriver.Chrome):
    return driver.find_elements(By.CSS_SELECTOR, "div.message-out")

def extrair_mensagem(elem):
    """
    Retorna (sender, timestamp_str, text, meta) ou None.
    timestamp_str: "HH:MM, dd/mm/YYYY"
    """
    try:
        text_elem = elem.find_element(By.CSS_SELECTOR, "div.copyable-text span.selectable-text")
        text = text_elem.text.strip()
        if not text:
            return None

        container = elem.find_element(By.CSS_SELECTOR, "div.copyable-text")
        meta = container.get_attribute("data-pre-plain-text") or ""  # "[08:56, 08/08/2025] Fulano: "
        sender = "Desconhecido"
        timestamp_str = "Desconhecido"

        if meta:
            try:
                timestamp_str = meta.split("]")[0].strip("[").strip()     # "08:56, 08/08/2025"
                sender = meta.split("] ")[1].split(":")[0].strip()        # "Fulano" ou "Você"
            except Exception:
                pass

        return sender, timestamp_str, text, meta
    except NoSuchElementException:
        return None
    except Exception:
        return None

# =========================
# Consulta por data (on-demand)
# =========================

def mostrar_mensagens_por_data(store: MessageStore, data_input: str, direction: Optional[Literal["in","out"]] = None):
    """
    Imprime mensagens (recebidas/enviadas) de uma data específica.
    - data_input: 'YYYY-MM-DD', 'DD/MM/YYYY', 'hoje', 'ontem'
    - direction: None (todas), 'in' (recebidas), 'out' (enviadas)
    """
    date_ymd = normalize_input_date(data_input)
    if not date_ymd:
        print(f"❌ Data inválida: {data_input}. Use 'YYYY-MM-DD', 'DD/MM/YYYY', 'hoje' ou 'ontem'.")
        return

    rows = store.fetch_by_date(date_ymd, direction=direction)
    if not rows:
        print(f"📭 Nenhuma mensagem encontrada para {date_ymd}.")
        return

    legend = "todas" if direction is None else ("recebidas" if direction == "in" else "enviadas")
    print(f"📅 Mensagens de {date_ymd} ({legend}):")
    for sender, ts, text, dirc in rows:
        prefix = "📩" if dirc == "in" else "📤"
        print(f"{prefix} {sender} às {ts}: {text}")

# =========================
# Monitoramento (apenas hoje ao vivo)
# =========================

class GracefulExit:
    stop = False

def _handle_sig(sig, frame):
    GracefulExit.stop = True
    print("\n🛑 Encerrando com segurança…")

signal.signal(signal.SIGINT, _handle_sig)
signal.signal(signal.SIGTERM, _handle_sig)

def monitorar_conversa(driver: webdriver.Chrome, store: MessageStore):
    hoje_iso = datetime.now().date().isoformat()
    print("📡 Monitorando novas mensagens (APENAS hoje)…")
    print(f"📊 Total inicial hoje (recebidas): {store.count_today_incoming()}")

    seen_out = set()  # dedupe enviadas no ciclo
    seen_in = set()   # dedupe adicionais para recebidas no ciclo

    while not GracefulExit.stop:
        try:
            # === RECEBIDAS ===
            for el in iterar_mensagens_recebidas(driver):
                dados = extrair_mensagem(el)
                if not dados:
                    continue
                sender, timestamp_str, text, meta = dados
                if parse_date_from_timestamp(timestamp_str) == hoje_iso:
                    key = MessageStore.make_id(text, meta)
                    if key in seen_in:
                        continue
                    seen_in.add(key)

                    if not store.exists(text, meta):
                        store.add(sender, timestamp_str, text, meta, direction="in")
                        print(f"\n📩 {sender} às {timestamp_str}: {text}")
                        print(f"📊 Total hoje (recebidas): {store.count_today_incoming()}")

            # === ENVIADAS ===
            for el in iterar_mensagens_enviadas(driver):
                dados = extrair_mensagem(el)
                if not dados:
                    continue
                sender, timestamp_str, text, meta = dados
                if parse_date_from_timestamp(timestamp_str) != hoje_iso:
                    continue
                key = MessageStore.make_id(text, meta)
                if key in seen_out:
                    continue
                seen_out.add(key)

                if not store.exists(text, meta):
                    store.add(sender, timestamp_str, text, meta, direction="out")
                print(f"\n📤 {sender} às {timestamp_str}: {text}")

            time.sleep(POLL_INTERVAL_SEC)

        except (StaleElementReferenceException, TimeoutException, WebDriverException):
            time.sleep(1.5)
            continue
        except Exception as e:
            print(f"[ERRO] {e}")
            time.sleep(2)

# =========================
# Main
# =========================

def main():
    store = MessageStore(DB_PATH)
    driver = iniciar_driver()
    try:
        esperar_login(driver)
        abrir_conversa(driver, CONTACT_NAME)

        # Exemplo: consultar antes de iniciar o monitoramento
        # mostrar_mensagens_por_data(store, "hoje")            # todas
        # mostrar_mensagens_por_data(store, "ontem", "in")     # só recebidas de ontem
        # mostrar_mensagens_por_data(store, "2025-08-08", "out")

        monitorar_conversa(driver, store)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
