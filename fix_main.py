"""
Fix escaped quotes in main.py
"""

import re

# Ler ficheiro
with open('src/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Substituir escape incorreto
content = content.replace(r'\"\"\"', '"""')
content = content.replace(r'\"', '"')

# Guardar
with open('src/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ main.py corrigido!")
