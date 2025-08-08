import os
import time
import json
import re
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException, TimeoutException, WebDriverException
)

# === Inicialização segura ===
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

CACHE_DIR = os.path.join(os.getcwd(), "chrome_profile")
MSG_REGISTRADAS = Path("mensagens_lidas.json")
AGENDADOS_ARQUIVO = "mensagens_agendadas.json"

# === Setup de logging seguro ===
logging.basicConfig(
    filename="bot.log",
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

def iniciar_driver():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument(f"--user-data-dir={CACHE_DIR}")
    return webdriver.Chrome(options=options)

def aguardar_e_abrir_conversa(driver, nome_contato):
    logging.info("Aguardando carregar contato...")
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, f'//span[@dir="auto"][@title="{nome_contato}"]'))
    ).click()
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'message-in')]"))
    )
    logging.info(f"Conversa com '{nome_contato}' aberta.")

def responder_automaticamente(driver, texto, remetente):
    try:
        campo = driver.find_element(By.XPATH, "//div[@aria-label='Digite uma mensagem'][@data-tab='10']")
        texto_limpo = texto.strip().lower()

        if re.match(r"bar[aã]o.*homem", texto_limpo, re.IGNORECASE):
            campo.send_keys("Não, Barão não é homem.\n")
        elif texto_limpo.startswith("#menu"):
            campo.send_keys("Menu:\n1. Opção 1\n2. Opção 2\n3. Opção 3\n")

    except Exception as e:
        logging.warning(f"Erro ao responder: {e}")

def carregar_mensagens_lidas():
    if MSG_REGISTRADAS.exists():
        try:
            with open(MSG_REGISTRADAS, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def salvar_mensagens_lidas(mensagens):
    try:
        with open(MSG_REGISTRADAS, "w") as f:
            json.dump(list(mensagens), f)
    except Exception as e:
        logging.error(f"Erro ao salvar mensagens lidas: {e}")

def monitorar_conversa(driver, nome_contato):
    mensagens_lidas = carregar_mensagens_lidas()

    while True:
        try: # _ao3e selectable-text copyable-text
            mensagens = driver.find_elements(By.XPATH, "//div[contains(@class, 'message-in focusable-list-item')]")
            for msg_element in mensagens:
                try:
                    conteudo = msg_element.find_element(
                        By.XPATH, ".//div[contains(@class, 'copyable-text')]//span"
                    ).text

                    if conteudo not in mensagens_lidas:
                        mensagens_lidas.add(conteudo)

                        metadata = msg_element.find_element(
                            By.XPATH, ".//div[contains(@data-pre-plain-text, '[')]"
                        ).get_attribute("data-pre-plain-text")

                        remetente = "Desconhecido"
                        try:
                            remetente = metadata.split("] ")[1].split(":")[0].strip()
                        except IndexError:
                            pass

                        hora_data = metadata.split("]")[0].strip("[")

                        print("\n📥 Nova mensagem registrada:")
                        print("👤 Remetente:", "***" + remetente[-4:] if remetente != "Desconhecido" else "Desconhecido")
                        print("💬 Conteúdo :", conteudo)
                        print("🕒 Horário  :", hora_data)
                        print("📊 Total de mensagens únicas registradas:", len(mensagens_lidas))

                        responder_automaticamente(driver, conteudo, remetente)

                except Exception as e:
                    logging.warning(f"[ERRO AO LER MENSAGEM] {e}")

            salvar_mensagens_lidas(mensagens_lidas)
            time.sleep(2)

        except (StaleElementReferenceException, TimeoutException, WebDriverException) as e:
            logging.warning(f"[WHATSAPP DRIVER WARNING] {e}")
            time.sleep(2)
            continue
        except Exception as e:
            logging.critical(f"[FATAL ERROR] {e}")
            break

def abrir_whatsapp_bot():
    nome_contato = "OPERACIONAL REGIONAL SP7"
    try:
        driver = iniciar_driver()
        driver.get("https://web.whatsapp.com")
        aguardar_e_abrir_conversa(driver, nome_contato)
        monitorar_conversa(driver, nome_contato)
    except Exception as e:
        logging.critical(f"[FALHA CRÍTICA]: {e}")
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    while True:
        abrir_whatsapp_bot()
        print("[REINÍCIO] Reiniciando o bot em 5 segundos...")
        time.sleep(5)
