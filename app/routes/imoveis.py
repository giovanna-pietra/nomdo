"""
app/routes/imoveis.py
"""
import json
import calendar
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash, jsonify, current_app
)
from app.extensions import db
from app.models import User, Grupo, Imovel, Estadia, Avaliacao, Assinatura
from app.services.email_service import enviar_email_nova_avaliacao
from app.services.push_service import enviar_push_notificacao
from app.services import planos, geocoding_service
from app.utils import login_required, salvar_arquivo, deletar_arquivo, formatar_nome_exibicao, get_effective_owner_id, t_flash

imoveis_bp = Blueprint("imoveis", __name__)


def _bloqueado_por_limite_de_plano(owner_id: int) -> bool:
    """
    True se cadastrar mais um imóvel estouraria o limite do plano de
    assinatura ativo do Proprietário (ver app/services/planos.py e
    app/models/assinatura.py). Sem PAYWALL_ATIVO ligado, ou sem uma
    assinatura reconhecida (conta admin, ambiente de teste, ou dado
    legado sem Assinatura vinculada), nunca bloqueia — mesmo padrão de
    degradação graciosa usado nas outras integrações novas.
    """
    if not current_app.config.get("PAYWALL_ATIVO"):
        return False

    dono = db.session.get(User, owner_id)
    if not dono or dono.is_admin:
        return False

    assinatura = (
        Assinatura.query.filter_by(user_id=owner_id)
        .order_by(Assinatura.id.desc())
        .first()
    )
    if not assinatura or assinatura.status not in ("active", "overdue"):
        return False

    qtd_atual = Imovel.query.filter_by(user_id=owner_id).count()
    return not planos.plano_cobre(qtd_atual + 1, assinatura.plano)


# ── Context Helper ────────────────────────────────────────────────────────────

def _imoveis_ctx(user: User) -> dict:
    return {
        "user": user,
        "nome_usuario": formatar_nome_exibicao(user.nome),
        "nome_completo": user.nome,
        "categoria_usuario": user.categoria,
        "grupos": Grupo.query.filter_by(user_id=user.owner_id).all(),
        "imoveis": Imovel.query.filter_by(user_id=user.owner_id).all(),
    }


def _parse_num(val, cast=float):
    """Converte string BRL (ex: '1.200,50') para número."""
    if not val:
        return None
    try:
        return cast(str(val).replace(".", "").replace(",", "."))
    except (ValueError, TypeError):
        return None


def _parse_coord(val):
    """
    Converte lat/lng (vindos dos campos hidden preenchidos via JS/Nominatim,
    ex: '-23.5505') para float.

    IMPORTANTE: NÃO usar _parse_num aqui. _parse_num assume formato BRL
    (ponto = separador de milhar, vírgula = decimal) e remove o ponto —
    isso transformava '-23.5505' em -235505.0, corrompendo a coordenada
    salva no banco. Esse era o motivo do endereço/local aparecer errado
    na guia do hóspede (que usa lat/lng direto do banco), enquanto telas
    como "Editar"/"Visualizar" pareciam OK só porque re-geocodificavam o
    endereço quando notavam a coordenada fora do intervalo válido.
    """
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


_UFS_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}


def _extrair_uf_da_cidade(cidade: str | None) -> str | None:
    """
    O campo "cidade" do formulário de imóvel já vem pronto como "Cidade/UF"
    pra endereços do Brasil (ex: "São Paulo/SP" — ver _selecionarCidade() e
    _buscarCEPImovel() em imoveis.html), ou "Cidade, Estado, País" pra fora
    do Brasil. Aqui só extraímos a UF quando reconhecível, pra poder cruzar
    com feriados estaduais e agrupar oportunidades de precificação por
    região (ver app/services/precificacao.py).
    """
    if not cidade or "/" not in cidade:
        return None
    uf = cidade.rsplit("/", 1)[-1].strip().upper()
    return uf if uf in _UFS_VALIDAS else None


# ── Página principal ──────────────────────────────────────────────────────────

@imoveis_bp.route("/imoveis")
@login_required
def imoveis():
    user = db.session.get(User, session["user_id"])
    return render_template("imoveis.html", **_imoveis_ctx(user))


# ── API: detalhes do imóvel ───────────────────────────────────────────────────

@imoveis_bp.route("/api/imovel/<int:id>")
@login_required
def api_detalhes_imovel(id: int):
    imovel = Imovel.query.filter_by(id=id, user_id=get_effective_owner_id()).first_or_404()

    hoje           = datetime.now()
    total_dias_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    primeiro_dia   = hoje.replace(day=1).date()
    ultimo_dia     = hoje.replace(day=total_dias_mes).date()

    # NOTA: isso costumava consultar o modelo "Reserva" (agenda de viagens
    # pessoais do usuário, sem relação real com o imóvel — nunca tinha
    # imovel_id preenchido, então sempre dava zero). O dado real de
    # ocupação/faturamento por imóvel é a Estadia.
    estadias = Estadia.query.filter_by(imovel_id=id).all()

    faturamento_mes = 0.0
    dias_ocupados   = 0

    for e in estadias:
        if e.status == "cancelada":
            continue
        if e.data_checkin and e.data_checkout and e.data_checkin <= ultimo_dia and e.data_checkout >= primeiro_dia:
            inicio_ef = max(e.data_checkin,  primeiro_dia)
            fim_ef    = min(e.data_checkout, ultimo_dia)
            dias_ocupados += max(0, (fim_ef - inicio_ef).days)
            if e.status != "bloqueio":
                # Líquido (o que o anfitrião de fato recebe) — antes usava
                # valor_bruto aqui, o que fazia esse card mostrar como lucro
                # um valor que pode não corresponder ao que sobra de verdade
                # (mesma inconsistência já corrigida no Dashboard/Início).
                faturamento_mes += float(e.valor_liquido or 0)
    pct = (dias_ocupados / total_dias_mes) * 100

    # ── Utensílios ────────────────────────────────────────────
    def _parse_utensilios(raw):
        if not raw or not raw.strip() or raw.strip() in ("[]", "null", ""):
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [u for u in parsed if isinstance(u, dict) and u.get("nome")]
        except (json.JSONDecodeError, TypeError):
            pass
        # fallback texto legado separado por vírgula
        return [{"nome": u.strip(), "valor": ""} for u in raw.split(",") if u.strip()]

    # ── Regras ───────────────────────────────────────────────
    def _parse_regras(raw):
        if not raw or not raw.strip() or raw.strip() in ("[]", "null", ""):
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [r for r in parsed if isinstance(r, dict) and r.get("texto")]
        except (json.JSONDecodeError, TypeError):
            pass
        # fallback texto legado separado por quebra de linha
        return [{"texto": r.strip(), "horario_inicio": "", "horario_fim": "", "multa": ""} for r in raw.split("\n") if r.strip()]

    utensilios = _parse_utensilios(imovel.utensilios)
    regras     = _parse_regras(imovel.regras)

    # Backfill: imóveis criados antes do slug público existir ficavam sem link,
    # o que fazia o QR Code do guia do hóspede não apontar para lugar nenhum.
    if not imovel.slug_publico:
        imovel.gerar_slug()
        db.session.commit()

    # Monta URL da foto se existir
    foto_url = f"/static/uploads/{imovel.foto_principal}" if imovel.foto_principal else None

    # ── Avaliações recebidas (hóspede -> anfitrião) ──────────────
    avaliacoes_qs = (
        Avaliacao.query
        .filter_by(imovel_id=imovel.id)
        .order_by(Avaliacao.created_at.desc())
        .limit(20)
        .all()
    )
    media_avaliacoes = None
    if avaliacoes_qs:
        media_avaliacoes = round(sum(a.nota for a in avaliacoes_qs) / len(avaliacoes_qs), 1)

    return jsonify({
        # Identificação
        "id":       imovel.id,
        "titulo":   imovel.titulo,
        "endereco": imovel.endereco,
        "ponto_referencia": imovel.ponto_referencia,
        "cidade":   imovel.cidade,
        "estado":   imovel.estado,
        "grupo":    imovel.grupo.nome if imovel.grupo else None,
        "foto_url": foto_url,
        "slug_publico": imovel.slug_publico,  # usado pro QR/link público (/g/<slug>)

        # Localização
        "lat": imovel.lat,
        "lng": imovel.lng,

        # Acesso
        "wifi_rede":       imovel.wifi_rede       or "",
        "wifi_senha":      imovel.wifi_senha      or "",
        "senha_fechadura": imovel.senha_fechadura or "",

        # Contato do anfitrião (aparece no guia do hóspede)
        "contato_telefone": imovel.contato_telefone or "",
        "contato_email":    imovel.contato_email    or "",

        # Conteúdo
        "utensilios": utensilios,
        "regras":     regras,

        # Operacional
        "checkin_padrao":      imovel.checkin_padrao      or "14:00",
        "checkout_padrao":     imovel.checkout_padrao     or "11:00",
        "diaria_base":         str(imovel.diaria_base or ""),
        "taxa_limpeza_padrao": str(imovel.taxa_limpeza_padrao or ""),
        "capacidade_max":      imovel.capacidade_max,
        "qtd_quartos":         imovel.qtd_quartos,
        "qtd_banheiros":       imovel.qtd_banheiros,
        "qtd_camas":           imovel.qtd_camas,

        # Cancelamento
        "prazo_cancelamento_gratis": imovel.prazo_cancelamento_gratis,
        "multa_tipo":  imovel.multa_tipo  or "sem_multa",
        "multa_valor": str(imovel.multa_valor or ""),

        # Checklist de hospedagem saiu daqui — agora é editado direto no
        # Hub do Anfitrião (Task #41), que é onde ele é realmente usado.

        # Formulário de Documentos do Hóspede (RG/CPF, placa do carro, foto
        # do pet etc.) — lista vazia aqui significa "nunca customizado"; o
        # envio usa o modelo padrão nesse caso (ver DEFAULT_CAMPOS_DOCUMENTOS
        # em app/services/documentos_service.py).
        "documentos_ativo":      bool(imovel.documentos_ativo),
        "documentos_dias_antes": imovel.documentos_dias_antes if imovel.documentos_dias_antes is not None else 3,
        "documentos_campos":     _parse_documentos_campos(imovel.documentos_campos),

        # E-mails automáticos ao hóspede
        "email_guia_ativo":            bool(imovel.email_guia_ativo),
        "email_guia_dias_antes":       imovel.email_guia_dias_antes if imovel.email_guia_dias_antes is not None else 1,
        "email_avaliacao_ativo":       bool(imovel.email_avaliacao_ativo),
        "email_avaliacao_dias_depois": imovel.email_avaliacao_dias_depois if imovel.email_avaliacao_dias_depois is not None else 2,

        # Avaliações recebidas
        "media_avaliacoes": media_avaliacoes,
        "qtd_avaliacoes":   len(avaliacoes_qs),
        "avaliacoes": [
            {
                "nome_hospede": a.nome_hospede or "Hóspede",
                "nota":         a.nota,
                "comentario":   a.comentario or "",
                "data":         a.created_at.strftime("%d/%m/%Y") if a.created_at else "",
            }
            for a in avaliacoes_qs
        ],

        # Stats
        "stats": {
            "ocupacao":    f"{min(100, round(pct, 1))}%",
            "faturamento": f"R$ {faturamento_mes:,.2f}",
            "dias_texto":  f"{dias_ocupados} dias",
        },
    })


# ── Imóveis — criar ───────────────────────────────────────────────────────────

@imoveis_bp.route("/salvar-imovel", methods=["POST"])
@login_required
def salvar_imovel():
    owner_id = get_effective_owner_id()

    # Bloqueio de plano: checado antes de qualquer outra validação pra
    # não processar upload de foto/JSON à toa quando o plano já não
    # cobre mais um imóvel (ver app/services/planos.py). O aviso em si
    # (SweetAlert2 + link pra /pagamento) é mostrado no template a
    # partir do parâmetro ?limite_imoveis=1 — flash() sozinho não
    # aparece nas páginas internas do dashboard (base_dash.html não
    # renderiza get_flashed_messages).
    if _bloqueado_por_limite_de_plano(owner_id):
        return redirect(url_for("imoveis.imoveis", limite_imoveis="1"))

    titulo   = request.form.get("titulo", "").strip()
    grupo_id = request.form.get("grupo_id") or None
    endereco = (request.form.get("endereco_completo") or request.form.get("endereco", "")).strip()

    if Imovel.query.filter_by(user_id=owner_id, titulo=titulo).first():
        flash(t_flash("Já existe um imóvel com esse nome."), "erro")
        return redirect(url_for("imoveis.imoveis"))

    # Endereço é obrigatório — sem ele o imóvel fica sem localização no mapa,
    # no guia do hóspede e na busca da listagem (ver ponto_referencia abaixo).
    if not endereco:
        flash(t_flash("Endereço é obrigatório."), "erro")
        return redirect(url_for("imoveis.imoveis"))

    foto = salvar_arquivo(request.files.get("foto_principal"))

    # Utensílios: vem como JSON string do frontend
    utensilios_json = _build_utensilios_json(request)
    regras_json     = _build_regras_json(request)

    cidade_form = request.form.get("cidade", "").strip() or None

    novo = Imovel(
        titulo              = titulo,
        endereco            = endereco,
        ponto_referencia    = request.form.get("ponto_referencia", "").strip() or None,
        cidade              = cidade_form,
        estado              = _extrair_uf_da_cidade(cidade_form),
        lat                 = _parse_coord(request.form.get("lat")),
        lng                 = _parse_coord(request.form.get("lng")),
        utensilios          = utensilios_json,
        regras              = regras_json,
        foto_principal      = foto,
        user_id             = owner_id,
        grupo_id            = grupo_id,

        # Acesso
        wifi_rede         = request.form.get("wifi_rede",       "").strip() or None,
        wifi_senha        = request.form.get("wifi_senha",      "").strip() or None,
        senha_fechadura   = request.form.get("senha_fechadura", "").strip() or None,

        # Contato do anfitrião
        contato_telefone  = request.form.get("contato_telefone", "").strip() or None,
        contato_email     = request.form.get("contato_email",    "").strip() or None,

        # Operacional
        checkin_padrao      = request.form.get("checkin_padrao",  "14:00"),
        checkout_padrao     = request.form.get("checkout_padrao", "11:00"),
        diaria_base         = _parse_num(request.form.get("diaria_base")),
        taxa_limpeza_padrao = _parse_num(request.form.get("taxa_limpeza_padrao")),
        capacidade_max      = _parse_num(request.form.get("capacidade_max"), int),
        qtd_quartos         = _parse_num(request.form.get("qtd_quartos"), int),
        qtd_banheiros       = _parse_num(request.form.get("qtd_banheiros"), int),
        qtd_camas           = _parse_num(request.form.get("qtd_camas"), int),

        # Cancelamento
        prazo_cancelamento_gratis = _parse_num(request.form.get("prazo_cancelamento_gratis"), int),
        multa_tipo  = request.form.get("multa_tipo"),
        multa_valor = _parse_num(request.form.get("multa_valor")),

        # Custos fixos mensais (manutenção/contas) agora são configurados em
        # Finanças (ver main.py: salvar_custos_fixos_imovel), não aqui na
        # criação do imóvel. Checklist de hospedagem também saiu daqui —
        # agora é editado no Hub do Anfitrião (Task #41).

        # Formulário de Documentos do Hóspede (RG/CPF, placa do carro, foto
        # do pet etc.) — disponível pra qualquer anfitrião, diferente do
        # formulário do condomínio (esse é fixo a um imóvel específico).
        documentos_ativo      = request.form.get("documentos_ativo") == "1",
        documentos_dias_antes = _parse_num(request.form.get("documentos_dias_antes"), int),
        documentos_campos     = _build_documentos_campos_json(request) or None,

        # E-mails automáticos ao hóspede
        email_guia_ativo            = request.form.get("email_guia_ativo") == "1",
        email_guia_dias_antes       = _parse_num(request.form.get("email_guia_dias_antes"), int),
        email_avaliacao_ativo       = request.form.get("email_avaliacao_ativo") == "1",
        email_avaliacao_dias_depois = _parse_num(request.form.get("email_avaliacao_dias_depois"), int),
    )

    # Gera o slug automaticamente antes de salvar no banco de dados
    novo.gerar_slug()

    db.session.add(novo)
    db.session.commit()
    flash(t_flash("Imóvel cadastrado com sucesso!"), "sucesso")
    return redirect(url_for("imoveis.imoveis"))


# ── Geocodificação (Google, backend) ─────────────────────────────────────────

@imoveis_bp.route("/api/geocode")
@login_required
def api_geocode():
    """
    Endpoint opcional pro frontend consultar geocodificação via Google
    (backend) em vez do Nominatim (que roda 100% no navegador hoje, ver
    imoveis.html). Nenhuma tela chama isso ainda — fica pronto pra
    quando fizer sentido usar (ex.: precisão melhor, endereços fora do
    Brasil). Sem GOOGLE_GEOCODING_API_KEY/GOOGLE_MAPS_API_KEY
    configuradas, devolve "encontrado: false" em vez de erro.
    """
    endereco = (request.args.get("endereco") or "").strip()
    if not endereco:
        return jsonify({"success": False, "message": t_flash("Informe um endereço.")}), 400

    resultado = geocoding_service.geocodificar_endereco(endereco)
    if not resultado:
        return jsonify({"success": True, "encontrado": False})

    return jsonify({"success": True, "encontrado": True, **resultado})


# ── Imóveis — editar ──────────────────────────────────────────────────────────

@imoveis_bp.route("/editar_imovel/<int:id>", methods=["POST"])
@login_required
def editar_imovel(id):
    owner_id = get_effective_owner_id()
    imovel = Imovel.query.filter_by(id=id, user_id=owner_id).first_or_404()
    titulo = request.form.get("titulo", "").strip()

    if Imovel.query.filter(
        Imovel.id != id,
        Imovel.user_id == owner_id,
        Imovel.titulo  == titulo
    ).first():
        flash(t_flash("Já existe imóvel com esse nome."), "erro")
        return redirect(url_for("imoveis.imoveis"))

    novo_endereco = (request.form.get("endereco_completo") or request.form.get("endereco", "")).strip()
    # Endereço é obrigatório — só aceita string vazia se o campo nem veio no
    # form (telas que não reenviam endereço), nunca um valor apagado de propósito.
    if "endereco_completo" in request.form or "endereco" in request.form:
        if not novo_endereco:
            flash(t_flash("Endereço é obrigatório."), "erro")
            return redirect(url_for("imoveis.imoveis"))

    # Se o título mudar, atualiza o slug dinamicamente
    if imovel.titulo != titulo:
        imovel.titulo = titulo
        imovel.gerar_slug()
    else:
        imovel.titulo = titulo
        # Backfill: imóveis antigos sem slug ficavam com QR/link do guia quebrado
        if not imovel.slug_publico:
            imovel.gerar_slug()

    imovel.endereco         = novo_endereco or imovel.endereco
    imovel.ponto_referencia = request.form.get("ponto_referencia", "").strip() or None
    if "cidade" in request.form:
        cidade_form    = request.form.get("cidade", "").strip() or None
        imovel.cidade  = cidade_form
        imovel.estado  = _extrair_uf_da_cidade(cidade_form)
    imovel.grupo_id  = request.form.get("grupo_id") or None
    lat_val = _parse_coord(request.form.get("lat"))
    lng_val = _parse_coord(request.form.get("lng"))
    if lat_val is not None: imovel.lat = lat_val
    if lng_val is not None: imovel.lng = lng_val

    imovel.utensilios = _build_utensilios_json(request)
    imovel.regras     = _build_regras_json(request)

    # Acesso
    imovel.wifi_rede         = request.form.get("wifi_rede",       "").strip() or None
    imovel.wifi_senha        = request.form.get("wifi_senha",      "").strip() or None
    imovel.senha_fechadura   = request.form.get("senha_fechadura", "").strip() or None

    # Contato do anfitrião
    imovel.contato_telefone  = request.form.get("contato_telefone", "").strip() or None
    imovel.contato_email     = request.form.get("contato_email",    "").strip() or None

    # Operacional
    imovel.checkin_padrao      = request.form.get("checkin_padrao",  "14:00")
    imovel.checkout_padrao     = request.form.get("checkout_padrao", "11:00")
    imovel.diaria_base         = _parse_num(request.form.get("diaria_base"))
    imovel.taxa_limpeza_padrao = _parse_num(request.form.get("taxa_limpeza_padrao"))
    imovel.capacidade_max      = _parse_num(request.form.get("capacidade_max"), int)
    imovel.qtd_quartos         = _parse_num(request.form.get("qtd_quartos"), int)
    imovel.qtd_banheiros       = _parse_num(request.form.get("qtd_banheiros"), int)
    imovel.qtd_camas           = _parse_num(request.form.get("qtd_camas"), int)

    # Cancelamento
    imovel.prazo_cancelamento_gratis = _parse_num(request.form.get("prazo_cancelamento_gratis"), int)
    imovel.multa_tipo  = request.form.get("multa_tipo")
    imovel.multa_valor = _parse_num(request.form.get("multa_valor"))

    # Custos fixos mensais (manutenção/contas) agora são configurados em
    # Finanças (ver main.py: salvar_custos_fixos_imovel), não neste form.
    # Checklist de hospedagem também saiu daqui — agora é editado no Hub do
    # Anfitrião (ver app/routes/hub.py: salvar_checklist_modelo).

    # Formulário de Documentos do Hóspede — disponível pra qualquer
    # anfitrião. "documentos_ativo" só regrava se o campo veio no form
    # (evita desativar sem querer em telas que não têm essa seção).
    if "documentos_ativo" in request.form:
        imovel.documentos_ativo = request.form.get("documentos_ativo") == "1"
    if "documentos_dias_antes" in request.form:
        imovel.documentos_dias_antes = _parse_num(request.form.get("documentos_dias_antes"), int)
    if "documentos_campos_json" in request.form or "documento_nome[]" in request.form:
        imovel.documentos_campos = _build_documentos_campos_json(request) or None

    # E-mails automáticos ao hóspede
    imovel.email_guia_ativo            = request.form.get("email_guia_ativo") == "1"
    imovel.email_guia_dias_antes       = _parse_num(request.form.get("email_guia_dias_antes"), int)
    imovel.email_avaliacao_ativo       = request.form.get("email_avaliacao_ativo") == "1"
    imovel.email_avaliacao_dias_depois = _parse_num(request.form.get("email_avaliacao_dias_depois"), int)

    nova_foto = request.files.get("foto_principal")
    if nova_foto and nova_foto.filename:
        if imovel.foto_principal:
            deletar_arquivo(imovel.foto_principal)
        imovel.foto_principal = salvar_arquivo(nova_foto)

    db.session.commit()
    flash(t_flash("Imóvel atualizado!"), "sucesso")
    return redirect(url_for("imoveis.imoveis"))


# ── Imóveis — excluir ─────────────────────────────────────────────────────────

@imoveis_bp.route("/excluir_imovel/<int:id>", methods=["POST"])
@login_required
def excluir_imovel(id: int):
    imovel = Imovel.query.filter_by(id=id, user_id=get_effective_owner_id()).first_or_404()
    try:
        if imovel.foto_principal:
            deletar_arquivo(imovel.foto_principal)
        db.session.delete(imovel)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


# ── Imóveis — ativar/inativar ─────────────────────────────────────────────────
# Diferente de excluir: o imóvel continua existindo com todo o histórico
# (estadias, finanças, checklists etc.) — só fica marcado como inativo (ex:
# em reforma) e some visualmente esmaecido na listagem. Não bloqueia nada
# automaticamente em outras telas (Hub, reservas...), é só um indicador visual.
@imoveis_bp.route("/imovel/<int:id>/toggle-ativo", methods=["POST"])
@login_required
def toggle_ativo_imovel(id: int):
    imovel = Imovel.query.filter_by(id=id, user_id=get_effective_owner_id()).first_or_404()
    try:
        imovel.ativo = not imovel.ativo
        db.session.commit()
        return jsonify({"success": True, "ativo": imovel.ativo})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


# ── Grupos — criar ────────────────────────────────────────────────────────────

@imoveis_bp.route("/salvar-grupo", methods=["POST"])
@login_required
def salvar_grupo():
    owner_id = get_effective_owner_id()
    nome = request.form.get("nome", "").strip()
    if not nome:
        flash(t_flash("Informe um nome."), "erro")
        return redirect(url_for("imoveis.imoveis"))

    grupo = Grupo(nome=nome, user_id=owner_id)
    db.session.add(grupo)
    db.session.flush()

    for imovel in Imovel.query.filter(
        Imovel.id.in_(request.form.getlist("imoveis")),
        Imovel.user_id == owner_id
    ).all():
        imovel.grupo_id = grupo.id

    db.session.commit()
    flash(t_flash("Grupo criado!"), "sucesso")
    return redirect(url_for("imoveis.imoveis"))


# ── Grupos — editar ───────────────────────────────────────────────────────────

@imoveis_bp.route("/editar_grupo/<int:id>", methods=["POST"])
@login_required
def editar_grupo(id):
    owner_id = get_effective_owner_id()
    grupo = Grupo.query.filter_by(id=id, user_id=owner_id).first_or_404()
    nome  = request.form.get("nome", "").strip()

    if not nome:
        flash(t_flash("O nome do grupo não pode ser vazio."), "erro")
        return redirect(url_for("imoveis.imoveis"))

    grupo.nome = nome
    for imovel in grupo.imoveis:
        imovel.grupo_id = None

    for imovel in Imovel.query.filter(
        Imovel.id.in_(request.form.getlist("imoveis")),
        Imovel.user_id == owner_id
    ).all():
        imovel.grupo_id = grupo.id

    db.session.commit()
    flash(t_flash("Grupo atualizado!"), "sucesso")
    return redirect(url_for("imoveis.imoveis"))


# ── Grupos — excluir ──────────────────────────────────────────────────────────

@imoveis_bp.route("/excluir_grupo/<int:id>", methods=["POST"])
@login_required
def excluir_grupo(id):
    grupo = Grupo.query.filter_by(id=id, user_id=get_effective_owner_id()).first_or_404()
    try:
        for imovel in grupo.imoveis:
            imovel.grupo_id = None
        db.session.delete(grupo)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


# ── Grupos — API ──────────────────────────────────────────────────────────────

@imoveis_bp.route("/api/grupo/<int:id>")
@login_required
def api_grupo(id):
    grupo = Grupo.query.filter_by(id=id, user_id=get_effective_owner_id()).first_or_404()
    return jsonify({
        "nome":    grupo.nome,
        "imoveis": [{"id": i.id, "titulo": i.titulo} for i in grupo.imoveis],
    })


# ── Helpers internos ──────────────────────────────────────────────────────────

def _build_utensilios_json(req) -> str:
    """
    Lê os arrays nome e valor do form e monta JSON.
    Se o frontend enviar 'utensilios_json' (string já serializada), usa diretamente.
    Fallback: lê utensilios[] (lista de nomes) e utensilio_valor[] (lista de valores).
    """
    raw = req.form.get("utensilios_json", "").strip()
    if raw:
        return raw

    nomes   = req.form.getlist("utensilios[]")
    valores = req.form.getlist("utensilio_valor[]")
    items = []
    for i, nome in enumerate(nomes):
        nome = nome.strip()
        if nome:
            items.append({"nome": nome, "valor": valores[i].strip() if i < len(valores) else ""})
    return json.dumps(items, ensure_ascii=False) if items else ""


def _parse_documentos_campos(raw):
    """Lê o template de campos do Formulário de Documentos (RG, placa, foto do pet...) salvo como JSON."""
    if not raw or not raw.strip() or raw.strip() in ("[]", "null", ""):
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            campos = []
            for c in parsed:
                if not isinstance(c, dict) or not c.get("nome"):
                    continue
                tipo = c.get("tipo") if c.get("tipo") in ("foto", "texto") else "texto"
                campos.append({
                    "nome": c["nome"],
                    "tipo": tipo,
                    "obrigatorio": bool(c.get("obrigatorio")),
                })
            return campos
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _build_documentos_campos_json(req) -> str:
    """
    Lê os arrays de nome/tipo/obrigatório dos campos do Formulário de
    Documentos e monta JSON — mesmo padrão de _build_utensilios_json. Se o
    frontend enviar 'documentos_campos_json' (string já serializada), usa direto.
    """
    raw = req.form.get("documentos_campos_json", "").strip()
    if raw:
        return raw

    nomes         = req.form.getlist("documento_nome[]")
    tipos         = req.form.getlist("documento_tipo[]")
    obrigatorios  = req.form.getlist("documento_obrigatorio[]")  # paralelo a nomes/tipos: "1"/"0" por linha
    items = []
    for i, nome in enumerate(nomes):
        nome = nome.strip()
        if not nome:
            continue
        tipo = tipos[i].strip() if i < len(tipos) and tipos[i].strip() in ("foto", "texto") else "texto"
        obrigatorio = obrigatorios[i].strip() == "1" if i < len(obrigatorios) else False
        items.append({"nome": nome, "tipo": tipo, "obrigatorio": obrigatorio})
    return json.dumps(items, ensure_ascii=False) if items else ""


def _build_regras_json(req) -> str:
    """
    Lê regras_lista[], regra_horario_inicio[], regra_horario_fim[], regra_multa[]
    e monta JSON. Se o frontend enviar 'regras_json', usa diretamente.
    Fallback legado: campo 'regras' (texto puro).
    """
    raw = req.form.get("regras_json", "").strip()
    if raw:
        return raw

    textos           = req.form.getlist("regras_lista[]")
    horarios_inicio  = req.form.getlist("regra_horario_inicio[]")
    horarios_fim     = req.form.getlist("regra_horario_fim[]")
    multas           = req.form.getlist("regra_multa[]")
    items = []
    for i, texto in enumerate(textos):
        texto = texto.strip()
        if texto:
            items.append({
                "texto":          texto,
                "horario_inicio": horarios_inicio[i].strip() if i < len(horarios_inicio) else "",
                "horario_fim":    horarios_fim[i].strip()    if i < len(horarios_fim)    else "",
                "multa":          multas[i].strip()          if i < len(multas)          else "",
            })
    if items:
        return json.dumps(items, ensure_ascii=False)

    # fallback legado
    legado = req.form.get("regras", "").strip()
    return legado

# ── Rota Pública do Imóvel (Acessível sem login) ──────────────────────────────

@imoveis_bp.route("/g/<string:slug>")
def pagina_publica_imovel(slug):
    """
    Rota pública para hóspedes acessarem via QR Code ou Link.
    Repare que ela NÃO tem o decorador @login_required.
    """
    # Busca o imóvel usando o slug que veio na URL
    imovel = Imovel.query.filter_by(slug_publico=slug).first_or_404()

    # Aqui você renderiza o HTML que o hóspede vai ver (regras, wifi, etc.)
    # Exemplo: criando um template chamado 'publico_imovel.html'
    google_maps_api_key = current_app.config.get("GOOGLE_MAPS_API_KEY", "")
    return render_template(
        "guia_hospede.html", imovel=imovel, google_maps_api_key=google_maps_api_key
    )


# ── Rota Pública de Avaliação do Hóspede (Acessível sem login) ────────────────

@imoveis_bp.route("/avaliar/<string:token>")
def pagina_avaliacao_hospede(token):
    """
    Página pública que o hóspede acessa pelo link enviado por e-mail depois
    da estadia, para deixar nota + comentário. Sem @login_required — é o
    hóspede, não o anfitrião, quem acessa.
    """
    estadia = Estadia.query.filter_by(token_avaliacao=token).first_or_404()
    imovel  = Imovel.query.get(estadia.imovel_id)

    return render_template(
        "avaliacao_hospede.html",
        estadia=estadia,
        imovel=imovel,
        avaliacao=estadia.avaliacao,  # já preenchida = mostra tela de "obrigado"
        token=token,
    )


@imoveis_bp.route("/avaliar/<string:token>", methods=["POST"])
def enviar_avaliacao_hospede(token):
    estadia = Estadia.query.filter_by(token_avaliacao=token).first_or_404()
    imovel  = Imovel.query.get(estadia.imovel_id)

    # Idempotência: se já existe avaliação para essa estadia, não deixa duplicar
    if estadia.avaliacao:
        return redirect(url_for("imoveis.pagina_avaliacao_hospede", token=token))

    nota = _parse_num(request.form.get("nota"), int)
    if not nota or nota < 1 or nota > 5:
        return redirect(url_for("imoveis.pagina_avaliacao_hospede", token=token, erro=1))

    nova = Avaliacao(
        estadia_id   = estadia.id,
        imovel_id    = estadia.imovel_id,
        user_id      = estadia.user_id,
        nome_hospede = estadia.nome_hospede,
        nota         = nota,
        comentario   = request.form.get("comentario", "").strip() or None,
    )
    db.session.add(nova)
    db.session.commit()

    # Notifica o anfitrião por e-mail (falha no envio não deve quebrar o fluxo
    # do hóspede — a avaliação já está salva de qualquer forma)
    try:
        host = db.session.get(User, estadia.user_id)
        if host and host.notify_email and host.email and imovel:
            enviar_email_nova_avaliacao(
                destinatario_host = host.email,
                nome_hospede      = estadia.nome_hospede,
                imovel_titulo     = imovel.titulo,
                nota              = nota,
                comentario        = nova.comentario,
            )
        if host and imovel:
            estrelas = "⭐" * max(1, min(5, nota))
            enviar_push_notificacao(
                host,
                titulo="Nova avaliação recebida",
                corpo=f"{estrelas} {estadia.nome_hospede or 'Um hóspede'} avaliou {imovel.titulo}",
                url="/financas",
                tag="nomdo-nova-avaliacao",
            )
    except Exception:
        pass

    return redirect(url_for("imoveis.pagina_avaliacao_hospede", token=token))