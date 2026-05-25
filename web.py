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
from deepface import DeepFace  # Engine de biometria
import numpy as np
from PIL import Image

# --- CONFIGURAÇÃO E LOGO ---
USER_GITHUB = "adrianormartins86-lab"
REPO_GITHUB = "Visita-Promotores-Facial"
NOME_IMAGEM = "passaro_logo.png"
URL_ICONE = f"https://raw.githubusercontent.com/{USER_GITHUB}/{REPO_GITHUB}/main/{NOME_IMAGEM}"

st.set_page_config(
    page_title="Registro Promotores Facial", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# --- SISTEMA DE LOGIN ---
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

    st.title("Visita Promotores Facial - Teste Automatizado")
    st.markdown("---")

    conn = st.connection("gsheets", type=GSheetsConnection)

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
            
            # --- NOVA SEÇÃO DE REGISTRO FACIAL AUTOMÁTICO ---
            with st.container():
                st.markdown("### 📸 2. Realizar Registro por Reconhecimento Facial Automatizado")
                st.write("Apenas olhe para a câmera. O sistema identificará seu rosto e sua empresa automaticamente.")
                
                obs = st.text_input("Observação (Opcional):", key=f"obs_{st.session_state['form_count']}")
                
                # Câmera disponível logo de cara, sem selects intermediários
                foto_capturada = st.camera_input("Olhe para a câmera", key=f"cam_{st.session_state['form_count']}")

                if foto_capturada:
                    pasta_cadastro = "fotos_cadastro"
                    
                    if not os.path.exists(pasta_cadastro) or len(os.listdir(pasta_cadastro)) == 0:
                        st.error("❌ Erro de Infraestrutura: A pasta 'fotos_cadastro' está vazia ou não existe no repositório.")
                    else:
                        with st.spinner('Buscando correspondência biométrica no banco...'):
                            try:
                                # Salva temporariamente a foto tirada
                                caminho_temp_captura = "temp_identifica.jpg"
                                with open(caminho_temp_captura, "wb") as f:
                                    f.write(foto_capturada.getbuffer())
                                
                                # Varre a pasta inteira procurando quem é o dono desse rosto
                                lista_resultados = DeepFace.find(
                                    img_path = caminho_temp_captura,
                                    db_path = pasta_cadastro,
                                    enforce_detection = True,
                                    detector_backend = 'opencv',
                                    silent = True
                                )
                                
                                if os.path.exists(caminho_temp_captura):
                                    os.remove(caminho_temp_captura)

                                # Verifica se encontrou algum match na lista retornada
                                if len(lista_resultados) > 0 and not lista_resultados[0].empty:
                                    # Pega o melhor match (primeira linha do dataframe retornado)
                                    melhor_match = lista_resultados[0].iloc[0]
                                    caminho_foto_encontrada = melhor_match['identity']
                                    
                                    # Extrai o nome do arquivo (ex: "fotos_cadastro/Nestle.jpg" -> "Nestle")
                                    nome_arquivo = os.path.basename(caminho_foto_encontrada)
                                    forn_detectado = os.path.splitext(nome_arquivo)[0]
                                    
                                    # Verifica se o fornecedor encontrado está escalado para esta loja
                                    df_validacao_forn = df_loja[df_loja[col_fornecedor].astype(str) == forn_detectado]
                                    
                                    if not df_validacao_forn.empty:
                                        dados_linha = df_validacao_forn.iloc[0]
                                        nome_promotor_cadastrado = dados_linha[col_promotor]
                                        
                                        st.success(f"🎉 Promotor Identificado: **{nome_promotor_cadastrado}** ({forn_detectado})")
                                        
                                        # Faz o upload e salva na planilha
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
                                                "Fornecedor": forn_detectado,
                                                "Observacao": f"[FACIAL_AUTOMATICO_OK] {obs}".strip(),
                                                "Arquivo_Foto": link_f, 
                                                "Usuario": st.session_state["usuario_logado"]
                                            }])
                                            
                                            df_final = pd.concat([df_atual, novo_registro], ignore_index=True)
                                            conn.update(data=df_final)
                                            
                                            st.balloons()
                                            st.session_state["form_count"] += 1
                                            time.sleep(3)
                                            st.rerun()
                                        else:
                                            st.error("❌ Falha no upload da foto para o ImgBB.")
                                    else:
                                        st.error(f"❌ Promotor de '{forn_detectado}' identificado, mas essa empresa não está escalada para a Loja {loja_sel} hoje.")
                                else:
                                    st.error("❌ Rosto não reconhecido em nossa base de promotores cadastrados.")
                                        
                            except Exception as e:
                                if "Face could not be detected" in str(e):
                                    st.error("❌ Nenhum rosto identificado na câmera. Centralize-se melhor na tela.")
                                else:
                                    st.error(f"Erro no processamento automático: {e}")
    else:
        st.error("Erro: Arquivo 'fornecedores.xlsx' não encontrado no repositório.")
