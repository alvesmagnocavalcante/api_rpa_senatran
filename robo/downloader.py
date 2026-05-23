"""
robo/downloader.py
Executa cliques de ação no portal e captura o PDF gerado.
"""
import os
import time
import glob
from DrissionPage import ChromiumPage
from robo.scraper import (
    URL_INFRACOES, _ir_para_lista_infracoes, fechar_modais,
    XPATH_INF_ITEM, _GRUPOS_ACOES
)

# XPath base do container de ações no detalhe da infração
_BASE_ACOES = ("xpath:/html/body/app-root/form/br-main-layout/div/div/main"
               "/app-infracao/app-infracoes-list/app-infracoes-veiculo-list"
               "/app-infrator-list/app-infracoes-detail/div/div/div[4]/div/div")

# Mapeia nome do grupo → índice do div
_GRUPO_IDX = {v: k for k, v in _GRUPOS_ACOES.items()}


def _navegar_para_infracao(page: ChromiumPage, placa: str, renavam: str,
                            numero_auto: str) -> bool:
    """
    Navega até o detalhe da infração específica pelo número do auto de infração.
    Retorna True se encontrou e abriu o detalhe.
    """
    if not _ir_para_lista_infracoes(page, placa, renavam):
        return False

    # Procura o item pelo número do auto de infração no texto
    idx = 1
    while True:
        item = page.ele(XPATH_INF_ITEM.format(i=idx), timeout=2)
        if not item:
            break
        if numero_auto.upper() in item.text.upper():
            item.click(by_js=True)
            time.sleep(2.0)
            page.wait.doc_loaded(timeout=15)
            return True
        idx += 1

    # Fallback: abre pelo índice se não encontrar pelo texto
    print(f"  [AVISO] Auto {numero_auto} não encontrado pelo texto. Tentando idx=1.")
    item = page.ele(XPATH_INF_ITEM.format(i=1), timeout=3)
    if item:
        item.click(by_js=True)
        time.sleep(2.0)
        page.wait.doc_loaded(timeout=15)
        return True
    return False


def _aguardar_download(download_dir: str, timeout: int = 30) -> str | None:
    """
    Aguarda um arquivo PDF aparecer na pasta de download.
    Retorna o caminho do arquivo ou None se timeout.
    """
    antes = set(glob.glob(os.path.join(download_dir, "*.pdf")))
    for _ in range(timeout * 2):
        time.sleep(0.5)
        agora = set(glob.glob(os.path.join(download_dir, "*.pdf")))
        # Arquivo novo e não está sendo escrito (sem .crdownload)
        novos = agora - antes
        em_andamento = glob.glob(os.path.join(download_dir, "*.crdownload"))
        if novos and not em_andamento:
            return list(novos)[0]
    return None


def _clicar_acao_no_portal(page: ChromiumPage, grupo: str, acao: str) -> bool:
    """
    Abre o dropdown do grupo (Pagamento/Real Infrator/Notificações)
    e clica na ação específica.
    """
    idx_grupo = _GRUPO_IDX.get(grupo)
    if idx_grupo is None:
        print(f"  [ERRO] Grupo '{grupo}' não reconhecido.")
        return False

    # Clica no botão principal do grupo (abre o dropdown)
    container = page.ele(f"{_BASE_ACOES}/div[{idx_grupo}]", timeout=5)
    if not container:
        print(f"  [ERRO] Container do grupo '{grupo}' não encontrado.")
        return False

    btn_grupo = container.ele("xpath:.//button[1]", timeout=3)
    if not btn_grupo:
        print(f"  [ERRO] Botão do grupo '{grupo}' não encontrado.")
        return False

    btn_grupo.click(by_js=True)
    time.sleep(0.5)

    # Clica no sub-botão da ação específica
    botoes = container.eles("xpath:.//div//button")
    for btn in botoes:
        if btn.text.strip() == acao:
            btn.click(by_js=True)
            print(f"  Clicou: {grupo} → {acao}")
            return True

    print(f"  [ERRO] Ação '{acao}' não encontrada no grupo '{grupo}'.")
    return False


def baixar_documento(
    page: ChromiumPage,
    placa: str,
    renavam: str,
    numero_auto: str,
    grupo: str,
    acao: str,
    download_dir: str,
) -> str | None:
    """
    Navega até a infração, executa o clique da ação e aguarda o PDF ser gerado.

    Parâmetros:
        page        : instância do navegador já logado
        placa       : placa do veículo
        renavam     : RENAVAM do veículo
        numero_auto : número do auto de infração (para localizar a infração correta)
        grupo       : "Pagamento", "Real Infrator" ou "Notificações"
        acao        : nome exato do botão (ex: "Notificação de Autuação")
        download_dir: pasta onde o Chrome salvará o PDF

    Retorna o caminho local do PDF ou None em caso de falha.
    """
    print(f"\nBaixando: [{grupo}] {acao} — Auto {numero_auto} | Placa {placa}")

    # 1) Navega até o detalhe da infração
    if not _navegar_para_infracao(page, placa, renavam, numero_auto):
        print(f"  [ERRO] Não conseguiu abrir a infração {numero_auto}.")
        return None

    # 2) Clica na ação
    if not _clicar_acao_no_portal(page, grupo, acao):
        return None

    # 3) Aguarda o PDF ser baixado (o Chrome abre em nova aba ou faz download)
    time.sleep(1.0)

    # Se abriu nova aba com o PDF, captura via tab
    if len(page.get_tabs()) > 1:
        tab_pdf = page.get_tabs()[-1]
        page.to_tab(tab_pdf)
        time.sleep(2.0)
        # Tenta obter a URL do PDF
        pdf_url = page.url
        print(f"  PDF aberto na aba: {pdf_url}")
        page.close()  # fecha a aba do PDF
        page.to_tab(page.get_tabs()[0])  # volta para a aba principal
        # Aguarda download se iniciado
        caminho = _aguardar_download(download_dir, timeout=30)
        if caminho:
            print(f"  PDF salvo: {caminho}")
            return caminho
        # Se não baixou, retorna a URL para o cliente abrir direto
        return pdf_url

    # Se não abriu nova aba, aguarda download direto
    caminho = _aguardar_download(download_dir, timeout=30)
    if caminho:
        print(f"  PDF salvo: {caminho}")
        return caminho

    print(f"  [AVISO] PDF não encontrado na pasta de download.")
    return None
