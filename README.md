# Monitor de Mensagens do WhatsApp Web com Selenium + SQLite

Este script monitora mensagens **recebidas** e **enviadas** em um chat específico do **WhatsApp Web**, armazenando-as em um banco SQLite e exibindo apenas as mensagens do dia atual em tempo real.  
Também é possível consultar mensagens de qualquer data usando a função de busca.

## 📌 Funcionalidades
- Armazena mensagens recebidas (`📩`) e enviadas (`📤`) com data, hora e remetente.
- Filtro para mostrar **somente mensagens de hoje** durante o monitoramento.
- Consulta por **qualquer data** (`hoje`, `ontem`, `YYYY-MM-DD` ou `DD/MM/YYYY`).
- Banco de dados **SQLite** persistente (`mensagens.db`).
- Reaproveitamento de sessão do navegador para evitar login por QR Code a cada execução.
- Suporte a busca de mensagens filtradas por **direção** (`in` para recebidas, `out` para enviadas).

---

## 📦 Dependências

Antes de rodar o script, instale os seguintes pacotes Python:

```bash

pip install selenium python-dotenv
===============================================================================================================================================================================================================================
⚙️ Configuração
Crie um arquivo .env na raiz do projeto com:

CONTACT_NAME=OPERACIONAL REGIONAL SP7
CACHE_DIR=./chrome_profile
DB_PATH=./mensagens.db
WHATSAPP_URL=https://web.whatsapp.com
POLL_INTERVAL_SEC=2.0
Parâmetros:

CONTACT_NAME → Nome do contato ou grupo que será monitorado exatamente como aparece no WhatsApp.
CACHE_DIR → Pasta para armazenar o perfil do Chrome (mantém login).
DB_PATH → Caminho para o banco SQLite.
WHATSAPP_URL → URL do WhatsApp Web.
POLL_INTERVAL_SEC → Intervalo (em segundos) para verificar novas mensagens.
===============================================================================================================================================================================================================================
Execute o script:
python imc_beta.py
===============================================================================================================================================================================================================================
⚠️ Observações
Este script é para uso pessoal e não é oficial do WhatsApp.
Mudanças no layout do WhatsApp Web podem exigir ajustes no seletor CSS.
Apenas funciona enquanto o WhatsApp Web estiver aberto e conectado.

