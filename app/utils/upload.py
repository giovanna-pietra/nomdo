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


def salvar_arquivo(arquivo, pasta: str | None = None) -> str | None:
    """
    Valida e salva o arquivo enviado pelo usuário.
    Retorna o nome do arquivo salvo, ou None se inválido/ausente.

    `pasta` opcional sobrescreve UPLOAD_FOLDER — usado por
    salvar_arquivo_documento() pra guardar documentos de hóspede (RG/CPF
    etc.) fora da pasta pública de uploads (fotos de imóvel, avatar).
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

    upload_folder = pasta or current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)

    caminho = os.path.join(upload_folder, unique_name)
    arquivo.save(caminho)

    return unique_name


def deletar_arquivo(filename: str | None, pasta: str | None = None) -> None:
    """Remove arquivo do disco; ignora erros silenciosamente.

    `pasta` opcional sobrescreve UPLOAD_FOLDER (ver salvar_arquivo)."""
    if not filename:
        return

    # Aceita tanto "foto.jpg" quanto "uploads/foto.jpg"
    basename = os.path.basename(filename)
    upload_folder = pasta or current_app.config["UPLOAD_FOLDER"]
    caminho = os.path.join(upload_folder, basename)

    try:
        if os.path.exists(caminho):
            os.remove(caminho)
    except OSError as e:
        current_app.logger.error("Erro ao deletar arquivo %s: %s", caminho, e)


def salvar_arquivo_documento(arquivo) -> str | None:
    """
    Mesma validação de salvar_arquivo(), mas grava em UPLOAD_FOLDER_DOCUMENTOS
    — uma pasta FORA de app/static, que não é servida publicamente pelo
    Flask. Usado só pros documentos sensíveis do hóspede (RG/CPF, foto do
    pet etc. — ver app/routes/documentos.py), diferente das fotos de
    imóvel/avatar, que continuam públicas de propósito (aparecem no
    anúncio/guia público do imóvel).

    O arquivo só fica acessível de volta através de uma rota protegida
    (ver documentos_recebidos.servir_arquivo), que confere se quem está
    pedindo é de fato o anfitrião daquele imóvel antes de servir a imagem.
    """
    return salvar_arquivo(arquivo, pasta=current_app.config["UPLOAD_FOLDER_DOCUMENTOS"])


def deletar_arquivo_documento(filename: str | None) -> None:
    """Par de salvar_arquivo_documento() — apaga da pasta privada de documentos."""
    deletar_arquivo(filename, pasta=current_app.config["UPLOAD_FOLDER_DOCUMENTOS"])
