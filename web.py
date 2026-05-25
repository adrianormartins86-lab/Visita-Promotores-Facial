import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
import pytz
import os
import requests
import base64
import re
import time
import face_recognition  # <-- NOVA DEPENDÊNCIA
import numpy as np       # <-- NOVA DEPENDÊNCIA
from PIL import Image    # <-- NOVA DEPENDÊNCIA

# --- CONFIGURAÇÃO E LOGO (Ajustado para o novo repositório) ---
USER_GITHUB = "adrianormartins86-lab"
REPO_GITHUB = "Visita-Promotores-Facial"  # <-- ATUALIZADO
NOME_IMAGEM = "passaro_logo.png"
URL_ICONE = f"https://raw.githubusercontent.com/{USER_GITHUB}/{REPO_GITHUB}/main/{NOME_IMAGEM}"

st.set_page_config(
    page_title="Registro Promotores Facial", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# --- FUNÇÃO COM CACHE PARA EVITAR TRAVAMENTO NO DEPLOY ---
@st.cache_resource
def carregar_modelos_faciais():
    """Força o Streamlit a isolar o carregamento pesado da IA"""
    # Apenas um truque para garantir que a biblioteca inicializou sem travar o escopo global
    teste_inicializacao = face_recognition.__file__
    return True

# Inicializa o recurso de IA com segurança
modelos_prontos = carregar_modelos_faciais()

# --- SISTEMA DE LOGIN (Idêntico ao original) ---
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if st.session_state["authenticated"]:
        return True

    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("Acesso Restrito")
        st.write("Laboratório de Reconhecimento Facial")
        email = st.text_input("E-mail", placeholder="seu_email@molicenter.com.br").lower().strip()
        senha = st.text_input("Senha", type="password")
        if st.button("Entrar", use_container_width=True):
            emails_gerentes = [f"gerente{i}@molicenter.com.br" for i in range(1, 15)]
            email_analista = "analista@molicenter.com.br"
            if (email in emails_gerentes or email == email_analista) and senha == "moli1234":
                st.session_state["authenticated"] = True
                st.session_state["usuario_logado"] = email
                if email == email_analista:
                    st.session_state["perfil"] = "analista"
                else:
                    st.session_state["perfil"] = "gerente"
                    st.session_state["loja_id"] = re.search(r'\d+', email).group()
                st.session_state["form_count"] = 0
                st.rerun()
            else:
                st.error("❌ E-mail ou senha incorretos.")
    return False

if check_password():
    # --- BARRA LATERAL OCULTA (EXPANDER) ---
    with st.sidebar:
        with st.expander("⚙️ Opções de Conta"):
            st.write(f"👤 **Usuário:** {st.session_state['usuario_logado']}")
            st.write(f"📊 **Perfil:** {st.session_state['perfil'].capitalize()}")
            if st.button("Sair / Logout", use_container_width=True):
                st.session_state.clear()
                st.rerun()

    def upload_para_imgbb(bytes_foto):
        try:
            api_key = st.secrets["imgbb"]["api_key"]
            url = "https://api.imgbb.com/1/upload"
            foto_base64 = base64.b64encode(bytes_foto).decode('utf-8')
            payload = {"key": api_key, "image": foto_base64}
            response = requests.post(url, payload)
            res = response.json()
            return res['data']['url'] if res['success'] else "Erro no Upload"
        except: return "Erro no Upload"

    st.title("Visita Promotores Facial - Teste")
    st.markdown("---")

    conn = st.connection("gsheets", type=GSheetsConnection)

    # Carrega fornecedores do arquivo local .xlsx no repositório
    @st.cache_data
    def carregar_fornecedores():
        arquivo = 'fornecedores.xlsx'
        if os.path.exists(arquivo):
            try:
                df = pd.read_excel(arquivo, engine='openpyxl').dropna(how='all')
                df.columns = [str(col).strip() for col in df.columns]
                return df
            except Exception as e:
                st.error(f"Erro ao ler Excel: {e}")
        return None

    df_forn = carregar_fornecedores()

    if df_forn is not None:
        col_fornecedor = df_forn.columns[1]  
        col_promotor = df_forn.columns[4]     
        col_frequencia = df_forn.columns[6]   
        col_loja = df_forn.columns[-1]        
        
        fuso_br = pytz.timezone('America/Sao_Paulo')
        agora = datetime.now(fuso_br)
        dias_map = {0: 'SEG', 1: 'TER', 2: 'QUA', 3: 'QUI', 4: 'SEX', 5: 'SAB', 6: 'DOM'}
        dia_hoje = dias_map[agora.weekday()]

        st.subheader(f"📅 Hoje é {agora.strftime('%d/%m')} ({dia_hoje})")

        lista_lojas = sorted(df_forn[col_loja].dropna().astype(str).unique().tolist())
        if st.session_state["perfil"] == "analista":
            loja_sel = st.selectbox("Selecione a Loja:", ["Escolha..."] + lista_lojas)
        else:
            id_g = st.session_state["loja_id"]
            loja_sel = next((l for l in lista_lojas if l.startswith(id_g) or l.startswith(id_g.zfill(2))), "Escolha...")
            st.info(f"📍 **Loja: {loja_sel}**")

        if loja_sel != "Escolha...":
            df_loja = df_forn[df_forn[col_loja].astype(str) == loja_sel]
            df_hoje = df_loja[df_loja[col_frequencia].astype(str).str.contains(dia_hoje, case=False, na=False)]

            st.markdown("### 📋 Agenda de Visitas (Hoje)")
            if not df_hoje.empty:
                colunas_exibir = [col_fornecedor, col_promotor, col_frequencia]
                tabela_exibicao = df_hoje[colunas_exibir].copy().sort_values(by=col_fornecedor)
                st.dataframe(tabela_exibicao, use_container_width=True, hide_index=True)
            else:
                st.warning("Nenhum fornecedor programado para hoje.")

            st.markdown("---")

            if "form_count" not in st.session_state:
                st.session_state["form_count"] = 0
            
            # --- SEÇÃO DE REGISTRO FACIAL ---
            with st.container():
                st.markdown("### 📸 2. Realizar Registro por Reconhecimento Facial")
                
                opcoes_forn = ["Escolha..."] + sorted(df_loja[col_fornecedor].unique().tolist())
                
                forn_sel = st.selectbox(
                    "Selecione o fornecedor:", 
                    opcoes_forn, 
                    key=f"forn_{st.session_state['form_count']}"
                )

                if forn_sel != "Escolha...":
                    dados_linha = df_loja[df_loja[col_fornecedor] == forn_sel].iloc[0]
                    nome_promotor_cadastrado = dados_linha[col_promotor]
                    
                    st.info(f"👤 Promotor esperado: **{nome_promotor_cadastrado}**")
                    
                    obs = st.text_input("3. Observação (Opcional):", key=f"obs_{st.session_state['form_count']}")
                    
                    foto_capturada = st.camera_input("Olhe para a câmera", key=f"cam_{st.session_state['form_count']}")

                    if foto_capturada:
                        caminho_base_rostos = f"fotos_cadastro/{forn_sel}.jpg"
                        
                        if not os.path.exists(caminho_base_rostos):
                            st.error(f"❌ Não há foto de cadastro para o fornecedor '{forn_sel}' em 'fotos_cadastro/'.")
                        else:
                            with st.spinner('Analisando biometria e gravando...'):
                                try:
                                    # 1. Carrega foto gabarito com segurança apenas quando a foto é tirada
                                    img_gabarito = face_recognition.load_image_file(caminho_base_rostos)
                                    encodings_gabarito = face_recognition.face_encodings(img_gabarito)
                                    
                                    if len(encodings_gabarito) == 0:
                                        st.error(f"❌ Erro na foto de cadastro original de '{forn_sel}'. Não foi detectado rosto nela.")
                                    else:
                                        encoding_gabarito = encodings_gabarito[0]
                                        
                                        # 2. Converte foto capturada
                                        img_atual_pil = Image.open(foto_capturada)
                                        img_atual_np = np.array(img_atual_pil)
                                        encodings_atuais = face_recognition.face_encodings(img_atual_np)
                                        
                                        if len(encodings_atuais) == 0:
                                            st.error("Nenhum rosto identificado na câmera. Ajuste o enquadramento.")
                                        else:
                                            encoding_atual = encodings_atuais[0]
                                            
                                            # 3. Compara rostos
                                            match = face_recognition.compare_faces([encoding_gabarito], encoding_atual, tolerance=0.55)
                                            
                                            if match[0]:
                                                bytes_da_foto = foto_capturada.getvalue()
                                                link_f = upload_para_imgbb(bytes_da_foto)
                                                
                                                if link_f != "Erro no Upload":
                                                    try:
                                                        df_atual = conn.read(ttl=0)
                                                    except:
                                                        df_atual = pd.DataFrame()

                                                    novo_registro = pd.DataFrame([{
                                                        "Data": agora.strftime("%d/%m/%Y %H:%M:%S"),
                                                        "Loja": loja_sel, 
                                                        "Fornecedor": forn_sel,
                                                        "Observacao": f"[FACIAL_OK] {obs}".strip(),
                                                        "Arquivo_Foto": link_f, 
                                                        "Usuario": st.session_state["usuario_logado"]
                                                    }])
                                                    
                                                    df_final = pd.concat([df_atual, novo_registro], ignore_index=True)
                                                    conn.update(data=df_final)
                                                    
                                                    st.success(f"✅ Facial Aprovado! Visita salva.")
                                                    st.balloons()
                                                    
                                                    st.session_state["form_count"] += 1
                                                    time.sleep(2)
                                                    st.rerun()
                                                else:
                                                    st.error("❌ Falha no upload para o ImgBB.")
                                            else:
                                                st.error("❌ Acesso Negado! Rosto não confere.")
                                except Exception as e:
                                    st.error(f"Erro no processamento facial: {e}")
    else:
        st.error("Erro: Arquivo 'fornecedores.xlsx' não encontrado no repositório.")
