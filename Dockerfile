FROM python:3.11-slim

WORKDIR /app

# Instala ferramentas essenciais do sistema, o motor Tesseract (com idioma PT-BR) e o Poppler (manipulação de PDF)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    tesseract-ocr \
    tesseract-ocr-por \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Garante a pasta interna para o armazenamento temporário
RUN mkdir -p uploads

# Comunica a porta 82 interna para o roteador Easypanel
EXPOSE 82

# Inicia o servidor HTTP nativo na porta 82
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "82"]
