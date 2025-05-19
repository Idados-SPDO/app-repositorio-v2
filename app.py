import streamlit as st
import yaml
import json
from streamlit_authenticator.utilities.hasher import Hasher
import streamlit_authenticator as stauth
from snowflake.snowpark import Session

# --- Configurações da página ---
st.set_page_config(
    page_title="SPDO Repositório de Aplicações",
    page_icon="image.png",
    layout="wide",
)

# --- Funções reutilizáveis ---
@st.cache_data(show_spinner=False)
def load_credentials(path: str = "config.yaml"):
    with open(path, encoding="utf-8") as file:
        cfg = yaml.load(file, Loader=yaml.SafeLoader)
    cfg["credentials"] = Hasher.hash_passwords(cfg["credentials"])
    return cfg

def load_areas_from_sf():
    session = Session.builder.configs(st.secrets["snowflake"]).create()
    df = session.table("TB_REPO_APPS_AREAS") \
                .select("NAME", "LINKS") \
                .order_by("NAME") \
                .collect()
    areas = []
    for row in df:
        raw = row["LINKS"]
        links = []
        if isinstance(raw, str):
            try:
                links = json.loads(raw)
            except json.JSONDecodeError:
                pass
        elif raw:
            links = raw
        areas.append({"name": row["NAME"], "links": links})
    return areas

# --- Carregando dados e autenticando ---
config = load_credentials()
areas = load_areas_from_sf()

authenticator = stauth.Authenticate(
    credentials=config["credentials"],
    cookie_expiry_days=1,
)
with st.sidebar:
    st.logo("logo.png")
    st.write("---")
    authenticator.login(location="sidebar", key="login_form")
    auth_status = st.session_state.get("authentication_status")
    if auth_status:
        st.success(f"👋 Olá, **{st.session_state.get('name')}**")
        authenticator.logout(location="sidebar")
    elif auth_status is False:
        st.error("❌ Usuário ou senha incorretos")
    else:
        st.info("ℹ️ Informe usuário e senha")

if not st.session_state.get("authentication_status"):
    # Tela de apresentação para não-logados
    st.markdown(
        "<div style='text-align:center; margin-top:50px;'>"
        "<h1 style='font-size:48px;'>SPDO</h1>"
        "<h2 style='font-weight:normal;'>Repositório de Aplicações</h2>"
        "<p style='max-width:600px; margin:auto; line-height:1.5;'>"
        "O Repositório de Aplicações da SPDO é uma plataforma centralizada que armazena e organiza diversas soluções tecnológicas. Sua principal função é facilitar o acesso e o compartilhamento de recursos entre setores e equipes, promovendo maior colaboração e elevando a eficiência operacional em toda a organização."
        "</p>"
        "</div>",
        unsafe_allow_html=True
    )
    st.stop()

# --- Define permissões do usuário ---
username = st.session_state.get("username", "").lower()
raw_permissions = {
    "spdo": "all",
    "test_user": ["Cadastramento e Governança BP", "Coleta Tradicional"],
}
user_permissions = {k.lower(): v for k, v in raw_permissions.items()}
permitted = user_permissions.get(username, [])

# --- Cria abas dinamicamente ---
if permitted == "all":
    tab_names = ["Aplicações", "Gerenciamento"]
else:
    tab_names = ["Aplicações"]

tabs = st.tabs(tab_names)
tab_view = tabs[0]
tab_manage = tabs[1] if len(tabs) > 1 else None

# --- Aba 1: Visualização ---
with tab_view:
    st.header("📂 Repositório de Aplicações SPDO")
    if permitted == "all":
        areas_to_show = areas
    else:
        areas_to_show = [a for a in areas if a["name"] in permitted]

    if not areas_to_show:
        st.warning("Você não possui acesso a nenhuma área.")
    else:
        cols = st.columns(2, gap="large")
        for idx, area in enumerate(areas_to_show):
            with cols[idx % 2].expander(area["name"]):
                if not area["links"]:
                    st.write("Nenhum aplicativo disponível nesta área.")
                for link in area["links"]:
                    st.markdown(f"**{link['name']}**", unsafe_allow_html=True)
                    for sub in link.get("sublinks", []):
                        st.markdown(
                            f"[▶️ Acessar APP]({sub['url']})  |  "
                            f"[📘 Tutorial]({sub['tutorial_url']})",
                            unsafe_allow_html=True
                        )
                        st.divider()

if tab_manage:
    with tab_manage:
        st.header("⚙️ Gerenciar Áreas e Projetos")
        session = Session.builder.configs(st.secrets["snowflake"]).create()

        subtab_areas, subtab_projects = st.tabs(["Áreas", "Projetos"])
        # --- 1) Adicionar Nova Área ---

        with subtab_areas:
            st.subheader("Gerenciar Áreas")
            area_cols = st.columns(3)


            with area_cols[0].expander("➕ Adicionar Nova Área"):
                new_area = st.text_input("Nome da Área", key="add_area_name")
                new_links_json = st.text_area(
                    "Links (JSON)",
                    placeholder='[{"name":"Meu APP","sublinks":[{"url":"…","tutorial_url":"…"}]}]',
                    key="add_area_links",
                    help='Formato: [{"name":"Meu APP","sublinks":[{"url":"…","tutorial_url":"…"}]}]'
                )

                if st.button("Adicionar Área", key="btn_add_area"):
                    # 1) parse seguro
                    try:
                        parsed_links = json.loads(new_links_json)
                    except json.JSONDecodeError as e:
                        st.error(f"JSON inválido: {e.msg} (linha {e.lineno}, coluna {e.colno})")
                        st.stop()

                    if not isinstance(parsed_links, list):
                        st.error("O JSON deve ser uma **lista** de objetos.")
                        st.stop()

                    # 2) preparar string JSON escapada
                    json_str = json.dumps(parsed_links).replace("'", "\\'")

                    # 3) inserir usando SELECT em vez de VALUES
                    try:
                        session.sql(f"""
                            INSERT INTO TB_REPO_APPS_AREAS (NAME, LINKS)
                            SELECT '{new_area}', PARSE_JSON('{json_str}')
                        """).collect()
                        st.success("Área adicionada com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao adicionar área: {e}")

            with area_cols[1].expander("✏️ Atualizar Área"):
                area_names = [a["name"] for a in areas]
                sel = st.selectbox("Selecione a Área", area_names, key="upd_area")
                new_area_name = st.text_input("Novo Nome da Área", value=sel, key="upd_area_name")
                new_links_json = st.text_area(
                    "Novos Links (JSON)",
                    placeholder='[{"name":"Meu APP","sublinks":[{"url":"…","tutorial_url":"…"}]}]',
                    key="upd_area_links",
                    help='[{"name":"Meu APP","sublinks":[{"url":"…","tutorial_url":"…"}]}]'
                )
                if st.button("Atualizar Área", key="btn_upd_area"):
                    try:
                        parsed_links = json.loads(new_links_json)
                        json_str = json.dumps(parsed_links).replace("'", "\\'")
                        session.sql(f"""
                            UPDATE TB_REPO_APPS_AREAS
                            SET NAME = '{new_area_name}', LINKS = PARSE_JSON('{json_str}')
                            WHERE NAME = '{sel}'
                        """).collect()
                        st.success("Área atualizada com sucesso!")
                        st.rerun()
                    except json.JSONDecodeError as e:
                        st.error(f"JSON inválido: {e.msg} (linha {e.lineno}, coluna {e.colno})")
                    except Exception as e:
                        st.error(f"Erro ao atualizar área: {e}")
                
            with area_cols[2].expander("🗑 Deletar Área"):
                names = [a["name"] for a in areas]
                sel = st.selectbox("Selecione a Área", names, key="del_area")
                if st.button("Deletar Área", key="btn_del_area"):
                    try:
                        session.sql(f"DELETE FROM TB_REPO_APPS_AREAS WHERE NAME = '{sel}'").collect()
                        st.success("Área deletada com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao deletar área: {e}")
        with subtab_projects:
            st.subheader("Gerenciar Projetos")
            area_cols = st.columns(3)
        # --- 2) Adicionar Novo Projeto em Uma Área ---
            with area_cols[0].expander("➕ Adicionar Novo Projeto"):
                area_names = [a["name"] for a in areas]
                sel_area = st.selectbox("Selecione a Área", area_names, key="add_proj_area")
                proj_name = st.text_input("Nome do Projeto", key="add_proj_name")
                sublinks_json = st.text_area(
                    "Sublinks (JSON)",
                    placeholder='[{"url":"…","tutorial_url":"…"}]',
                    key="add_proj_sublinks",
                    help='Formato: [{"url":"…","tutorial_url":"…"}]'
                )
                if st.button("Adicionar Projeto", key="btn_add_proj"):
                    try:
                        new_sublinks = json.loads(sublinks_json)
                        # constrói a nova lista de links
                        area_obj = next(a for a in areas if a["name"] == sel_area)
                        updated_links = area_obj["links"] + [{"name": proj_name, "sublinks": new_sublinks}]
                        session.sql(f"""
                            UPDATE TB_REPO_APPS_AREAS
                            SET LINKS = PARSE_JSON('{json.dumps(updated_links)}')
                            WHERE NAME = '{sel_area}'
                        """).collect()
                        st.success("Projeto adicionado com sucesso!")
                        st.rerun()
                    except json.JSONDecodeError:
                        st.error("JSON inválido nos sublinks.")
                    except Exception as e:
                        st.error(f"Erro ao adicionar projeto: {e}")

            # --- 3) Atualizar Projeto ---
            with area_cols[1].expander("✏️ Atualizar Projeto"):
                # 1) Escolher área
                area_names = [a["name"] for a in areas]
                sel_area = st.selectbox("Selecione a Área", area_names, key="upd_proj_area")

                # traz os links atuais dessa área
                area_obj = next(a for a in areas if a["name"] == sel_area)
                area_links = area_obj.get("links", [])

                if not area_links:
                    st.info("Essa área não possui projetos cadastrados.")
                else:
                    # 2) Escolher projeto dentro da área
                    proj_names = [l["name"] for l in area_links]
                    sel_proj = st.selectbox("Selecione o Projeto", proj_names, key="upd_proj_select")

                    # 3) Busca o objeto do projeto de forma segura
                    proj_obj = next((l for l in area_links if l["name"] == sel_proj), None)
                    if proj_obj is None:
                        st.error("❌ Projeto não encontrado na lista.")
                    else:
                        # 4) Campos para editar nome e sublinks
                        new_proj_name = st.text_input("Novo Nome do Projeto", value=proj_obj["name"], key="upd_proj_name")
                        new_sublinks_json = st.text_area(
                            "Novos Sublinks (JSON)",
                            value=json.dumps(proj_obj.get("sublinks", []), indent=2),
                            key="upd_proj_sublinks"
                        )

                        # 5) Botão de atualização
                        if st.button("Atualizar Projeto", key="btn_upd_proj"):
                            try:
                                updated_sublinks = json.loads(new_sublinks_json)
                                updated_links = [
                                    {"name": new_proj_name, "sublinks": updated_sublinks}
                                    if l["name"] == sel_proj else l
                                    for l in area_links
                                ]
                                session.sql(f"""
                                    UPDATE TB_REPO_APPS_AREAS
                                    SET LINKS = PARSE_JSON('{json.dumps(updated_links)}')
                                    WHERE NAME = '{sel_area}'
                                """).collect()
                                st.rerun()
                                st.success("✅ Projeto atualizado com sucesso!")
                            except json.JSONDecodeError:
                                st.error("🚫 JSON inválido nos sublinks. Verifique a formatação.")
                            except Exception as e:
                                st.error(f"🚫 Erro ao atualizar projeto: {e}")

            # --- 4) Deletar Projeto ---
            with area_cols[2].expander("🗑️ Deletar Projeto"):
                area_names = [a["name"] for a in areas]
                sel_area = st.selectbox("Selecione a Área", area_names, key="del_proj_area")
                area_obj = next(a for a in areas if a["name"] == sel_area)
                proj_names = [l["name"] for l in area_obj["links"]]
                sel_proj = st.selectbox("Selecione o Projeto para Remover", proj_names, key="del_proj_select")
                if st.button("Deletar Projeto", key="btn_del_proj"):
                    try:
                        updated_links = [l for l in area_obj["links"] if l["name"] != sel_proj]
                        session.sql(f"""
                            UPDATE TB_REPO_APPS_AREAS
                            SET LINKS = PARSE_JSON('{json.dumps(updated_links)}')
                            WHERE NAME = '{sel_area}'
                        """).collect()
                        st.rerun()
                        st.success("Projeto deletado com sucesso!")
                    except Exception as e:
                        st.error(f"Erro ao deletar projeto: {e}")

        