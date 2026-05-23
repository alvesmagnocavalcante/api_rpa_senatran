"""
api/routes.py
Endpoints FastAPI do sistema Condução Segura.
"""
import os
import json
import asyncio
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel

from robo.scraper import fazer_login, obter_veiculos, extrair_todas_infracoes, criar_navegador
from robo.downloader import baixar_documento
from storage.minio_client import upload_pdf

router = APIRouter()

INFRACOES_JSON = "infracoes.json"
DOWNLOAD_DIR   = tempfile.mkdtemp(prefix="senatran_pdfs_")

# ── Estado global do robô (singleton) ─────────────────────────────────────────
# O navegador fica aberto durante toda a vida da API
_estado = {
    "page":      None,   # instância ChromiumPage
    "logado":    False,
    "extraindo": False,
}


def get_page():
    if not _estado["page"] or not _estado["logado"]:
        raise HTTPException(status_code=503, detail="Robô não está logado. POST /login primeiro.")
    return _estado["page"]


# ── Models ─────────────────────────────────────────────────────────────────────
class BaixarRequest(BaseModel):
    placa:       str
    renavam:     str
    numero_auto: str
    grupo:       Literal["Pagamento", "Real Infrator", "Notificações"]
    acao:        str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/login", summary="Inicia o navegador e realiza login com certificado digital")
async def login():
    if _estado["logado"]:
        return {"status": "já logado"}
    try:
        nav = criar_navegador(download_dir=DOWNLOAD_DIR)
        fazer_login(nav)
        _estado["page"]   = nav
        _estado["logado"] = True
        return {"status": "login realizado com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", summary="Status do robô e do sistema")
async def status():
    return {
        "logado":    _estado["logado"],
        "extraindo": _estado["extraindo"],
        "infracoes_json_existe": os.path.exists(INFRACOES_JSON),
        "download_dir": DOWNLOAD_DIR,
    }


@router.post("/extrair", summary="Extrai todos os veículos e infrações (roda em background)")
async def extrair(background_tasks: BackgroundTasks):
    if _estado["extraindo"]:
        raise HTTPException(status_code=409, detail="Extração já em andamento.")
    page = get_page()

    def _extrair():
        _estado["extraindo"] = True
        try:
            _, veiculos = obter_veiculos(page)
            extrair_todas_infracoes(page, veiculos, INFRACOES_JSON)
        finally:
            _estado["extraindo"] = False

    background_tasks.add_task(_extrair)
    return {"status": "extração iniciada em background"}


@router.get("/infracoes", summary="Retorna o JSON de infrações para o painel")
async def get_infracoes():
    if not os.path.exists(INFRACOES_JSON):
        raise HTTPException(status_code=404, detail="infracoes.json não encontrado. Execute /extrair primeiro.")
    with open(INFRACOES_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


@router.post("/baixar", summary="Baixa o PDF de uma ação específica e envia ao MinIO")
async def baixar(req: BaixarRequest):
    page = get_page()

    # Executa o download (bloqueante — o robô é single-thread)
    caminho_pdf = baixar_documento(
        page        = page,
        placa       = req.placa,
        renavam     = req.renavam,
        numero_auto = req.numero_auto,
        grupo       = req.grupo,
        acao        = req.acao,
        download_dir= DOWNLOAD_DIR,
    )

    if not caminho_pdf:
        raise HTTPException(status_code=500, detail="Não foi possível baixar o PDF.")

    # Se for uma URL (PDF abriu em nova aba), retorna direto
    if caminho_pdf.startswith("http"):
        return {"url": caminho_pdf, "tipo": "url_direta"}

    # Faz upload para o MinIO
    nome_arquivo = f"{req.placa}/{req.numero_auto}/{req.grupo}_{req.acao}.pdf".replace(" ", "_")
    try:
        url_minio = upload_pdf(caminho_pdf, nome_arquivo)
        # Remove arquivo local após upload
        os.remove(caminho_pdf)
        return {"url": url_minio, "tipo": "minio", "objeto": nome_arquivo}
    except Exception as e:
        # Se MinIO falhar, serve o arquivo local temporariamente
        nome = Path(caminho_pdf).name
        return {
            "url": f"/pdf/{nome}",
            "tipo": "local",
            "aviso": f"MinIO indisponível: {e}"
        }


@router.get("/pdf/{nome}", summary="Serve PDF local (fallback quando MinIO indisponível)")
async def serve_pdf(nome: str):
    caminho = os.path.join(DOWNLOAD_DIR, nome)
    if not os.path.exists(caminho):
        raise HTTPException(status_code=404, detail="PDF não encontrado.")
    return FileResponse(caminho, media_type="application/pdf", filename=nome)


@router.post("/logout", summary="Fecha o navegador")
async def logout():
    if _estado["page"]:
        try:
            _estado["page"].quit()
        except: pass
    _estado["page"]   = None
    _estado["logado"] = False
    return {"status": "navegador fechado"}
