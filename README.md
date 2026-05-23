# API RPA SENATRAN

## Rodando em Docker com interface gráfica e navegador

Este projeto agora possui um container com:

- API FastAPI na porta `8000`
- Ambiente gráfico virtual (`Xvfb + Fluxbox`)
- Navegador Chromium instalado
- Acesso remoto ao desktop via browser (`noVNC`) na porta `8080`
- Acesso VNC direto na porta `5901`

### 1) Build da imagem

```bash
docker build -t api-rpa-senatran .
```

### 2) Subir o container

```bash
docker run --rm -it \
  -p 8000:8000 \
  -p 8080:8080 \
  -p 5901:5901 \
  --name api-rpa-senatran \
  api-rpa-senatran
```

### 3) Acessos

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Desktop no navegador (noVNC): http://localhost:8080/vnc.html
- VNC direto: `localhost:5901`

## Observações

- `pywinauto` foi mantido apenas para Windows e é ignorado no Linux/Docker.
- O container usa `supervisord` para manter API + UI rodando no mesmo processo principal.
