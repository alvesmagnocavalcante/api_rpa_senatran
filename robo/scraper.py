import os
import csv
import json
import time
import random
import shutil
import tempfile
import atexit
from datetime import datetime
from dotenv import load_dotenv
from DrissionPage import ChromiumPage, ChromiumOptions
if os.name == "nt":
    from pywinauto.keyboard import send_keys as _send_keys
else:
    _send_keys = None

load_dotenv()

URL_PORTAL    = "https://portalservicos.senatran.serpro.gov.br/"
URL_HOME      = "https://portalservicos.senatran.serpro.gov.br/#/home"
URL_INFRACOES = "https://portalservicos.senatran.serpro.gov.br/#/infracoes/consultar/veiculo"
MAX_PAGINAS   = 200
CACHE_VEICULOS = "veiculos_cache.json"

# ── XPaths — Veículos ─────────────────────────────────────────────────────────

_BASE_VEI = ("xpath:/html/body/app-root/form/br-main-layout/div/div/main"
             "/app-veiculo/app-veiculos-list/div/div/div[2]/form"
             "/br-tab-set/div/nav/br-tab/div/div[3]/div")

XPATH_VEI_TOTAL   = _BASE_VEI + "/table/tfoot/tr/td[2]"
XPATH_VEI_PROXIMO = _BASE_VEI + "/table/tfoot/tr/td[1]/pagination/ul/li[8]/a"
XPATH_VEI_MODELO  = _BASE_VEI + "/div[{i}]/div[1]/div/div/span"
XPATH_VEI_PLACA   = _BASE_VEI + "/div[{i}]/div[2]/div/div[1]/span"
XPATH_VEI_RENAVAM = _BASE_VEI + "/div[{i}]/div[2]/div/div[2]/span"

# ── XPaths — Infrações ────────────────────────────────────────────────────────

_BASE_INF = ("xpath:/html/body/app-root/form/br-main-layout/div/div/main"
             "/app-infracao/app-infracoes-list/app-infracoes-veiculo-list")

XPATH_INF_INPUT_PLACA   = _BASE_INF + "/div/div/app-infracao-veiculo-lista/form/div[2]/div[1]/br-input/div/div/input"
XPATH_INF_INPUT_RENAVAM = _BASE_INF + "/div/div/app-infracao-veiculo-lista/form/div[2]/div[2]/input"
XPATH_INF_FILTRAR       = _BASE_INF + "/div/div/app-infracao-veiculo-lista/form/div[2]/div[3]/button[1]"
XPATH_INF_LIMPAR        = _BASE_INF + "/div/div/app-infracao-veiculo-lista/form/div[2]/div[3]/button[2]"
XPATH_INF_VEICULO       = _BASE_INF + "/div/div/app-infracao-veiculo-lista/form/div[3]/div[2]/div[{i}]/div"
XPATH_INF_ITEM          = "xpath:/html/body/app-root/form/br-main-layout/div/div/main/app-infracao/app-infracoes-list/app-infracoes-veiculo-list/app-infrator-list/div/div/app-infracao-lista/form/div[3]/div[2]/div[{i}]/div"
XPATH_INF_MOTIVO        = _BASE_INF + "/app-infrator-list/app-infracoes-detail/div/div/div[2]"
XPATH_INF_TABELA        = _BASE_INF + "/app-infrator-list/app-infracoes-detail/div/div/div[3]/div/table[1]"

# ── Navegador ─────────────────────────────────────────────────────────────────

def criar_navegador(download_dir: str = None) -> ChromiumPage:
    tmp = tempfile.mkdtemp(prefix="chrome_senatran_")
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)

    default_dir = os.path.join(tmp, "Default")
    os.makedirs(default_dir, exist_ok=True)
    origens = ["https://sso.acesso.gov.br:443,*",
               "https://certificado.acesso.gov.br:443,*",
               "https://portalservicos.senatran.serpro.gov.br:443,*"]

    prefs = {
        "credentials_enable_service": False,
        "profile": {
            "password_manager_enabled": False,
            "content_settings": {"exceptions": {
                "client_certificate": {o: {"setting": {"filters": [{}]}} for o in origens},
            }},
            "default_content_setting_values": {"geolocation": 2, "notifications": 2},
        },
    }
    if download_dir:
        prefs["download"] = {
            "default_directory": download_dir,
            "prompt_for_download": False,
        }
        prefs["plugins"] = {"always_open_pdf_externally": True}

    json.dump(prefs, open(os.path.join(default_dir, "Preferences"), "w"))

    co = ChromiumOptions()
    co.set_user_data_path(tmp)
    co.set_argument("--disable-geolocation")
    co.set_argument("--deny-permission-prompts")
    co.set_argument("--disable-notifications")
    return ChromiumPage(co)

# ── Helpers gerais ─────────────────────────────────────────────────────────────

def clicar_modal(page: ChromiumPage, xpath: str, timeout: int = 3, label: str = "") -> bool:
    btn = page.ele(xpath, timeout=timeout)
    if not btn:
        return False
    try:
        btn.click(by_js=True)
        if label:
            print(f"{label} fechado.")
        return True
    except Exception as e:
        print(f"Aviso ao fechar '{label}': {e}")
        return False

def fechar_modais(page: ChromiumPage) -> None:
    clicar_modal(page, "xpath:/html/body/modal-container/div/div/div[3]/div/button", timeout=3, label="Modal")
    for label in ("Agora não", "Aceitar"):
        btn = page.ele(f"xpath://button[normalize-space()='{label}']", timeout=2)
        if btn:
            try:
                btn.click(by_js=True)
            except Exception:
                pass
    cookie = page.ele("xpath://*[@id='cookiebar']/div[1]/div/div/div/div[2]/button[2]", timeout=2)
    if cookie:
        try:
            cookie.click(by_js=True)
        except Exception:
            pass

def preencher_input_angular(page: ChromiumPage, xpath: str, valor: str, timeout: int = 5) -> bool:
    """Preenche um input Angular via JS disparando os eventos necessários."""
    inp = page.ele(xpath, timeout=timeout)
    if not inp:
        return False
    inp.click()
    inp.run_js("this.value = ''")
    inp.run_js(f"this.value = '{valor}'")
    inp.run_js("this.dispatchEvent(new Event('input',  {bubbles:true}))")
    inp.run_js("this.dispatchEvent(new Event('change', {bubbles:true}))")
    return True

# ── Login ──────────────────────────────────────────────────────────────────────

def fazer_login(page: ChromiumPage) -> None:
    page.get(URL_PORTAL)
    page.wait.doc_loaded(timeout=20)

    page.ele("xpath://*[@id='header']/br-header/div/div/div[2]/div/button", timeout=10).click()
    time.sleep(1.5)

    _lc = "translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
    btn_cert = (
        page.ele(f"xpath://a[contains({_lc}, 'certificado digital')]", timeout=3)
        or page.ele(f"xpath://button[contains({_lc}, 'certificado')]", timeout=3)
        or page.ele("xpath://a[contains(@href, 'certificado')]", timeout=3)
    )
    if not btn_cert:
        raise RuntimeError("Botão 'Certificado Digital' não encontrado.")
    btn_cert.click()
    print("Aguardando certificado...")

    time.sleep(1.5)
    if _send_keys is not None:
        _send_keys("{ENTER}")
    time.sleep(0.5)

    clicar_modal(page, "xpath://*[@id='cookiebar']/div[1]/div/div/div/div[2]/button[2]", timeout=5)
    clicar_modal(page, "xpath:/html/body/modal-container/div/div/div[3]/div/button", timeout=15, label="Modal GOV.BR")

    page.wait.doc_loaded(timeout=30)
    time.sleep(2.0)

    if "sso.acesso.gov.br" in page.url:
        raise RuntimeError(f"Login não concluído. URL: {page.url}")
    print(f"Login OK. URL: {page.url}")

    fechar_modais(page)

    home = page.ele(
        "xpath:/html/body/app-root/form/br-main-layout/div/div/main/div/br-breadcrumbs/div/ul/li[1]/a",
        timeout=10,
    )
    if home:
        home.click()
        page.wait.doc_loaded(timeout=20)
        fechar_modais(page)

# ── Cache de Veículos ─────────────────────────────────────────────────────────

def carregar_cache_veiculos() -> dict | None:
    if not os.path.exists(CACHE_VEICULOS):
        return None
    try:
        with open(CACHE_VEICULOS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def salvar_cache_veiculos(total: int, veiculos: list[dict]) -> None:
    with open(CACHE_VEICULOS, "w", encoding="utf-8") as f:
        json.dump({"total": total, "veiculos": veiculos}, f, ensure_ascii=False, indent=2)
    print(f"Cache salvo: {CACHE_VEICULOS} ({total} veículos)")

def obter_veiculos(page: ChromiumPage) -> tuple[int, list[dict]]:
    """
    Lê o total do portal uma vez.
    - Cache válido (mesmo total) → usa cache, sem extrair nada.
    - Total diferente ou sem cache → extrai tudo e salva.
    """
    cache = carregar_cache_veiculos()

    fechar_modais(page)

    # Fecha alerta de segurança se aparecer
    alerta = page.ele(
        "xpath://div[contains(@class,'alert')]//button[@aria-label='Close' or contains(@class,'close')]",
        timeout=2,
    )
    if alerta:
        try:
            alerta.click(by_js=True)
        except Exception:
            pass

    # Clica no card "Consultar Meus Veículos"
    card = page.ele(
        "xpath://*[@id='outros-servicos']/br-fieldset[2]/fieldset/div[2]/div[2]/div/div",
        timeout=15,
    )
    if not card:
        raise RuntimeError("Card 'Consultar Meus Veículos' não encontrado.")
    card.click()
    page.wait.doc_loaded(timeout=20)
    fechar_modais(page)

    el_total = page.ele(XPATH_VEI_TOTAL, timeout=10)
    total_portal = int("".join(filter(str.isdigit, el_total.text))) if el_total else 0
    print(f"Total no portal: {total_portal} veículos")

    if cache and cache.get("total") == total_portal:
        print(f"Cache válido ({total_portal} veículos). Pulando extração.")
        return total_portal, cache["veiculos"]

    print("Extraindo veículos...")
    veiculos = _extrair_paginas_veiculos(page, total_portal)

    # Só salva cache se extraiu todos os veículos esperados
    if len(veiculos) >= total_portal:
        salvar_cache_veiculos(total_portal, veiculos)
    else:
        print(f"[AVISO] Extração incompleta: {len(veiculos)}/{total_portal}. Cache NÃO salvo.")

    return total_portal, veiculos

def _extrair_paginas_veiculos(page: ChromiumPage, total: int) -> list[dict]:
    """Percorre todas as páginas da tela de veículos já aberta."""
    veiculos: list[dict] = []
    placas_vistas: set[str] = set()
    ultima_placa_pag: str | None = None

    for pagina in range(1, MAX_PAGINAS + 1):
        print(f"\n--- Página {pagina} ---")

        pagina_atual, i = [], 1
        while True:
            el = page.ele(XPATH_VEI_MODELO.format(i=i), timeout=0.5)
            if not el:
                break
            placa = page.ele(XPATH_VEI_PLACA.format(i=i)).text.strip()
            if placa not in placas_vistas:
                v = {
                    "modelo":  el.text.strip(),
                    "placa":   placa,
                    "renavam": page.ele(XPATH_VEI_RENAVAM.format(i=i)).text.strip(),
                }
                print(f"  [{i}] {v['modelo']} | {v['placa']} | {v['renavam']}")
                pagina_atual.append(v)
                placas_vistas.add(placa)
            i += 1

        if not pagina_atual:
            print("Página vazia. Encerrando.")
            break

        primeira_placa = pagina_atual[0]["placa"]
        if primeira_placa == ultima_placa_pag:
            print("Página não avançou. Encerrando.")
            break
        ultima_placa_pag = primeira_placa
        veiculos.extend(pagina_atual)
        print(f"  +{len(pagina_atual)} | acumulado: {len(veiculos)}/{total}")

        if total > 0 and len(veiculos) >= total:
            print("Todos os veículos extraídos.")
            break

        btn = (
            page.ele(XPATH_VEI_PROXIMO, timeout=3)
            or page.ele("xpath://pagination//li[not(contains(@class,'disabled'))]/a[@aria-label='Next']", timeout=3)
            or page.ele("xpath://pagination//li[last()-1]/a", timeout=3)
        )
        if not btn:
            print("Botão próximo não encontrado. Encerrando.")
            break

        if "disabled" in (btn.attr("class") or "") or "disabled" in (btn.parent().attr("class") or ""):
            print("Última página atingida.")
            break

        placa_antes = ultima_placa_pag
        btn.click()
        page.wait.doc_loaded(timeout=15)
        time.sleep(2.0)

        # Aguarda a página recarregar com novos itens (até 15s)
        for _ in range(30):
            el = page.ele(XPATH_VEI_PLACA.format(i=1), timeout=0.5)
            if el and el.text.strip() != placa_antes:
                break
            time.sleep(0.5)

    return veiculos

# ── Extração de Infrações ──────────────────────────────────────────────────────

def _filtrar_por_placa(page: ChromiumPage, placa: str, renavam: str) -> bool:
    """Filtra pela placa, com fallback por RENAVAM. Retorna True se encontrou card."""
    btn_limpar = page.ele(XPATH_INF_LIMPAR, timeout=2)
    if btn_limpar:
        btn_limpar.click(by_js=True)

    ok = preencher_input_angular(page, XPATH_INF_INPUT_PLACA, placa)
    if not ok:
        print(f"  [AVISO] Campo Placa não encontrado.")
        return False

    btn = page.ele(XPATH_INF_FILTRAR, timeout=5)
    if not btn:
        return False
    btn.click(by_js=True)
    page.wait.doc_loaded(timeout=15)

    if page.ele(XPATH_INF_VEICULO.format(i=1), timeout=5):
        return True

    # Fallback por RENAVAM
    print(f"  Nenhum resultado por placa. Tentando RENAVAM...")
    btn_limpar2 = page.ele(XPATH_INF_LIMPAR, timeout=2)
    if btn_limpar2:
        btn_limpar2.click(by_js=True)
    preencher_input_angular(page, XPATH_INF_INPUT_RENAVAM, renavam)
    btn2 = page.ele(XPATH_INF_FILTRAR, timeout=5)
    if btn2:
        btn2.click(by_js=True)
        page.wait.doc_loaded(timeout=15)

    return page.ele(XPATH_INF_VEICULO.format(i=1), timeout=5) is not None

def _ir_para_lista_infracoes(page: ChromiumPage, placa: str, renavam: str) -> bool:
    """Navega para URL de infrações, filtra pela placa e clica no card do veículo."""
    page.get(URL_INFRACOES)
    page.wait.doc_loaded(timeout=20)
    fechar_modais(page)

    if not _filtrar_por_placa(page, placa, renavam):
        return False

    c = page.ele(XPATH_INF_VEICULO.format(i=1), timeout=8)
    if not c:
        return False
    print(f"  Card: {c.text.strip()[:80]}")
    c.click(by_js=True)
    page.wait.doc_loaded(timeout=15)
    return True

# Mapeamento fixo: índice do div → nome do grupo
_GRUPOS_ACOES = {1: "Pagamento", 2: "Real Infrator", 3: "Notificações"}

def _btn_disponivel(btn) -> bool:
    """Verifica se um botão está disponível usando opacity computada via JS."""
    classe   = btn.attr("class") or ""
    disabled = btn.attr("disabled")
    style    = btn.attr("style") or ""
    try:
        opacity = float(btn.run_js("return window.getComputedStyle(this).opacity") or "1")
    except Exception:
        opacity = 1.0
    return (
        disabled is None
        and "disabled" not in classe
        and "pointer-events: none" not in style
        and opacity >= 0.99
    )

def extrair_acoes_disponiveis(page: ChromiumPage) -> dict:
    """
    Extrai ações agrupadas por categoria (Pagamento, Real Infrator, Notificações).
    Retorna dict aninhado: { "Pagamento": { "Desconto de 40%": True, ... }, ... }
    """
    _BASE_ACOES = ("xpath:/html/body/app-root/form/br-main-layout/div/div/main"
                   "/app-infracao/app-infracoes-list/app-infracoes-veiculo-list"
                   "/app-infrator-list/app-infracoes-detail/div/div/div[4]/div/div")

    acoes = {}

    for idx, grupo in _GRUPOS_ACOES.items():
        # Pega o container do grupo (div[1], div[2], div[3])
        container = page.ele(f"{_BASE_ACOES}/div[{idx}]", timeout=3)
        if not container:
            acoes[grupo] = {}
            continue

        sub = {}
        botoes = container.eles("xpath:.//div//button")
        for btn in botoes:
            nome = btn.text.strip()
            if not nome:
                continue
            sub[nome] = _btn_disponivel(btn)

        acoes[grupo] = sub

    return acoes

def extrair_tabela_detalhes(page: ChromiumPage) -> dict:
    """Lê a tabela de detalhes: <tr><th>chave</th><td>valor</td></tr>"""
    dados = {}
    tabela = page.ele(XPATH_INF_TABELA, timeout=8)
    if not tabela:
        print("    [AVISO] Tabela de detalhes não encontrada.")
        return dados
    for linha in tabela.eles("xpath:.//tr"):
        th = linha.ele("xpath:.//th", timeout=0)
        td = linha.ele("xpath:.//td", timeout=0)
        if th and td:
            chave = th.text.strip().rstrip(":")
            valor = td.text.strip()
            if chave:
                dados[chave] = valor
    return dados

def extrair_infracoes_veiculo(page: ChromiumPage, veiculo: dict) -> list[dict]:
    """Extrai todas as infrações não pagas de um veículo."""
    placa   = veiculo["placa"]
    modelo  = veiculo["modelo"]
    renavam = veiculo["renavam"]

    print(f"\n{'='*60}")
    print(f"Consultando: {modelo} | {placa}")
    print(f"{'='*60}")

    # Entra na lista de infrações e conta os itens
    if not _ir_para_lista_infracoes(page, placa, renavam):
        print(f"  Nenhum veículo encontrado para {placa}. Pulando.")
        return []

    total_itens = 0
    while page.ele(XPATH_INF_ITEM.format(i=total_itens + 1), timeout=1):
        total_itens += 1
    print(f"  {total_itens} infração(ões) encontrada(s).")

    if total_itens == 0:
        return []

    # Para cada infração: reinicia o fluxo completo e clica pelo índice
    infracoes = []
    for idx in range(1, total_itens + 1):
        print(f"  Abrindo infração [{idx}/{total_itens}]...")

        if not _ir_para_lista_infracoes(page, placa, renavam):
            print(f"    [AVISO] Não conseguiu voltar à lista para item [{idx}].")
            continue

        item = page.ele(XPATH_INF_ITEM.format(i=idx), timeout=5)
        if not item:
            print(f"    [AVISO] Item [{idx}] não encontrado.")
            continue

        item.click(by_js=True)
        # Único sleep necessário: aguarda a tabela de detalhes carregar
        time.sleep(random.uniform(1.5, 2.5))
        page.wait.doc_loaded(timeout=15)

        el_motivo = page.ele(XPATH_INF_MOTIVO, timeout=8)
        motivo    = el_motivo.text.strip() if el_motivo else ""
        detalhes  = extrair_tabela_detalhes(page)
        acoes     = extrair_acoes_disponiveis(page)

        # Ignora itens fantasma (sem dados reais)
        if not motivo and not detalhes:
            print(f"    [AVISO] Item [{idx}] vazio, ignorando.")
            continue

        infracao = {
            "placa_veiculo":  placa,
            "modelo_veiculo": modelo,
            "renavam":        renavam,
            "motivo":         motivo,
            **detalhes,
            "acoes":          acoes,
            "extraido_em":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        print(f"    Motivo  : {motivo[:80]}")
        print(f"    Detalhes: {len(detalhes)} campos extraídos")
        infracoes.append(infracao)

    print(f"  Total infrações para {placa}: {len(infracoes)}")
    return infracoes

def extrair_todas_infracoes(page: ChromiumPage, veiculos: list[dict], arquivo: str = "infracoes.json") -> list[dict]:
    """
    Percorre todos os veículos e extrai/atualiza suas infrações.
    - Sempre re-extrai cada veículo para pegar infrações novas.
    - Substitui os dados do veículo no JSON ao invés de acumular.
    - Salva incrementalmente após cada veículo.
    """
    # Carrega dados existentes como dicionário indexado por placa
    dados_existentes: dict[str, dict] = {}
    if os.path.exists(arquivo):
        try:
            with open(arquivo, "r", encoding="utf-8") as f:
                for vei in json.load(f):
                    dados_existentes[vei["placa"]] = vei
            print(f"JSON existente: {len(dados_existentes)} veículos carregados.")
        except Exception:
            pass

    # Lista plana para compatibilidade com salvar_resultados
    todas: list[dict] = []

    for i, veiculo in enumerate(veiculos, 1):
        placa = veiculo["placa"]
        print(f"\n[{i}/{len(veiculos)}] {placa}")

        try:
            infracoes = extrair_infracoes_veiculo(page, veiculo)

            # Substitui os dados do veículo (sempre atualiza)
            dados_existentes[placa] = {
                "placa":     placa,
                "modelo":    veiculo["modelo"],
                "renavam":   veiculo["renavam"],
                "infracoes": [
                    {k: v for k, v in inf.items()
                     if k not in ("placa_veiculo", "modelo_veiculo", "renavam")}
                    for inf in infracoes
                ],
            }
            if infracoes:
                print(f"  {len(infracoes)} infração(ões) atualizada(s).")
            else:
                print(f"  Sem infrações no momento.")

        except Exception as e:
            print(f"  [ERRO] {placa}: {e}")

        # Reconstrói lista plana a partir do dict atualizado
        todas = []
        for vei in dados_existentes.values():
            for inf in vei.get("infracoes", []):
                todas.append({"placa_veiculo": vei["placa"],
                              "modelo_veiculo": vei["modelo"],
                              "renavam": vei["renavam"], **inf})

        salvar_resultados(todas, arquivo)

    return todas

# ── Salvar resultados ─────────────────────────────────────────────────────────

def salvar_resultados(infracoes: list[dict], caminho: str = "infracoes.json") -> None:
    """Salva as infrações agrupadas por veículo."""
    agrupado: dict[str, dict] = {}
    for inf in infracoes:
        placa = inf["placa_veiculo"]
        if placa not in agrupado:
            agrupado[placa] = {
                "placa":   placa,
                "modelo":  inf.get("modelo_veiculo", ""),
                "renavam": inf.get("renavam", ""),
                "infracoes": [],
            }
        # Remove campos redundantes já presentes no nível do veículo
        item = {k: v for k, v in inf.items()
                if k not in ("placa_veiculo", "modelo_veiculo", "renavam")}
        agrupado[placa]["infracoes"].append(item)

    # Só inclui veículos que tenham ao menos 1 infração
    resultado = [v for v in agrupado.values() if v["infracoes"]]
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    total_inf = sum(len(v["infracoes"]) for v in resultado)
    print(f"JSON salvo: {caminho} ({len(resultado)} veículos com infração, {total_inf} infrações)")