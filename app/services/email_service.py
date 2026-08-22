"""
app/services/email_service.py
Serviço centralizado de envio de e-mails.
"""

from email.mime.application import MIMEApplication
import smtplib

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app


# ==========================================================
# SMTP
# ==========================================================

def _smtp_enviar(destinatario: str, mensagem: MIMEMultipart) -> None:

    remetente = current_app.config["EMAIL_REMETENTE"]
    senha = current_app.config["EMAIL_SENHA"]

    try:

        # timeout=10: sem isso, se o SMTP do Gmail ficar lento/inacessível
        # (rede da hospedagem, bloqueio de saída, etc.) a conexão trava sem
        # limite — o request de cadastro/login fica pendurado até o gunicorn
        # matar o worker por timeout (120s, ver gunicorn.conf.py), e quem
        # está usando o site recebe "502 Bad Gateway" em vez do fluxo normal
        # (que já tolera falha de e-mail sem travar nada). Com o timeout
        # aqui, uma falha de rede vira erro rápido e só loga, como já era
        # a intenção original deste try/except.
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as servidor:

            servidor.login(remetente, senha)
            servidor.send_message(mensagem)

            current_app.logger.info(
                "E-mail enviado para %s",
                destinatario
            )

    except Exception as exc:

        current_app.logger.error(
            "Erro ao enviar e-mail para %s: %s",
            destinatario,
            exc
        )


# ==========================================================
# TEMPLATE BASE
# ==========================================================

def _template_email(
    titulo: str,
    subtitulo: str,
    conteudo: str,
    codigo: str | None = None
) -> str:

    bloco_codigo = ""

    if codigo:

        bloco_codigo = f"""
<div style="
    background:#eaf1fe;
    border:2px dashed #0052D4;
    border-radius:14px;
    padding:22px;
    margin:30px 0;
    text-align:center;
">

    <p style="
        margin:0 0 14px 0;
        font-size:13px;
        color:#666;
        letter-spacing:1px;
        text-transform:uppercase;
        font-weight:600;
    ">
        Código de verificação
    </p>

    <div style="
        background:#ffffff;
        border-radius:10px;
        padding:16px;
        border:1px solid #cfe0fb;
        user-select:all;
    ">

        <span style="
            font-size:32px;
            font-weight:800;
            letter-spacing:8px;
            color:#0052D4;
            font-family:Arial,sans-serif;
            display:block;
        ">
            {codigo}
        </span>

    </div>

    <p style="
        margin:14px 0 0 0;
        color:#777;
        font-size:12px;
    ">
        Toque e segure para copiar
    </p>

</div>
"""

    return f"""
    <html>
    <body style="
        margin:0;
        padding:0;
        background:#f5f5f5;
        font-family:Arial,sans-serif;
    ">

        <div style="
            max-width:600px;
            margin:40px auto;
            background:#ffffff;
            border-radius:18px;
            overflow:hidden;
            box-shadow:0 5px 20px rgba(0,0,0,0.08);
        ">

            <div style="
                background:linear-gradient(135deg,#0052D4,#4364F7);
                padding:35px;
                text-align:center;
            ">
                <h1 style="
                    color:white;
                    margin:0;
                    font-size:32px;
                ">
                    Nomdo
                </h1>
            </div>

            <div style="padding:40px; color:#333;">

                <h2 style="
                    margin-top:0;
                    font-size:26px;
                    color:#222;
                ">
                    {titulo}
                </h2>

                <p style="
                    font-size:16px;
                    line-height:1.7;
                    color:#555;
                ">
                    {subtitulo}
                </p>

                {bloco_codigo}

                <div style="
                    font-size:15px;
                    line-height:1.7;
                    color:#555;
                ">
                    {conteudo}
                </div>

            </div>

            <div style="
                background:#fafafa;
                padding:20px;
                text-align:center;
                font-size:12px;
                color:#999;
            ">
                © 2026 Nomdo — Todos os direitos reservados
            </div>

        </div>

    </body>
    </html>
    """


# ==========================================================
# MONTAR MENSAGEM
# ==========================================================

def _montar_mensagem(
    destinatario: str,
    assunto: str,
    html: str,
    anexos: list | None = None,
) -> MIMEMultipart:

    remetente = current_app.config["EMAIL_REMETENTE"]

    # mixed suporta anexos + html
    mensagem = MIMEMultipart("mixed")
    mensagem["Subject"] = assunto
    mensagem["From"] = remetente
    mensagem["To"] = destinatario

    parte_html = MIMEMultipart("alternative")
    parte_html.attach(MIMEText(html, "html"))
    mensagem.attach(parte_html)

    if anexos:
        for arquivo in anexos:
            if not getattr(arquivo, "filename", ""):
                continue
            payload = MIMEApplication(arquivo.read(), Name=arquivo.filename)
            payload["Content-Disposition"] = f'attachment; filename="{arquivo.filename}"'
            mensagem.attach(payload)
            try:
                arquivo.seek(0)
            except Exception:
                pass

    return mensagem


# ==========================================================
# VERIFICAÇÃO DE CADASTRO
# ==========================================================

def enviar_codigo_verificacao(
    destinatario: str,
    nome: str,
    codigo: str
) -> None:

    html = _template_email(
        titulo=f"Olá, {nome}! 👋",
        subtitulo="Seu cadastro foi iniciado com sucesso.",
        codigo=codigo,
        conteudo="""
        <p>
            Use o código acima para confirmar sua conta.
        </p>

        <p>
            O código expira em 
            <strong> 
            15 minutos 
            </strong>.
        </p>

        <p>
            Se você não realizou esse cadastro, ignore este e-mail.
        </p>
        """
    )

    msg = _montar_mensagem(
        destinatario,
        "Código de confirmação — Nomdo",
        html
    )

    _smtp_enviar(destinatario, msg)


# ==========================================================
# RECUPERAÇÃO DE SENHA
# ==========================================================

def enviar_codigo_recuperacao(
    destinatario: str,
    nome: str,
    codigo: str
) -> None:

    html = _template_email(
        titulo=f"Olá, {nome}!",
        subtitulo="Recebemos uma solicitação de recuperação de senha.",
        codigo=codigo,
        conteudo="""
        <p>
            Utilize o código acima para redefinir sua senha.
        </p>

        <p>
            <strong> 
            Caso não tenha solicitado a recuperação, 
            <strong>
            ignore este e-mail.
        </p>
        """
    )

    msg = _montar_mensagem(
        destinatario,
        "Recuperação de senha — Nomdo",
        html
    )

    _smtp_enviar(destinatario, msg)


# ==========================================================
# DESPEDIDA
# ==========================================================

def enviar_email_despedida(
    destinatario: str,
    nome: str
) -> None:

    html = _template_email(
        titulo=f"Até logo, {nome}!",
        subtitulo="Sua conta foi removida com sucesso.",
        conteudo="""
        <p>
            Esperamos ver você novamente em breve.
        </p>
<br>
        <strong>
            Obrigado por utilizar o Nomdo!
        </strong>
        """
    )

    msg = _montar_mensagem(
        destinatario,
        "Conta encerrada — Nomdo",
        html
    )

    _smtp_enviar(destinatario, msg)

# ==========================================================
# CONVITE DE ANFITRIÃO-AJUDANTE (hierarquia Proprietário/Anfitrião)
# ==========================================================

def enviar_email_convite_anfitriao(
    destinatario: str,
    nome_proprietario: str,
    link_convite: str,
    ja_tem_conta: bool,
) -> bool:
    """
    Convida alguém para se tornar Anfitrião-ajudante de uma conta
    Proprietária — passará a ver e operar os imóveis, estadias, hub etc.
    do Proprietário, sem acesso ao dashboard financeiro dele.
    """
    texto_acao = (
        "Basta entrar na sua conta Nomdo e confirmar o convite."
        if ja_tem_conta else
        "Basta criar sua conta gratuita no Nomdo — o convite já estará esperando por você."
    )

    conteudo = f"""
    <div style="background:#eef4ff;border:1px solid #cfe0fb;border-radius:14px;
                padding:20px 22px;margin:10px 0 24px;">
        <p style="margin:0;font-size:11px;font-weight:700;letter-spacing:.06em;
                  text-transform:uppercase;color:#0052D4;">
            🤝 Convite de equipe
        </p>
        <p style="margin:8px 0 0;font-size:17px;font-weight:800;color:#1e293b;">
            {nome_proprietario} te convidou pra ajudar como Anfitrião
        </p>
    </div>

    <p style="margin:0 0 20px;color:#475569;font-size:14px;line-height:1.6;">
        Você vai poder acessar e cuidar dos imóveis, estadias e do dia a dia
        operacional dessa conta. {texto_acao}
    </p>

    <div style="text-align:center;">
        <a href="{link_convite}"
           style="display:inline-block;background:linear-gradient(135deg,#0052D4,#4364F7);
                  color:#ffffff;text-decoration:none;padding:13px 30px;
                  border-radius:12px;font-weight:700;font-size:14px;">
            Aceitar convite
        </a>
    </div>

    <p style="margin:20px 0 0;color:#94a3b8;font-size:12px;">
        Se você não esperava este convite, pode ignorar este e-mail.
    </p>
    """

    html = _template_email(
        titulo="Você foi convidado(a)! 🤝",
        subtitulo=f"{nome_proprietario} quer sua ajuda no Nomdo.",
        conteudo=conteudo,
    )

    msg = _montar_mensagem(
        destinatario,
        f"🤝 Convite de {nome_proprietario} — Nomdo",
        html,
    )

    _smtp_enviar(destinatario, msg)
    return True


def enviar_email_suporte(nome, email_usuario, tipo_contato, contato, mensagem, lista_anexos=None):
    email_remetente = current_app.config["EMAIL_REMETENTE"] 
    metodo_formatado = tipo_contato.capitalize()

    html = _template_email(
        titulo="Novo chamado de suporte",
        subtitulo=f"Solicitação enviada por {nome}",
        conteudo=f"""
            <div style="background:#f9f9f9; padding:15px; border-radius:10px; border:1px solid #eee;">
                <p><strong>Usuário:</strong> {nome}</p>
                <p><strong>E-mail da conta:</strong> {email_usuario}</p>
                <p><strong>Método de retorno:</strong> {metodo_formatado}</p>
                <p><strong>Contato para Retorno:</strong> {contato}</p>
            </div>
            <p style="margin-top:20px; white-space: pre-wrap;">{mensagem}</p>
        """
    )

    msg = _montar_mensagem(
        email_remetente,
        f"SUPORTE: {nome}",
        html,
        anexos=lista_anexos # Passa os arquivos para a montagem
    )

    _smtp_enviar(email_remetente, msg)


# ==========================================================
# LEMBRETES OPERACIONAIS DO HUB DO ANFITRIÃO
# (troca de pilha, limpeza pós-checkout, checkup de eletrônicos,
#  reposição de café/papel higiênico, ou qualquer rotina personalizada)
# ==========================================================

def enviar_email_lembrete(
    destinatario: str,
    nome_usuario: str,
    tipo: str,
    imovel_titulo: str,
    titulo_tarefa: str,
    descricao: str | None = None,
    imovel_endereco: str | None = None,
) -> bool:
    """
    Envia um e-mail avisando o anfitrião sobre uma pendência operacional
    gerada pelo Hub (seja por rotina recorrente — pilha, eletrônicos, café,
    papel higiênico, custom — seja por evento, como limpeza após checkout).

    Usa o mesmo motor de envio (smtplib) já usado pelos outros e-mails
    deste arquivo — nenhuma dependência nova é necessária.

    Retorno
    -------
    bool : True se o envio foi tentado (erros já são logados por
           `_smtp_enviar` sem interromper o fluxo do chamador).
    """
    # Import local para evitar import circular entre models e services.
    from app.models.hub import TIPOS_LEMBRETE

    meta = TIPOS_LEMBRETE.get(tipo, {"icone": "📌", "label": "Lembrete", "cor": "#4364F7"})
    primeiro_nome = nome_usuario.split()[0] if nome_usuario else "Anfitrião"

    endereco_html = (
        f'<p style="margin:4px 0 0;color:#64748b;font-size:13px;">{imovel_endereco}</p>'
        if imovel_endereco else ""
    )
    descricao_html = (
        f'<p style="margin-top:14px;color:#475569;font-size:14px;line-height:1.6;">{descricao}</p>'
        if descricao else ""
    )

    conteudo = f"""
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;
                padding:20px 22px;margin:10px 0 24px;">
        <p style="margin:0;font-size:11px;font-weight:700;letter-spacing:.06em;
                  text-transform:uppercase;color:{meta['cor']};">
            {meta['icone']} {meta['label']}
        </p>
        <p style="margin:8px 0 0;font-size:17px;font-weight:800;color:#1e293b;">
            {titulo_tarefa}
        </p>
        <p style="margin:4px 0 0;color:#64748b;font-size:13px;">
            {imovel_titulo}
        </p>
        {endereco_html}
        {descricao_html}
    </div>

    <div style="text-align:center;">
        <a href="#"
           style="display:inline-block;background:linear-gradient(135deg,#0052D4,#4364F7);
                  color:#ffffff;text-decoration:none;padding:13px 30px;
                  border-radius:12px;font-weight:700;font-size:14px;">
            Abrir Hub do Anfitrião
        </a>
    </div>
    """

    html = _template_email(
        titulo=f"{meta['icone']} {meta['label']}",
        subtitulo=f"Olá, {primeiro_nome}! Uma pendência precisa da sua atenção.",
        conteudo=conteudo,
    )

    msg = _montar_mensagem(
        destinatario,
        f"{meta['icone']} {titulo_tarefa} — Nomdo",
        html,
    )

    _smtp_enviar(destinatario, msg)
    return True


# ==========================================================
# E-MAILS AO HÓSPEDE (guia pré-estadia + pedido de avaliação)
# ==========================================================

def enviar_email_guia_hospede(
    destinatario: str,
    nome_hospede: str,
    imovel_titulo: str,
    link_guia: str,
    data_checkin_fmt: str,
    hora_checkin: str | None = None,
) -> bool:
    """
    Envia ao hóspede, antes da estadia, o link do Guia Digital do imóvel
    (mesmo conteúdo acessado pelo QR code: wifi, regras, contato, política
    de cancelamento etc.) — pra ele já chegar preparado, sem precisar
    escanear nada na chegada.
    """
    primeiro_nome = nome_hospede.split()[0] if nome_hospede else "Hóspede"
    hora_txt = f" às {hora_checkin}" if hora_checkin else ""

    conteudo = f"""
    <div style="background:#eef4ff;border:1px solid #cfe0fb;border-radius:14px;
                padding:20px 22px;margin:10px 0 24px;">
        <p style="margin:0;font-size:11px;font-weight:700;letter-spacing:.06em;
                  text-transform:uppercase;color:#0052D4;">
            🏠 Sua próxima estadia
        </p>
        <p style="margin:8px 0 0;font-size:17px;font-weight:800;color:#1e293b;">
            {imovel_titulo}
        </p>
        <p style="margin:4px 0 0;color:#64748b;font-size:13px;">
            Check-in em {data_checkin_fmt}{hora_txt}
        </p>
    </div>

    <p style="margin:0 0 20px;color:#475569;font-size:14px;line-height:1.6;">
        Preparamos um guia completo com Wi-Fi, regras da casa, contato do
        anfitrião e tudo que você precisa saber antes de chegar.
    </p>

    <div style="text-align:center;">
        <a href="{link_guia}"
           style="display:inline-block;background:linear-gradient(135deg,#0052D4,#4364F7);
                  color:#ffffff;text-decoration:none;padding:13px 30px;
                  border-radius:12px;font-weight:700;font-size:14px;">
            Abrir Guia da Estadia
        </a>
    </div>
    """

    html = _template_email(
        titulo=f"Olá, {primeiro_nome}! 🎒",
        subtitulo="Sua estadia está chegando — aqui está tudo o que você precisa saber.",
        conteudo=conteudo,
    )

    msg = _montar_mensagem(
        destinatario,
        f"🏠 Guia da sua estadia em {imovel_titulo} — Nomdo",
        html,
    )

    _smtp_enviar(destinatario, msg)
    return True


def enviar_email_solicitar_avaliacao(
    destinatario: str,
    nome_hospede: str,
    imovel_titulo: str,
    link_avaliacao: str,
) -> bool:
    """
    Envia ao hóspede, depois da estadia, um convite pra avaliar a
    experiência. A avaliação (nota + comentário) fica salva e o
    anfitrião recebe uma notificação por e-mail em seguida.
    """
    primeiro_nome = nome_hospede.split()[0] if nome_hospede else "Hóspede"

    conteudo = f"""
    <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:14px;
                padding:20px 22px;margin:10px 0 24px;text-align:center;">
        <p style="margin:0;font-size:28px;">⭐️⭐️⭐️⭐️⭐️</p>
        <p style="margin:10px 0 0;font-size:15px;font-weight:800;color:#1e293b;">
            Como foi sua estadia em {imovel_titulo}?
        </p>
    </div>

    <p style="margin:0 0 20px;color:#475569;font-size:14px;line-height:1.6;">
        Sua opinião ajuda o anfitrião a melhorar a experiência pros
        próximos hóspedes. Leva menos de um minuto.
    </p>

    <div style="text-align:center;">
        <a href="{link_avaliacao}"
           style="display:inline-block;background:linear-gradient(135deg,#0052D4,#4364F7);
                  color:#ffffff;text-decoration:none;padding:13px 30px;
                  border-radius:12px;font-weight:700;font-size:14px;">
            Avaliar minha estadia
        </a>
    </div>
    """

    html = _template_email(
        titulo=f"Obrigado por ficar com a gente, {primeiro_nome}!",
        subtitulo="Conte pra gente como foi sua experiência.",
        conteudo=conteudo,
    )

    msg = _montar_mensagem(
        destinatario,
        f"⭐️ Avalie sua estadia em {imovel_titulo} — Nomdo",
        html,
    )

    _smtp_enviar(destinatario, msg)
    return True


def enviar_email_nova_avaliacao(
    destinatario_host: str,
    nome_hospede: str,
    imovel_titulo: str,
    nota: int,
    comentario: str | None = None,
) -> bool:
    """Notifica o anfitrião quando um hóspede envia uma nova avaliação."""
    estrelas = "⭐️" * max(1, min(5, nota))
    comentario_html = (
        f'<p style="margin-top:14px;color:#475569;font-size:14px;line-height:1.6;">"{comentario}"</p>'
        if comentario else ""
    )

    conteudo = f"""
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;
                padding:20px 22px;margin:10px 0 24px;">
        <p style="margin:0;font-size:20px;">{estrelas}</p>
        <p style="margin:10px 0 0;font-size:15px;font-weight:800;color:#1e293b;">
            {nome_hospede or "Um hóspede"} avaliou {imovel_titulo}
        </p>
        {comentario_html}
    </div>
    """

    html = _template_email(
        titulo="Nova avaliação recebida ⭐️",
        subtitulo="Um hóspede acabou de avaliar sua estadia.",
        conteudo=conteudo,
    )

    msg = _montar_mensagem(
        destinatario_host,
        f"⭐️ Nova avaliação — {imovel_titulo}",
        html,
    )

    _smtp_enviar(destinatario_host, msg)
    return True


# ==========================================================
# FORMULÁRIO DE DOCUMENTOS DO HÓSPEDE
# (genérico/customizável — RG, CPF, placa do carro, foto do pet etc.)
# ==========================================================

def enviar_email_formulario_documentos(
    destinatario: str,
    nome_hospede: str,
    imovel_titulo: str,
    link_formulario: str,
    data_checkin_fmt: str,
) -> bool:
    """
    Convida o hóspede a enviar os documentos pedidos pelo anfitrião antes
    da chegada (RG/CPF, placa do carro, foto do pet etc, conforme
    configurado em Imovel.documentos_campos). Envio único, com link
    expirável — um por estadia.
    """
    primeiro_nome = nome_hospede.split()[0] if nome_hospede else "Hóspede"

    conteudo = f"""
    <div style="background:#eef4ff;border:1px solid #cfe0fb;border-radius:14px;
                padding:20px 22px;margin:10px 0 24px;">
        <p style="margin:0;font-size:17px;font-weight:800;color:#1e293b;">
            {imovel_titulo}
        </p>
        <p style="margin:4px 0 0;color:#64748b;font-size:13px;">
            Check-in em {data_checkin_fmt}
        </p>
    </div>

    <p style="margin:0 0 20px;color:#475569;font-size:14px;line-height:1.6;">
        Antes da sua chegada, o anfitrião pediu alguns documentos e dados
        rapidinho (como RG/CPF, placa do carro ou foto do pet, conforme o
        caso) — leva poucos minutos e ajuda a deixar tudo pronto pra sua
        estadia. Depois de enviar, você já recebe o acesso ao guia digital
        do imóvel.
    </p>

    <div style="text-align:center;">
        <a href="{link_formulario}"
           style="display:inline-block;background:linear-gradient(135deg,#0052D4,#4364F7);
                  color:#ffffff;text-decoration:none;padding:13px 30px;
                  border-radius:12px;font-weight:700;font-size:14px;">
            Enviar meus documentos
        </a>
    </div>

    <p style="margin:20px 0 0;color:#94a3b8;font-size:12px;text-align:center;">
        Esse link é pessoal e expira alguns dias após o check-out.
    </p>
    """

    html = _template_email(
        titulo="📄 Envie seus documentos antes da chegada",
        subtitulo=f"Olá, {primeiro_nome}! Falta um passo antes da sua estadia.",
        conteudo=conteudo,
    )

    msg = _montar_mensagem(
        destinatario,
        f"📄 Documentos pra sua estadia — {imovel_titulo}",
        html,
    )

    _smtp_enviar(destinatario, msg)
    return True