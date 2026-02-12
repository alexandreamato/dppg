#!/bin/bash
# D-PPG Manager - Vasoquant 1000
# Clique duplo para iniciar o aplicativo

cd "$(dirname "$0")"

# Verificar Python 3
if ! command -v python3 &>/dev/null; then
    echo "Python 3 não encontrado. Instale em https://www.python.org"
    read -p "Pressione Enter para sair..."
    exit 1
fi

# Instalar dependências se necessário
python3 -c "import sqlalchemy, reportlab, matplotlib" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Instalando dependências..."
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "Erro ao instalar dependências."
        read -p "Pressione Enter para sair..."
        exit 1
    fi
    echo ""
fi

python3 dppg_manager.py
