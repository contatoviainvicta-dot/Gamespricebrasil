# GamePrice Brasil - versao Streamlit + Supabase

Comparador de precos de jogos construido com a stack que voce ja domina:
**Streamlit** (interface) + **Supabase** (banco PostgreSQL + API) + **GitHub Actions**
(atualizacao automatica de precos).

## Como cada peca se encaixa

- **Supabase**: guarda os dados (jogos, lojas, ofertas, precos, alertas) e expoe uma
  API automatica. Voce so cola o `db/schema.sql` no SQL Editor.
- **Streamlit** (`app.py`): a interface. Le e escreve no Supabase com a chave *anon*.
- **GitHub Actions** (`.github/workflows/update-prices.yml`): roda o `worker/update_prices.py`
  a cada 6h, busca precos nas lojas e grava no Supabase com a chave *service_role*.

## Passo a passo

### 1. Criar o banco no Supabase
1. Crie um projeto em https://supabase.com (gratuito).
2. Va em **SQL Editor > New query**, cole o conteudo de `db/schema.sql` e clique em **Run**.
3. Faca o mesmo com `db/seed.sql` (dados de exemplo, para o app nao nascer vazio).
4. Em **Project Settings > API**, anote tres coisas:
   - **Project URL** (ex.: `https://xxxx.supabase.co`)
   - **anon public** key (usada pelo Streamlit)
   - **service_role** key (usada pelo worker - mantenha em segredo!)

### 2. Rodar o app localmente (opcional)
```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edite secrets.toml com a URL e a anon_key
streamlit run app.py
```
Abre em http://localhost:8501

### 3. Publicar no Streamlit Community Cloud (gratuito)
1. Suba este projeto para um repositorio no GitHub (veja abaixo).
2. Em https://share.streamlit.io , clique em **New app** e selecione o repositorio.
3. Em **Advanced settings > Secrets**, cole:
```toml
   [supabase]
   url = "https://SEU-PROJETO.supabase.co"
   anon_key = "SUA-CHAVE-ANON"
```
4. Deploy. Pronto - seu app ganha um link publico.

### 4. Ligar a atualizacao automatica de precos (GitHub Actions)
No repositorio do GitHub: **Settings > Secrets and variables > Actions > New repository secret**.
Crie dois segredos:
- `SUPABASE_URL` = a Project URL
- `SUPABASE_SERVICE_KEY` = a chave **service_role**

O cron roda sozinho a cada 6h. Para testar agora, va na aba **Actions > update-prices >
Run workflow** (botao manual). Depois recarregue o Streamlit e veja os precos reais da Steam.

## Subir para o GitHub
```bash
cd gameprice-streamlit
git init
git add .
git commit -m "GamePrice Brasil - Streamlit + Supabase"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/gameprice-streamlit.git
git push -u origin main
```
> O `.gitignore` ja evita subir `secrets.toml` (suas chaves nao vao para o GitHub).

## O que ja funciona e o que vem depois

Funciona: busca, ranking 🥇🥈🥉 com diferenca percentual, historico em grafico, criacao de
alertas, e o worker da Steam (sem credencial). 

Proximos passos: conector do Mercado Livre (precisa de token OAuth - ha um scaffold em
`worker/connectors.py`), envio de e-mail dos alertas (pode virar outro GitHub Action
diario, ou uma Edge Function do Supabase), login real com Supabase Auth, e dashboard de
metricas.

## Limite honesto desta stack
Streamlit nao gera URLs amigaveis nem sitemap, entao **nao e ideal para SEO** (trafego
organico do Google). Para validar o produto e os primeiros usuarios, e perfeito. Se o SEO
virar prioridade, a hora e de colocar um frontend Next.js como vitrine na frente do mesmo
Supabase.
