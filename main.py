"""
main.py
Ponto de entrada do sistema Condução Segura.

Modos de uso:
  python main.py extrair   → roda extração completa (sem API)
  python main.py api       → sobe a API FastAPI
"""
import sys

def rodar_extracao():
    """Modo extração direta — sem API, igual ao script original."""
    from robo.scraper import (criar_navegador, fazer_login, obter_veiculos,
                               extrair_todas_infracoes)
    nav = criar_navegador()
    fazer_login(nav)
    total_vei, veiculos = obter_veiculos(nav)
    print(f"\n=== Veículos: {len(veiculos)}/{total_vei} ===")
    todas_infracoes = extrair_todas_infracoes(nav, veiculos)
    print(f"\n=== Total de infrações: {len(todas_infracoes)} ===")
    nav.quit()
    print("Concluído.")

def rodar_api():
    """Modo API — sobe FastAPI com uvicorn."""
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from api.routes import router

    app = FastAPI(
        title="Condução Segura — API de Multas",
        description="API para extração e download de infrações do portal SENATRAN.",
        version="1.0.0",
    )

    # Permite requisições do painel HTML (qualquer origem em dev)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="")

    print("API disponível em http://localhost:8000")
    print("Documentação em  http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "api"
    if modo == "extrair":
        rodar_extracao()
    elif modo == "api":
        rodar_api()
    else:
        print(f"Modo inválido: '{modo}'. Use 'extrair' ou 'api'.")
        sys.exit(1)
