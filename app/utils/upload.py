"""
app/utils/upload.py
Gerenciamento seguro de uploads de arquivos.
Preparado para migração futura ao AWS S3 (troque _save_local por _save_s3).
"""

import os
import secrets
from flask import current_app
from werkzeug.utils import secure_filename


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_FILENAME_LENGTH = 100


def _extensao_permitida(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def salvar_arquivo(arquivo) -> str | None:
    """
    Valida e salva o arquivo enviado pelo usuário.
    Retorna o nome do arquivo salvo, ou None se inválido/ausente.
    """
    if not arquivo or arquivo.filename == "":
        return None

    if not _extensao_permitida(arquivo.filename):
        current_app.logger.warning(
            "Upload rejeitado — extensão não permitida: %s", arquivo.filename
        )
        return None

    filename = secure_filename(arquivo.filename)

    # Trunca nomes muito longos antes de adicionar prefixo
    if len(filename) > MAX_FILENAME_LENGTH:
        ext = filename.rsplit(".", 1)[1]
        filename = filename[:MAX_FILENAME_LENGTH] + "." + ext

    # Prefixo aleatório evita colisões e impede adivinhação de URLs
    unique_name = f"{secrets.token_hex(12)}_{filename}"

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)

    caminho = os.path.join(upload_folder, unique_name)
    arquivo.save(caminho)

    return unique_name


def deletar_arquivo(filename: str | None) -> None:
    """Remove arquivo do disco; ignora erros silenciosamente."""
    if not filename:
        return

    # Aceita tanto "foto.jpg" quanto "uploads/foto.jpg"
    basename = os.path.basename(filename)
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    caminho = os.path.join(upload_folder, basename)

    try:
        if os.path.exists(caminho):
            os.remove(caminho)
    except OSError as e:
        current_app.logger.error("Erro ao deletar arquivo %s: %s", caminho, e)
