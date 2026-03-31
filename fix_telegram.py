"""
Remove todas as referências ao Telegram do main.py
"""

import re

# Ler ficheiro
with open('src/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Padrões a remover
patterns_to_remove = [
    r'from src\.automation import.*TelegramNotifier.*\n',
    r'.*USE_TELEGRAM.*\n',
    r'.*telegram = TelegramNotifier.*\n',
    r'.*telegram =.*\n.*bot_token.*\n.*chat_id.*\n',
    r'if telegram:.*\n(?:    .*\n)*',
    r'.*telegram\..*\n',
    r'global telegram\n',
]

for pattern in patterns_to_remove:
    content = re.sub(pattern, '', content)

# Corrigir import
content = re.sub(
    r'from src\.automation import.*',
    'from src.automation import AutoRestarter, ConfigBackup',
    content
)

# Remover linhas vazias consecutivas
content = re.sub(r'\n\n\n+', '\n\n', content)

# Guardar
with open('src/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Telegram removido do main.py!")
