"""
app/utils/upload.py
Gerenciamento de uploads de arquivos — dois backends escolhidos
automaticamente conforme o ambiente:

  • Disco local (comportamento histórico) — usado em dev, ou em produção
    se as variáveis R2_* não estiverem configuradas.
  • Cloudflare R2 (armazenamento S3-compatible, via boto3) — usado
    automaticamente quando R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY /
    R2_BUCKET_NAME / R2_ENDPOINT_URL / R2_PUBLIC_BASE_URL estão
    preenchidas (ver config/settings.py). Necessário porque o filesystem
    do Render é efêmero: qualquer coisa salva em disco (fotos de imóvel,
    avatar, documento do hóspede) é perdida a cada redeploy/restart.

Ninguém que já chama salvar_arquivo()/deletar_arquivo() precisa mudar nada
— mesma assinatura, mesmo valor de retorno (nome do arquivo). A escolha de
backend é 100% interna a este módulo.
"""

import mimetypes
import os
import secrets

from flask import current_app, url_for
from werkzeug.utils import secure_filename


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_FILENAME_LENGTH = 100


def _extensao_permitida(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def _r2_configurado() -> bool:
    cfg = current_app.config
    return bool(
        cfg.get("R2_ACCESS_KEY_ID")
        and cfg.get("R2_SECRET_ACCESS_KEY")
        and cfg.get("R2_BUCKET_NAME")
        and cfg.get("R2_ENDPOINT_URL")
    )


def _r2_client():
    # Import tardio: só exige boto3 instalado se o R2 estiver de fato
    # configurado — dev local sem essas variáveis continua funcionando
    # mesmo sem o pacote instalado.
    import boto3
    cfg = current_app.config
    return boto3.client(
        "s3",
        endpoint_url=cfg["R2_ENDPOINT_URL"],
        aws_access_key_id=cfg["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=cfg["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def _r2_prefixo(pasta_local: str | None) -> str:
    """
    Traduz a pasta local pedida (UPLOAD_FOLDER ou UPLOAD_FOLDER_DOCUMENTOS)
    num prefixo de "pasta" dentro do bucket R2. Documentos do hóspede
    (RG/CPF etc.) ficam sob "documentos/" — nunca é exposto por URL pública,
    só lido de volta via ler_arquivo_documento(), atrás da rota protegida
    (documentos_recebidos.servir_arquivo). O resto ("uploads/") é fotos de
    imóvel/avatar, que já são públicas de propósito hoje (aparecem no
    anúncio/guia do imóvel).
    """
    if pasta_local and pasta_local == current_app.config.get("UPLOAD_FOLDER_DOCUMENTOS"):
        return "documentos"
    return "uploads"


def salvar_arquivo(arquivo, pasta: str | None = None) -> str | None:
    """
    Valida e salva o arquivo enviado pelo usuário — no R2 se configurado,
    senão em disco local. Retorna o nome do arquivo salvo, ou None se
    inválido/ausente.

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

    if _r2_configurado():
        chave = f"{_r2_prefixo(pasta)}/{unique_name}"
        content_type = arquivo.mimetype or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        try:
            _r2_client().put_object(
                Bucket=current_app.config["R2_BUCKET_NAME"],
                Key=chave,
                Body=arquivo.read(),
                ContentType=content_type,
            )
        except Exception:
            current_app.logger.exception("Falha ao enviar arquivo pro R2 (chave=%s)", chave)
            return None
        return unique_name

    upload_folder = pasta or current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)

    caminho = os.path.join(upload_folder, unique_name)
    arquivo.save(caminho)

    return unique_name


def deletar_arquivo(filename: str | None, pasta: str | None = None) -> None:
    """Remove o arquivo (do R2 ou do disco local, conforme configurado);
    ignora erros silenciosamente.

    `pasta` opcional sobrescreve UPLOAD_FOLDER (ver salvar_arquivo)."""
    if not filename:
        return

    # Aceita tanto "foto.jpg" quanto "uploads/foto.jpg"
    basename = os.path.basename(filename)

    if _r2_configurado():
        chave = f"{_r2_prefixo(pasta)}/{basename}"
        try:
            _r2_client().delete_object(Bucket=current_app.config["R2_BUCKET_NAME"], Key=chave)
        except Exception as e:
            current_app.logger.error("Erro ao deletar arquivo do R2 %s: %s", chave, e)
        return

    upload_folder = pasta or current_app.config["UPLOAD_FOLDER"]
    caminho = os.path.join(upload_folder, basename)

    try:
        if os.path.exists(caminho):
            os.remove(caminho)
    except OSError as e:
        current_app.logger.error("Erro ao deletar arquivo %s: %s", caminho, e)


def salvar_arquivo_documento(arquivo) -> str | None:
    """
    Mesma validação de salvar_arquivo(), mas grava na "pasta" de documentos
    (UPLOAD_FOLDER_DOCUMENTOS local, ou prefixo "documentos/" no R2) — que
    nunca é servida publicamente. Usado só pros documentos sensíveis do
    hóspede (RG/CPF, foto do pet etc. — ver app/routes/documentos.py),
    diferente das fotos de imóvel/avatar, que continuam públicas de
    propósito (aparecem no anúncio/guia público do imóvel).

    O arquivo só fica acessível de volta através de uma rota protegida
    (ver documentos_recebidos.servir_arquivo), que confere se quem está
    pedindo é de fato o anfitrião daquele imóvel antes de servir a imagem.
    """
    return salvar_arquivo(arquivo, pasta=current_app.config["UPLOAD_FOLDER_DOCUMENTOS"])


def deletar_arquivo_documento(filename: str | None) -> None:
    """Par de salvar_arquivo_documento() — apaga da pasta privada de documentos."""
    deletar_arquivo(filename, pasta=current_app.config["UPLOAD_FOLDER_DOCUMENTOS"])


def ler_arquivo_documento(filename: str | None):
    """
    Lê os bytes + content-type de um documento privado (RG/CPF etc.), do R2
    ou do disco local conforme configurado. Usado só pela rota protegida
    documentos_recebidos.servir_arquivo (que já confere login + posse do
    imóvel antes de chamar isso — aqui não tem checagem nenhuma de novo).

    Retorna (bytes, content_type). content_type vem None quando lido do
    disco local (o call-site já sabe adivinhar via mimetypes nesse caso).
    Retorna (None, None) se o arquivo não existir.
    """
    if not filename:
        return None, None

    basename = os.path.basename(filename)

    if _r2_configurado():
        chave = f"documentos/{basename}"
        try:
            obj = _r2_client().get_object(Bucket=current_app.config["R2_BUCKET_NAME"], Key=chave)
            return obj["Body"].read(), obj.get("ContentType")
        except Exception as e:
            current_app.logger.error("Erro ao ler documento do R2 %s: %s", chave, e)
            return None, None

    caminho = os.path.join(current_app.config["UPLOAD_FOLDER_DOCUMENTOS"], basename)
    if not os.path.exists(caminho):
        return None, None
    with open(caminho, "rb") as f:
        return f.read(), None


def url_arquivo_publico(nome_arquivo: str | None) -> str | None:
    """
    Constrói a URL pública de um arquivo salvo por salvar_arquivo() (fotos
    de imóvel, avatar) — URL do R2 quando configurado (R2_PUBLIC_BASE_URL),
    senão a rota estática local de sempre (/static/uploads/<arquivo>).

    Aceita tanto "foto.jpg" (convenção de Imovel.foto_principal) quanto
    "uploads/foto.jpg" (convenção antiga de User.foto) — normaliza pro
    nome puro do arquivo antes de montar a URL, pra nunca duplicar
    "uploads/uploads/...".

    Registrado também como filtro Jinja "url_upload" (ver app/__init__.py),
    pra usar direto nos templates: {{ imovel.foto_principal|url_upload }}.
    """
    if not nome_arquivo:
        return None

    nome = nome_arquivo.split("/", 1)[-1] if nome_arquivo.startswith("uploads/") else nome_arquivo

    base = (current_app.config.get("R2_PUBLIC_BASE_URL") or "").strip()
    if base:
        return f"{base.rstrip('/')}/uploads/{nome}"

    return url_for("static", filename=f"uploads/{nome}", _external=True)
