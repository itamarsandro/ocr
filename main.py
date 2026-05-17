from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from worker import processar_ocr
from celery.result import AsyncResult
import uuid
import os

app = FastAPI(title="Fábrica de Textos (OCR)")

# Pasta para salvar os arquivos temporários e os textos gerados
UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# Permitir o mapeamento de arquivos estáticos da pasta uploads
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

def deletar_arquivo_servidor(caminho_arquivo: str):
    """Função executada em segundo plano para deletar o arquivo após o download."""
    try:
        if os.path.exists(caminho_arquivo):
            os.remove(caminho_arquivo)
            print(f"Arquivo {caminho_arquivo} removido com sucesso do servidor.")
    except Exception as e:
        print(f"Erro ao remover arquivo em segundo plano: {str(e)}")

@app.get("/download/{filename}")
async def forcar_download_e_limpar(filename: str, background_tasks: BackgroundTasks):
    """Endpoint que força o download do arquivo de Texto e agenda a sua destruição automática."""
    nome_seguro = os.path.basename(filename)
    caminho_completo = os.path.join(UPLOAD_DIR, nome_seguro)
    
    if not os.path.exists(caminho_completo):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado ou já deletado.")
    
    # Agenda a exclusão do arquivo para rodar IMEDIATAMENTE após a resposta ser entregue ao cliente
    background_tasks.add_task(deletar_arquivo_servidor, caminho_completo)
    
    # Retorna o arquivo forçando o download nativo do navegador
    return FileResponse(
        path=caminho_completo,
        filename=nome_seguro,
        media_type="text/plain"
    )

@app.get("/", response_class=HTMLResponse)
async def pagina_inicial():
    html_content = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Fábrica de Textos - OCR Automático</title>
        <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
    </head>
    <body class="bg-slate-900 text-slate-100 font-sans min-h-screen flex items-center justify-center p-4">
        <div class="max-w-md w-full bg-slate-800 p-8 rounded-2xl shadow-2xl border border-slate-700">
            <h1 class="text-3xl font-bold text-center mb-2 bg-gradient-to-r from-indigo-400 to-purple-500 bg-clip-text text-transparent">Fábrica de Textos</h1>
            <p class="text-slate-400 text-center text-sm mb-8">Extraia texto de documentos PDF ou Imagens automaticamente via OCR.</p>
            
            <form id="uploadForm" class="space-y-6">
                <div>
                    <label class="block text-sm font-medium mb-2">Selecione o PDF ou Imagem</label>
                    <input type="file" id="arquivo" name="arquivo" accept=".pdf,image/*" required class="w-full text-sm text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-semibold file:bg-indigo-500 file:text-slate-900 hover:file:bg-indigo-400 cursor-pointer bg-slate-900 p-3 rounded-xl border border-slate-700">
                </div>
                
                <button type="submit" class="w-full bg-gradient-to-r from-indigo-500 to-purple-600 text-slate-900 font-bold py-3 px-4 rounded-xl hover:from-indigo-400 hover:to-purple-500 transition duration-200 shadow-lg cursor-pointer">
                    Extrair Texto (OCR)
                </button>
            </form>
            
            <div id="statusContainer" class="hidden mt-8 p-4 bg-slate-900 rounded-xl border border-slate-700 text-center space-y-4">
                <div id="iconContainer" class="flex justify-center items-center">
                    <div id="spinner" class="animate-spin rounded-full h-10 w-10 border-4 border-indigo-500 border-t-transparent"></div>
                    
                    <div id="successCheck" class="hidden text-indigo-400 bg-indigo-500/10 p-2 rounded-full">
                        <svg class="h-10 w-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                    </div>
                </div>
                
                <p id="statusTexto" class="text-sm font-medium text-indigo-400">Enviando documento...</p>
                
                <div id="downloadContainer" class="hidden">
                    <a id="downloadLink" href="#" class="inline-block w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 px-4 rounded-xl transition duration-200 shadow-lg text-center">
                        Baixar Arquivo de Texto (.txt)
                    </a>
                </div>
            </div>
        </div>

        <script>
            let checagemIntervalo = null;

            document.getElementById('uploadForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                
                const form = document.getElementById('uploadForm');
                const statusContainer = document.getElementById('statusContainer');
                const statusTexto = document.getElementById('statusTexto');
                const spinner = document.getElementById('spinner');
                const successCheck = document.getElementById('successCheck');
                const downloadContainer = document.getElementById('downloadContainer');
                const downloadLink = document.getElementById('downloadLink');
                
                statusContainer.classList.remove('hidden');
                downloadContainer.classList.add('hidden');
                successCheck.classList.add('hidden');
                spinner.classList.remove('hidden');
                statusTexto.innerText = "Enviando documento para o servidor...";
                
                const formData = new FormData();
                formData.append('arquivo', document.getElementById('arquivo').files[0]);
                
                try {
                    const resposta = await fetch('/upload', { method: 'POST', body: formData });
                    const dados = await resposta.json();
                    
                    if (!dados.id_tarefa) {
                        throw new Error(dados.detail || "Falha ao injetar tarefa na fila de processamento.");
                    }
                    
                    const idTarefa = dados.id_tarefa;
                    statusTexto.innerText = "Documento na fila! Lendo e transcrevendo os caracteres...";
                    
                    if (checagemIntervalo) clearInterval(checagemIntervalo);
                    
                    checagemIntervalo = setInterval(async () => {
                        const checarStatus = await fetch(`/status/${idTarefa}`);
                        const statusDados = await checarStatus.json();
                        
                        if (statusDados.status === "Concluído") {
                            clearInterval(checagemIntervalo);
                            
                            if (statusDados.resultado.sucesso) {
                                spinner.classList.add('hidden');
                                successCheck.classList.remove('hidden');
                                statusTexto.innerText = "Sucesso! O texto foi completamente extraído.";
                                
                                const nomeArquivo = statusDados.resultado.url_download.split('/').pop();
                                downloadLink.href = `/download/${nomeArquivo}`;
                                downloadContainer.classList.remove('hidden');
                            } else {
                                spinner.classList.add('hidden');
                                statusTexto.innerText = "Erro interno no OCR: " + statusDados.resultado.erro;
                            }
                        }
                    }, 1200); 
                    
                } catch (erro) {
                    spinner.classList.add('hidden');
                    successCheck.classList.add('hidden');
                    statusTexto.innerText = "Erro operacional: " + erro.message;
                }
            });

            document.getElementById('downloadLink').addEventListener('click', () => {
                const statusTexto = document.getElementById('statusTexto');
                const downloadContainer = document.getElementById('downloadContainer');
                const successCheck = document.getElementById('successCheck');
                
                setTimeout(() => {
                    statusTexto.innerText = "Concluído! O texto foi baixado e destruído do servidor com segurança.";
                    downloadContainer.classList.add('hidden');
                    successCheck.classList.add('hidden');
                }, 800);
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)

@app.post("/upload")
async def upload_documento(arquivo: UploadFile = File(...)):
    # Permite PDFs e várias extensões de imagem
    ext = arquivo.filename.split(".")[-1].lower()
    formatos_permitidos = ["pdf", "png", "jpg", "jpeg", "webp"]
    
    if ext not in formatos_permitidos:
        raise HTTPException(status_code=400, detail=f"Formato inválido. Apenas {', '.join(formatos_permitidos)} são suportados.")
        
    id_unico = str(uuid.uuid4())
    caminho_entrada = os.path.join(UPLOAD_DIR, f"{id_unico}.{ext}")
    
    with open(caminho_entrada, "wb") as buffer:
        buffer.write(await arquivo.read())
    
    # Repassa para a fila
    tarefa = processar_ocr.delay(caminho_entrada)
    
    return {"id_tarefa": tarefa.id, "status": "Processando"}

@app.get("/status/{tarefa_id}")
async def ver_status(tarefa_id: str):
    resultado = AsyncResult(tarefa_id)
    if resultado.ready():
        return {"status": "Concluído", "resultado": resultado.result}
    return {"status": "Processando..."}
