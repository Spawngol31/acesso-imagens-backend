#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

# --- NOVO COMANDO ADICIONADO ---
# Tenta criar o super-utilizador de forma não-interativa.
# Ele irá ler as 3 variáveis de ambiente que vamos configurar no Render.
echo "A tentar criar o super-utilizador..."
python manage.py create_prod_superuser
echo "Criação de super-utilizador concluída (pode ter falhado se já existir, o que é normal)."