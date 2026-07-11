# 🎬 Guia Completo do Sistema de Catálogo de Filmes

## 📋 O que foi implementado:

### ✅ **Sistema Completo**
1. **Banco de dados** para armazenar catálogo
2. **Painel admin** para gerenciar filmes
3. **Catálogo HTML dinâmico** responsivo
4. **Deep linking** (link direto para filme específico)
5. **Geração automática de links** exclusivos por canal
6. **Multi-canal** (cada filme pode ter seu próprio canal)

---

## 🚀 Como Usar:

### **1. Configurar o Mini App URL**

Atualize no `config.py` a URL do seu GitHub Pages apontando para o **catalogo.html**:

```python
MINI_APP_URL = "https://josiasparentejoia-ship-it.github.io/coracao-sera-partido/catalogo.html"
```

### **2. Fazer Upload dos Arquivos**

Faça upload no GitHub Pages:
- `catalogo.html` (novo catálogo)
- `catalogo.json` (será atualizado automaticamente pelo bot)
- Posters dos filmes (ex: `filme1_poster.jpg`)
- Vídeos opcionais (ex: `filme1_trailer.mp4`)

---

## 🎬 Adicionar Filme ao Catálogo:

### **Passo a passo:**

1. **Inicie o bot** e envie `/admin`

2. **Clique em:** `🎬 Gerenciar Catálogo`

3. **Clique em:** `➕ Adicionar Filme`

4. **Siga os 5 passos:**

   **Passo 1 - Nome:**
   ```
   Seu Coração Será Partido
   ```

   **Passo 2 - Descrição:**
   ```
   Um drama romântico russo emocionante sobre amor, bullying e superação.
   ```

   **Passo 3 - Poster:**
   - Envie a imagem do poster
   - Será salvo como `seu_coracao_sera_partido_poster.jpg`

   **Passo 4 - Vídeo (opcional):**
   - Envie um trailer/amostra
   - Ou digite `PULAR` para pular
   - Será salvo como `seu_coracao_sera_partido_trailer.mp4`

   **Passo 5 - ID do Canal:**
   ```
   -1004433990981
   ```
   
   💡 **Como obter ID do canal:**
   - Encaminhe uma mensagem do canal para @userinfobot
   - Copie o número que aparece

5. **Confirme digitando:** `SIM`

✅ **Pronto!** O filme já está no catálogo.

---

## 🔗 Como Funciona o Deep Linking:

### **Link Direto para Filme:**

```
https://t.me/seu_bot?start=seu_coracao_sera_partido
```

Quando alguém clicar nesse link:
1. Abre o bot
2. Mostra o catálogo com esse filme **em destaque**
3. Outros filmes aparecem abaixo
4. Ao clicar em qualquer filme → Link exclusivo do canal

---

## 📱 Experiência do Usuário:

### **Usuário comum:**
1. `/start` → Abre catálogo direto
2. Vê filme em destaque
3. Vê outros filmes disponíveis
4. Clica em um filme
5. **Bot envia link exclusivo do canal automaticamente**
6. Link funciona **1 vez só**

### **Admin:**
1. `/start` → Menu admin
2. Acessa todas as funções
3. Pode gerenciar catálogo
4. Todas as funções anteriores mantidas

---

## 🎯 Funcionalidades:

### **Para Admin:**
- ➕ Adicionar filmes ao catálogo
- 📋 Ver lista de filmes
- ⭐ Definir filme principal (destaque)
- 🗑️ Remover filmes
- 📊 Ver estatísticas
- 🔗 Gerar links diretos para filmes
- 📌 Publicar botões fixos no canal (função já existente)

### **Automático:**
- 📄 Gera `catalogo.json` automaticamente
- 🔄 Atualiza catálogo em tempo real
- 🎟️ Cria links únicos por filme/canal
- 💾 Registra todos os acessos
- 📊 Rastreia qual filme cada usuário assistiu

---

## 📁 Estrutura de Arquivos:

```
projeto/
├── bot.py                    # Bot principal (atualizado)
├── database.py              # Banco de dados (atualizado)
├── config.py                # Configurações (atualizado)
├── catalogo.html            # Novo catálogo (fazer upload)
├── catalogo.json            # Auto-gerado pelo bot
├── coracao.db               # Banco SQLite
│
├── Posters/Vídeos (na raiz):
│   ├── filme1_poster.jpg
│   ├── filme1_trailer.mp4
│   ├── filme2_poster.jpg
│   └── filme2_trailer.mp4
```

---

## 🔧 Configurar Múltiplos Canais:

Cada filme pode ter seu próprio canal:

**Filme 1:** Canal A (`-1001111111111`)
**Filme 2:** Canal B (`-1002222222222`)
**Filme 3:** Canal C (`-1003333333333`)

O bot:
- ✅ É admin de todos os canais
- ✅ Gera link exclusivo do canal correto
- ✅ Pode publicar botões fixos em cada canal
- ✅ Rastreia acessos separadamente

---

## 📌 Publicar Botões Fixos no Canal:

**Você decide o que escrever nos botões!**

Use a função: `📌 Publicar Botões no Canal`

**Exemplo de mensagem:**

```
❤️ Bem-vindo ao canal oficial!

Aproveite o filme e não esqueça de apoiar o projeto.

BOTOES:
❤️ Apoiar Dublagem | APOIAR
💬 Suporte | https://t.me/DrBuscaOfc
🎵 TikTok | https://www.tiktok.com/@ilovedoramaxx
🎬 Mais Filmes | https://t.me/seu_bot
```

Os botões serão criados automaticamente e a mensagem fica fixada no canal.

---

## 🎨 Personalização do Catálogo:

Edite `catalogo.html` para mudar:
- 🎨 Cores e design
- 📐 Layout do grid
- 🖼️ Tamanho dos posters
- 📝 Textos e descrições
- ✨ Animações

---

## 📊 Estatísticas e Rastreamento:

O sistema registra:
- ✅ Quem assistiu qual filme
- ✅ Quando foi o acesso
- ✅ Link usado
- ✅ Canal acessado
- ✅ Total de acessos por filme

**Ver links gerados:** `/admin` → `📋 Ver Links Gerados`

---

## 🔐 Segurança:

- ✅ Links únicos (1 uso por pessoa)
- ✅ Rastreamento completo
- ✅ Apenas admin gerencia catálogo
- ✅ Validação de dados
- ✅ Logs detalhados

---

## 💡 Exemplos de Uso:

### **Cenário 1: Lançamento de Novo Filme**
1. Cria canal novo no Telegram
2. Adiciona bot como admin
3. `/admin` → Adicionar filme
4. Compartilha link direto: `/start nome_filme`

### **Cenário 2: Promoção Específica**
1. Quer destacar um filme
2. Compartilha: `/start filme_especial`
3. Catálogo abre com esse filme em destaque
4. Outros filmes também aparecem

### **Cenário 3: Parceria com Influencer**
1. Gera link direto do filme
2. Influencer compartilha
3. Cada pessoa que clica recebe link exclusivo
4. Admin vê quantos acessos vieram desse link

---

## ⚙️ Configuração Importante:

**No `config.py`, remova a seção antiga `FILMES`** (não é mais necessária):

```python
# REMOVER ESTA PARTE:
# FILMES = {
#     "coracao_partido": {...},
# }
```

Agora tudo é gerenciado pelo banco de dados!

---

## 🎯 Resumo do Fluxo:

```
ADMIN:
/admin → Gerenciar Catálogo → Adicionar Filme → 
5 passos → Filme adicionado → catalogo.json atualizado →
Fazer upload no GitHub Pages

USUÁRIO:
Link direto ou /start → Catálogo abre → 
Escolhe filme → Bot gera link do canal → 
Acessa canal exclusivo → Assiste gratuitamente
```

---

## 🎬 Resultado Final:

✅ Catálogo visual profissional
✅ Múltiplos filmes em um único bot
✅ Cada filme com seu canal
✅ Links únicos e rastreáveis
✅ Deep linking funcionando
✅ Admin controla tudo
✅ Usuários veem só o catálogo
✅ Escalável (adiciona quantos filmes quiser)

---

## 📞 Suporte:

Se precisar de ajuda:
- 💬 Telegram: @DrBuscaOfc
- 🎵 TikTok: @ilovedoramaxx

---

**🎉 Divirta-se com seu catálogo de filmes!**
