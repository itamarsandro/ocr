from celery import Celery
import os
import pytesseract
from PIL import Image
from pdf2image import convert_from_path

# Configura a conexão apontando para o serviço redis-ocr na sala 2
REDIS_URL = os.getenv("REDIS_URL", "redis://redis-ocr:6379/2")

# Nome da fila isolado
app_celery = Celery("tasks_ocr", broker=REDIS_URL, backend=REDIS_URL)

# Forçamos a 1 tarefa por vez, pois OCR é um processo que exige muito processamento de CPU
app_celery.conf.worker_concurrency = 1

@app_celery.task
def processar_ocr(caminho_original):
    try:
        if not os.path.exists(caminho_original):
            return {"erro": "Arquivo original não localizado pelo worker.", "sucesso": False}

        caminho_saida = caminho_original.rsplit(".", 1)[0] + "_extraido.txt"
        extensao = caminho_original.split(".")[-1].lower()
        
        texto_final = ""

        # Lógica para PDFs: Converter páginas em imagens antes da extração
        if extensao == "pdf":
            paginas = convert_from_path(caminho_original)
            for i, pagina in enumerate(paginas):
                texto_final += f"--- PÁGINA {i+1} ---\n\n"
                # O parâmetro lang='por' assegura reconhecimento de acentuações como ã, á, ç
                texto_extraido = pytesseract.image_to_string(pagina, lang='por')
                texto_final += texto_extraido + "\n\n"
        
        # Lógica para Imagens comuns
        else:
            imagem = Image.open(caminho_original)
            texto_final = pytesseract.image_to_string(imagem, lang='por')

        # Se a extração falhar por documento muito ruim, adicionamos uma mensagem padrão
        if not texto_final.strip():
            texto_final = "[Aviso: Nenhum texto reconhecível foi encontrado no documento.]"

        # Escreve todo o conteúdo em um arquivo de texto limpo (.txt)
        with open(caminho_saida, "w", encoding="utf-8") as f:
            f.write(texto_final)

        # Remove o PDF ou Imagem original enviado para poupar o armazenamento do servidor
        if os.path.exists(caminho_original):
            os.remove(caminho_original)

        return {"url_download": f"/uploads/{os.path.basename(caminho_saida)}", "sucesso": True}
    except Exception as e:
        return {"erro": str(e), "sucesso": False}
