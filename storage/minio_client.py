"""
storage/minio_client.py
Upload de arquivos para MinIO S3.
Configure as variáveis no .env antes de usar.
"""
import os
from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv

load_dotenv()

MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET     = os.getenv("MINIO_BUCKET", "multas")
MINIO_SECURE     = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_PUBLIC_URL = os.getenv("MINIO_PUBLIC_URL", f"http://{MINIO_ENDPOINT}")

_client: Minio | None = None


def get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
        )
        # Cria bucket se não existir
        if not _client.bucket_exists(MINIO_BUCKET):
            _client.make_bucket(MINIO_BUCKET)
            print(f"Bucket '{MINIO_BUCKET}' criado.")
    return _client


def upload_pdf(caminho_local: str, object_name: str) -> str:
    """
    Faz upload de um PDF para o MinIO.

    Parâmetros:
        caminho_local: caminho do arquivo no disco
        object_name  : chave no bucket (ex: "PMJ3687/autuacao.pdf")

    Retorna a URL pública do arquivo.
    """
    client = get_client()
    try:
        client.fput_object(
            MINIO_BUCKET,
            object_name,
            caminho_local,
            content_type="application/pdf",
        )
        url = f"{MINIO_PUBLIC_URL}/{MINIO_BUCKET}/{object_name}"
        print(f"Upload OK: {url}")
        return url
    except S3Error as e:
        print(f"[ERRO MinIO] {e}")
        raise


def gerar_url_temporaria(object_name: str, expires_horas: int = 24) -> str:
    """Gera uma URL pré-assinada com validade em horas."""
    from datetime import timedelta
    client = get_client()
    url = client.presigned_get_object(
        MINIO_BUCKET,
        object_name,
        expires=timedelta(hours=expires_horas),
    )
    return url
