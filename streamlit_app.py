import streamlit as st
import pandas as pd
import datetime
import random
import openai
import os
from st_aggrid import AgGrid, GridOptionsBuilder

#########################################
# FUNZIONI DI CARICAMENTO E PRE-ELABORAZIONE
#########################################

def load_datasets(file):
    """
    Carica il file Excel "contenuti.xlsx" che deve contenere i fogli:
      - "keyword"
      - "categorie"
      - "prodotti"
      - "copy"
    """
    try:
        df_kw = pd.read_excel(file, sheet_name="keyword")
        df_cat = pd.read_excel(file, sheet_name="categorie")
        df_prod = pd.read_excel(file, sheet_name="prodotti")
        df_copy = pd.read_excel(file, sheet_name="copy")
    except Exception as e:
        st.error(f"Errore nel caricamento dei fogli: {e}")
        return None, None, None, None

    # Pre-elabora tutti i DataFrame
    df_kw = preprocess_data(df_kw)
    df_cat = preprocess_data(df_cat)
    df_prod = preprocess_data(df_prod)
    df_copy = preprocess_data(df_copy)
    
    return df_kw, df_cat, df_prod, df_copy

def preprocess_data(df):
    """
    Rimuove spazi dai nomi delle colonne ed elimina le righe che contengono la stringa "total" (case-insensitive).
    """
    df.columns = [col.strip() for col in df.columns]
    df = df[~df.apply(lambda x: x.astype(str).str.contains("total", case=False).any(), axis=1)]
    return df

#########################################
# FUNZIONI DI SUPPORTO PER ANALISI E CALCOLI
#########################################

def get_categories_for_month(df_cat, mese):
    """
    Dal foglio "categorie", estrae l'elenco dei valori nella colonna "Label 2° liv" (o "categoria")
    per il mese selezionato. Si assume che df_cat contenga la colonna "Mese" e una colonna per le categorie.
    """
    if "Mese" not in df_cat.columns:
        st.warning("Colonna 'Mese' non trovata in df_cat.")
        return []
    
    row = df_cat[df_cat["Mese"].str.lower() == mese.lower()]
    if row.empty:
        return []
    
    # Usa "Label 2° liv" se esiste, altrimenti "categoria"
    cat_col = "Label 2° liv" if "Label 2° liv" in df_cat.columns else "categoria"
    cats_str = row.iloc[0][cat_col]
    cat_list = [c.strip().lower() for c in cats_str.split(",")]
    return cat_list

def get_relevant_keywords_for_month(df_kw, df_cat, mese, top_n=10, min_volume=1000):
    """
    Usa il foglio "categorie" per ottenere le macro-categorie rilevanti per il mese scelto,
    filtra il DataFrame delle keyword (df_kw) sulla colonna "Label 2° liv" oppure "categoria"
    (in base a quale esiste), ordina per il volume (se esiste una colonna con il nome del mese)
    e restituisce le prime top_n righe che hanno un volume >= min_volume.
    """
    cats_list = get_categories_for_month(df_cat, mese)
    if not cats_list:
        st.warning(f"Nessuna categoria trovata per il mese {mese} nel foglio 'categorie'.")
        return pd.DataFrame()

    # Determina quale colonna usare: "Label 2° liv" o "categoria"
    cat_col = "Label 2° liv" if "Label 2° liv" in df_kw.columns else "categoria"
    df_kw[cat_col] = df_kw[cat_col].astype(str).str.lower().str.strip()
    df_kw_filtered = df_kw[df_kw[cat_col].isin(cats_list)].copy()

    # Se esiste una colonna per il mese, ordina in base al volume e filtra per volume minimo
    if mese in df_kw_filtered.columns:
        df_kw_filtered[mese] = pd.to_numeric(df_kw_filtered[mese], errors="coerce").fillna(0)
        df_kw_filtered = df_kw_filtered[df_kw_filtered[mese] >= min_volume]
        df_kw_filtered = df_kw_filtered.sort_values(by=mese, ascending=False)
    
    return df_kw_filtered.head(top_n)

#########################################
# FUNZIONI PER IL CALENDARIO EDITORIALE
#########################################

def create_calendar_structure(mese, rubrica_dict):
    """
    Genera un DataFrame con le colonne:
      [Data, Ora, Rubrica, ARGOMENTO, COPY_IG, COPY_FB, SKU, Keyword, Categoria].
    Le date vengono generate per i giorni 1-28 del mese scelto; gli orari sono scelti casualmente
    tra le 8:00 e le 20:00 (minuti: 00,15,30,45).
    """
    month_map = {
        "Gennaio": 1, "Febbraio": 2, "Marzo": 3, "Aprile": 4, "Maggio": 5,
        "Giugno": 6, "Luglio": 7, "Agosto": 8, "Settembre": 9, "Ottobre": 10,
        "Novembre": 11, "Dicembre": 12
    }
    mnum = month_map[mese]
    base_year = 2025
    possible_days = [datetime.date(base_year, mnum, d) for d in range(1, 29)]
    
    rows = []
    idx_day = 0
    for rubrica, n_posts in rubrica_dict.items():
        for _ in range(n_posts):
            day = possible_days[idx_day % len(possible_days)]
            idx_day += 3
            ora = f"{random.randint(8,20)}:{random.choice(['00','15','30','45'])}"
            row = {
                "Data": day.strftime("%d/%m/%Y"),
                "Ora": ora,
                "Rubrica": rubrica,
                "ARGOMENTO": "",
                "COPY_IG": "",
                "COPY_FB": "",
                "SKU": "",
                "Keyword": "",
                "Categoria": ""
            }
            rows.append(row)
    df = pd.DataFrame(rows)
    df["Data_datetime"] = pd.to_datetime(df["Data"], format="%d/%m/%Y")
    df = df.sort_values(by=["Data_datetime", "Ora"]).drop(columns=["Data_datetime"])
    return df

def match_sku_by_label2(df_prod, label2):
    """
    Cerca in df_prod uno SKU avente il valore nella colonna "Label 2° liv" oppure "categoria"
    uguale a label2 (case-insensitive).
    """
    if "Label 2° liv" in df_prod.columns:
        cat_col = "Label 2° liv"
    elif "categoria" in df_prod.columns:
        cat_col = "categoria"
    else:
        return ""
    df_prod[cat_col] = df_prod[cat_col].astype(str).str.lower().str.strip()
    subset = df_prod[df_prod[cat_col] == label2.strip().lower()]
    if not subset.empty and "SKU" in subset.columns:
        return str(subset.iloc[0]["SKU"])
    return ""

def assign_initial_topics(calendar_df, df_kw, df_cat, df_prod):
    """
    Assegna automaticamente gli argomenti:
      - Per la rubrica "Prodotto": usa le keyword filtrate per il mese e crea un argomento più dettagliato,
        includendo lo SKU e un breve invito a scoprire i vantaggi del prodotto.
      - Per la rubrica "Categoria": usa le categorie del mese e cerca, se possibile, fino a 2 keyword correlate
        per arricchire l'argomento.
      - Per "Servizi", "Clienti" e "Curiosità": usa argomenti predefiniti.
    """
    df = calendar_df.copy()
    mese = st.session_state.get("mese_selezionato", "")
    
    # Rubrica Prodotto
    df_kw_sample = get_relevant_keywords_for_month(df_kw, df_cat, mese, top_n=10, min_volume=1500)
    prod_idx = df[df["Rubrica"].str.lower() == "prodotto"].index
    for i, idx in enumerate(prod_idx):
        if i < len(df_kw_sample):
            row_kw = df_kw_sample.iloc[i]
            k = row_kw.get("keyword", "")
            # Determina la colonna di categorie: se "Label 2° liv" esiste, altrimenti "categoria"
            if "Label 2° liv" in row_kw and pd.notna(row_kw["Label 2° liv"]):
                cat_col = "Label 2° liv"
            elif "categoria" in row_kw and pd.notna(row_kw.get("categoria", "")):
                cat_col = "categoria"
            else:
                cat_col = None
            label2_val = str(row_kw[cat_col]).lower().strip() if cat_col else ""
            
            sku_found = match_sku_by_label2(df_prod, label2_val)
            df.at[idx, "Keyword"] = k
            df.at[idx, "Categoria"] = label2_val
            df.at[idx, "SKU"] = sku_found
            df.at[idx, "ARGOMENTO"] = f"Focus Prodotto: {k}. Scopri i vantaggi (SKU: {sku_found})."
        else:
            df.at[idx, "ARGOMENTO"] = "Focus Prodotto generico"
    
    # Rubrica Categoria: per ciascuna categoria, integra anche le keyword più performanti correlate (fino a 2)
    cat_list = get_categories_for_month(df_cat, mese)
    cat_idx = df[df["Rubrica"].str.lower() == "categoria"].index
    for i, idx in enumerate(cat_idx):
        if i < len(cat_list):
            c = cat_list[i]
            # Se possibile, cerca in df_kw keyword correlate
            if "Label 2° liv" in st.session_state["df_kw"].columns:
                cat_keywords = st.session_state["df_kw"][st.session_state["df_kw"]["Label 2° liv"].str.lower() == c]
            elif "categoria" in st.session_state["df_kw"].columns:
                cat_keywords = st.session_state["df_kw"][st.session_state["df_kw"]["categoria"].str.lower() == c]
            else:
                cat_keywords = pd.DataFrame()
            if not cat_keywords.empty and mese in cat_keywords.columns:
                cat_keywords[mese] = pd.to_numeric(cat_keywords[mese], errors="coerce").fillna(0)
                cat_keywords = cat_keywords.sort_values(by=mese, ascending=False)
                top_keywords = cat_keywords["keyword"].head(2).tolist()
            else:
                top_keywords = []
            kw_str = ", ".join(top_keywords) if top_keywords else ""
            df.at[idx, "Categoria"] = c
            df.at[idx, "ARGOMENTO"] = f"Trend Categoria: {c}." + (f" Keyword principali: {kw_str}." if kw_str else "")
        else:
            df.at[idx, "ARGOMENTO"] = "Trend Categoria generico"
    
    # Rubrica Servizi
    serv_idx = df[df["Rubrica"].str.lower() == "servizi"].index
    for idx in serv_idx:
        df.at[idx, "ARGOMENTO"] = "Scopri un servizio di Agristore"
    
    # Rubrica Clienti
    cli_idx = df[df["Rubrica"].str.lower() == "clienti"].index
    for idx in cli_idx:
        df.at[idx, "ARGOMENTO"] = "Testimonianza cliente soddisfatto"
    
    # Rubrica Curiosità
    cur_idx = df[df["Rubrica"].str.lower() == "curiosità"].index
    for idx in cur_idx:
        df.at[idx, "ARGOMENTO"] = "Curiosità o info stagionale"
    
    return df

#########################################
# MODULI GPT
#########################################

def generate_argument_prompt(rubrica, keyword, categoria, volume, mese, target="appassionati di giardinaggio"):
    """
    Costruisce un prompt arricchito per generare o affinare l'argomento,
    includendo informazioni quali rubrica, keyword, categoria, volume e mese.
    """
    prompt = f"""
Sei un esperto di marketing per agricoltura e giardinaggio.
Stai pianificando un post per la rubrica "{rubrica}".
La keyword principale è: "{keyword}".
La categoria è: "{categoria}".
Nel mese di {mese}, questa keyword registra circa {volume} ricerche mensili.
Il target del contenuto è formato da {target}.
L'obiettivo è creare un argomento (titolo + breve descrizione) chiaro e specifico per il periodo.
Fornisci un'idea di post incisiva, evidenziando perché questa keyword e categoria sono rilevanti in {mese}.
Usa un tono amichevole ma autorevole.
Argomenta perché sono state scelte queste keyword e categorie.
Dai un'idea ipotetica su una parte grafica per permettere all'utente di andare poi a creare l'imamgine di accompagnamento del post.
    """
    return prompt

def refine_arguments_with_gpt(calendar_df):
    """
    Per ogni riga del calendario, utilizza i dati disponibili per costruire un prompt arricchito
    e invia il prompt a GPT per rielaborare l'argomento in modo creativo e specifico.
    """
    for idx, row in calendar_df.iterrows():
        rubrica = row.get("Rubrica", "")
        keyword = row.get("Keyword", "")
        categoria = row.get("Categoria", "")
        mese = st.session_state.get("mese_selezionato", "")
        volume = ""
        # Se esiste una colonna con il volume nel df_kw, cercala
        if mese and keyword and ("df_kw" in st.session_state) and (mese in st.session_state["df_kw"].columns):
            df_kw = st.session_state["df_kw"]
            match_kw = df_kw[df_kw["keyword"].str.lower() == keyword.lower()]
            if not match_kw.empty:
                vol = match_kw.iloc[0][mese]
                volume = str(vol)
        prompt = generate_argument_prompt(rubrica, keyword, categoria, volume, mese)
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Sei un planner editoriale e copywriter esperto."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.5
            )
            calendar_df.at[idx, "ARGOMENTO"] = response.choices[0].message.content.strip()
        except Exception as e:
            calendar_df.at[idx, "ARGOMENTO"] = f"Errore GPT: {str(e)}"
    return calendar_df

def get_prompt_for_rubrica(df_copy, rubrica):
    """
    Recupera dal foglio "copy" il prompt base associato alla rubrica.
    """
    if "Rubrica" in df_copy.columns and "Prompt" in df_copy.columns:
        row = df_copy[df_copy["Rubrica"].str.lower() == rubrica.lower()]
        if not row.empty:
            return row.iloc[0]["Prompt"]
    return "Crea un copy promozionale in stile AIDA"

def split_ig_fb(text):
    """
    Divide il testo generato in due parti: una per Instagram e una per Facebook.
    Se non trova indicatori espliciti, prova a dividerlo per doppia interruzione di linea.
    """
    ig_text = ""
    fb_text = ""
    lines = text.splitlines()
    current_platform = None
    for l in lines:
        lower = l.lower().strip()
        if lower.startswith("instagram"):
            current_platform = "ig"
            ig_text = l.split(":", 1)[-1].strip()
        elif lower.startswith("facebook"):
            current_platform = "fb"
            fb_text = l.split(":", 1)[-1].strip()
        else:
            if current_platform == "ig":
                ig_text += " " + l
            elif current_platform == "fb":
                fb_text += " " + l
    if not ig_text and not fb_text:
        parts = text.split("\n\n")
        if len(parts) >= 2:
            ig_text = parts[0].strip()
            fb_text = parts[1].strip()
        else:
            ig_text = text
            fb_text = text
    return ig_text.strip(), fb_text.strip()

def generate_copy_for_posts(calendar_df, df_copy):
    """
    Usa il prompt base, preso dal foglio "copy", e il campo ARGOMENTO per generare
    due varianti di copy (Instagram e Facebook) tramite GPT.
    """
    df = calendar_df.copy()
    for i, row in df.iterrows():
        rubrica = row["Rubrica"]
        argomento = row["ARGOMENTO"]
        base_prompt = get_prompt_for_rubrica(df_copy, rubrica)
        full_prompt = f"""
{base_prompt}

ARGOMENTO: {argomento}
This GPT generates social media copy for Agristore's Instagram and Facebook accounts, as well as newsletters. Its goal is to maintain a consistent brand tone while evolving and adapting to current trends. It analyzes existing social media posts and metrics such as likes, comments, and shares to understand the language and style that resonate best with the audience. It can create tailored copy for various content types like promotions, announcements, and storytelling, while prioritizing formats that have shown higher engagement. It also suggests relevant hashtags based on performance and themes, and adjusts content for seasonal or event-specific promotions. The GPT is integrated with Instagram and Facebook APIs to extract and analyze posts, allowing it to optimize its output continuously. All posts must be generated in Italian.
Genera 2 varianti brevi (massimo 250 caratteri ciascuna):
1) Instagram (tono informale, emoji ammesse)
2) Facebook (leggermente più descrittivo).

**Characteristics of the Guardian Archetype:**
1. **Reliability:** Agristore.it is a reliable reference point where customers know they can find what they need, confident in receiving quality products.
2. **Protection:** The brand cares about the success and well-being of its customers, providing them with the tools they need to protect and grow their crops.
3. **Constant Support:** Agristore.it is always present to assist customers, answering their questions and providing help at every stage of the purchasing process and product use.

**Communication Style:**
- Short, punchy texts with a CTA in the first part, no longer than 2 lines.
- Use ‘tu.’
- Simple and concrete: directly address practical needs.
- Emphasize the practical benefits of the products.
- Use the AIDA framework: Attention, Interest, Desire, Action.
Lingua obbligatoria dei contenuti: italiano.
Example:
Post: "Hai bisogno di un attrezzo che duri nel tempo? Scopri la nostra gamma di motoseghe per lavori pesanti. Facile da usare, robusta e pronta a lavorare con te. 💪"
When you make a copy for Instagram or Facebook add the: #agristore and #agristoreItalia
        """
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Sei GPT specializzato in copywriting per social media."},
                    {"role": "user", "content": full_prompt}
                ],
                max_tokens=300,
                temperature=0.7
            )
            out = response.choices[0].message.content
            ig_text, fb_text = split_ig_fb(out)
            df.at[i, "COPY_IG"] = ig_text
            df.at[i, "COPY_FB"] = fb_text
        except Exception as e:
            df.at[i, "COPY_IG"] = f"Err GPT: {e}"
            df.at[i, "COPY_FB"] = f"Err GPT: {e}"
    return df

#########################################
# AVVIO DELL'APP PRINCIPALE
#########################################

def main():
    st.title("Piano Editoriale Automatico per Agristore.it")
    st.markdown("""
**Funzionalità Principali:**
1. Caricamento del file Excel **contenuti.xlsx** (fogli: keyword, categorie, prodotti, copy).
2. Pre-elaborazione dei dati (normalizzazione, rimozione righe con 'total').
3. (Opzionale) Analisi con GPT per un report "umano" sulle keyword/categorie.
4. Generazione della struttura del calendario editoriale.
5. Assegnazione automatica degli argomenti (keyword, categorie e prodotti).
6. Rifinitura degli argomenti con GPT per renderli più "umani".
7. Generazione dei copy per Instagram e Facebook tramite GPT.
8. Esportazione del calendario in CSV.
    """)

    # ---------------------------
    # A) CONFIGURAZIONE API KEY (Sidebar)
    # ---------------------------
    st.sidebar.header("Configurazione OpenAI")
    openai_api_key_input = st.sidebar.text_input("Inserisci la tua OpenAI API Key:", type="password")
    if openai_api_key_input:
        openai.api_key = openai_api_key_input
        st.sidebar.success("API Key impostata correttamente da input!")
    else:
        env_api_key = os.getenv("OPENAI_API_KEY")
        if env_api_key:
            openai.api_key = env_api_key
            st.sidebar.info("API Key letta dalla variabile d'ambiente.")
        else:
            st.sidebar.warning("Inserire una chiave OpenAI valida per usare GPT.")
    
    # ---------------------------
    # STEP 1: Caricamento file di input
    # ---------------------------
    st.header("1) Caricamento file di input")
    file_contenuti = st.file_uploader("Carica il file contenuti.xlsx (fogli: keyword, categorie, prodotti, copy)", type=["xlsx"])
    if file_contenuti is not None:
        with st.spinner("Caricamento in corso..."):
            df_kw, df_cat, df_prod, df_copy = load_datasets(file_contenuti)
            if any(x is None for x in [df_kw, df_cat, df_prod, df_copy]):
                st.error("Errore nel caricamento dei dati. Verifica che il file contenga tutti i fogli richiesti.")
                return
            st.success("File caricati con successo!")
            with st.expander("Dati Keyword (sheet 'keyword')"):
                st.dataframe(df_kw, use_container_width=True)
            with st.expander("Dati Categorie (sheet 'categorie')"):
                st.dataframe(df_cat, use_container_width=True)
            with st.expander("Dati Prodotti (sheet 'prodotti')"):
                st.dataframe(df_prod, use_container_width=True)
            with st.expander("Dati Copy (sheet 'copy')"):
                st.dataframe(df_copy, use_container_width=True)
            
            st.session_state["df_kw"] = df_kw
            st.session_state["df_cat"] = df_cat
            st.session_state["df_prod"] = df_prod
            st.session_state["df_copy"] = df_copy
    else:
        st.warning("Carica il file contenuti.xlsx per procedere.")
        return

    # ---------------------------
    # STEP 2: Analisi di Keyword/Categorie con GPT (opzionale)
    # ---------------------------
    st.header("2) Analisi di Keyword/Categorie con GPT (opzionale)")
    st.markdown("""
Se desideri un'analisi sintetica delle keyword per comprendere quali macro-categorie emergono, usa il modulo GPT (Modulo 1).
    """)
    use_gpt_analysis = st.checkbox("Usa GPT per analisi e report?")
    if use_gpt_analysis:
        if st.button("Analizza con GPT (Modulo 1)"):
            with st.spinner("Analisi in corso..."):
                mese_richiesto = "Aprile"
                st.session_state["mese_selezionato"] = mese_richiesto
                df_kw_sample = get_relevant_keywords_for_month(st.session_state["df_kw"],
                                                               st.session_state["df_cat"],
                                                               mese_richiesto,
                                                               top_n=10,
                                                               min_volume=1000)
                analysis_summary = analyze_with_gpt_module1(df_kw_sample)
                st.text_area("Report GPT:", analysis_summary, height=200)

    # ---------------------------
    # STEP 3: Creazione Calendario e Definizione Uscite per Rubrica
    # ---------------------------
    st.header("3) Creazione Calendario e Definizione Uscite per Rubrica")
    mese = st.selectbox("Seleziona il mese di riferimento", 
                        ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno",
                         "Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"])
    st.session_state["mese_selezionato"] = mese
    st.subheader("Imposta il numero di post per rubrica:")
    n_prodotto = st.number_input("Post di Prodotto", min_value=0, value=3, step=1)
    n_categoria = st.number_input("Post di Categoria", min_value=0, value=2, step=1)
    n_servizi = st.number_input("Post di Servizi", min_value=0, value=1, step=1)
    n_clienti = st.number_input("Post Clienti", min_value=0, value=1, step=1)
    n_curiosita = st.number_input("Post Curiosità", min_value=0, value=1, step=1)
    rubrica_dict = {
        "Prodotto": n_prodotto,
        "Categoria": n_categoria,
        "Servizi": n_servizi,
        "Clienti": n_clienti,
        "Curiosità": n_curiosita
    }
    if st.button("Genera Struttura Calendario"):
        calendar_df = create_calendar_structure(mese, rubrica_dict)
        st.session_state["calendar_df"] = calendar_df
        st.success(f"Creati {len(calendar_df)} slot di post per il mese di {mese}.")
        st.dataframe(calendar_df, use_container_width=True)

    # ---------------------------
    # STEP 4: Assegnazione Iniziale degli Argomenti
    # ---------------------------
    st.header("4) Assegna Argomenti al Calendario")
    if "calendar_df" not in st.session_state:
        st.info("Crea prima la struttura del calendario.")
        return
    else:
        calendar_df = st.session_state["calendar_df"]
    if st.button("Assegna Argomenti (Keyword/Categoria)"):
        with st.spinner("Assegnazione argomenti in corso..."):
            calendar_df = assign_initial_topics(calendar_df,
                                                  st.session_state["df_kw"],
                                                  st.session_state["df_cat"],
                                                  st.session_state["df_prod"])
            st.session_state["calendar_df"] = calendar_df
        st.success("Argomenti assegnati!")
        st.dataframe(calendar_df, use_container_width=True)

    # ---------------------------
    # STEP 5: Rielaborazione Argomenti con GPT (Modulo 2)
    # ---------------------------
    st.header("5) Rielabora Argomenti con GPT (più 'umani')")
    st.markdown("Rielabora gli argomenti in modo più creativo e contestualizzato usando GPT.")
    if st.button("💡 Genera Argomenti (Modulo 2)"):
        with st.spinner("GPT sta rielaborando gli argomenti..."):
            calendar_df = refine_arguments_with_gpt(st.session_state["calendar_df"])
            st.session_state["calendar_df"] = calendar_df
        st.success("Argomenti aggiornati!")
        st.dataframe(calendar_df, use_container_width=True)

    # ---------------------------
    # STEP 6: Generazione dei COPY per IG e FB
    # ---------------------------
    st.header("6) Genera i Copy per Instagram e Facebook")
    if st.button("✍️ Genera COPY"):
        with st.spinner("GPT sta generando i copy..."):
            try:
                df_copy_finale = generate_copy_for_posts(st.session_state["calendar_df"], st.session_state["df_copy"])
                st.session_state["calendar_df"] = df_copy_finale
                st.success("Copy generati con successo!")
            except Exception as e:
                st.error(f"Errore durante la generazione dei copy: {str(e)}")
        st.dataframe(st.session_state["calendar_df"], use_container_width=True)

    # ---------------------------
    # STEP 7: Esportazione in CSV
    # ---------------------------
    st.header("7) Esporta il Piano Editoriale in CSV")
    if "calendar_df" in st.session_state:
        final_df = st.session_state["calendar_df"]
        csv_data = final_df.to_csv(index=False)
        st.download_button("📥 Scarica CSV",
                           csv_data,
                           file_name=f"PED_{mese}.csv",
                           mime="text/csv")
    else:
        st.info("Non c'è ancora un piano da esportare.")

def analyze_with_gpt_module1(df_sample):
    """
    Esempio di funzione GPT per analizzare un gruppo di keyword e fornire un report
    sintetico sulle macro-categorie principali.
    """
    text_lines = []
    for i, row in df_sample.iterrows():
        kw = row.get("keyword", "")
        text_lines.append(f"- {kw}")
    sample_text = "\n".join(text_lines)

    prompt = f"""
Sei un esperto di marketing e SEO nel settore agricoltura/giardinaggio.
Ecco un elenco di {len(df_sample)} keyword:
{sample_text}

Analizza il gruppo e indica quali macro-categorie emergono 
e quali keyword potrebbero essere le più rilevanti per incrementare l'engagement sui social.
Usa un tono umano, informale ma professionale.
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Sei un esperto SEO e di marketing per il settore agricoltura/giardinaggio."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Errore GPT: {str(e)}"

if __name__ == "__main__":
    main()
