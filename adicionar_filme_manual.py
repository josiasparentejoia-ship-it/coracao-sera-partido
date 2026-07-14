"""
Adicionar filme manualmente ao banco de dados
"""
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from database import init_db, adicionar_filme, listar_filmes_ativos
import json

# Inicializar banco
init_db()

# Dados do filme
nome = "Uma Ideia de Você, 2024 (Dublado)"
slug = "uma_ideia_de_voc_2024_dublado"
descricao = "✨ Uma Ideia de Você é um romance emocionante que prova que o amor pode surgir nos momentos mais inesperados. Entre paixão, desafios e escolhas difíceis, o filme entrega uma história envolvente que conquista do início ao fim e faz acreditar que nunca é tarde para viver um grande amor. 💖"
poster_path = "uma_ideia_de_voc_2024_dublado_poster.jpg"
video_path = ""  # Sem vídeo
canal_id = -1003977986178
principal = True  # Definir como filme principal

print("="*80)
print("ADICIONANDO FILME AO BANCO DE DADOS")
print("="*80)
print(f"\nNome: {nome}")
print(f"Slug: {slug}")
print(f"Descrição: {descricao[:100]}...")
print(f"Poster: {poster_path}")
print(f"Canal ID: {canal_id}")
print(f"Principal: {principal}")

# Adicionar filme
try:
    filme_id = adicionar_filme(
        nome=nome,
        slug=slug,
        descricao=descricao,
        poster_path=poster_path,
        video_path=video_path,
        canal_id=canal_id,
        principal=principal
    )
    print(f"\n✓ Filme adicionado com ID: {filme_id}")
except Exception as e:
    print(f"\n✗ Erro ao adicionar filme: {e}")
    sys.exit(1)

# Listar filmes
print("\n" + "-"*80)
print("FILMES NO CATÁLOGO:")
print("-"*80)
filmes = listar_filmes_ativos()
for filme_data in filmes:
    filme_id, nome, slug, descricao, poster_path, video_path, canal_id, principal = filme_data
    print(f"\n{filme_id}. {nome}")
    print(f"   Slug: {slug}")
    print(f"   Canal ID: {canal_id}")
    print(f"   Principal: {'Sim' if principal else 'Não'}")

# Gerar catalogo.json
print("\n" + "-"*80)
print("GERANDO catalogo.json")
print("-"*80)

catalogo = []
for filme_data in filmes:
    filme_id, nome, slug, descricao, poster_path, video_path, canal_id, principal = filme_data
    catalogo.append({
        "id": filme_id,
        "nome": nome,
        "slug": slug,
        "descricao": descricao,
        "poster": poster_path,
        "video": video_path,
        "principal": principal == 1
    })

with open("catalogo.json", "w", encoding="utf-8") as f:
    json.dump({"filmes": catalogo}, f, ensure_ascii=False, indent=2)

print("✓ catalogo.json gerado com sucesso!")

print("\n" + "="*80)
print("CONCLUÍDO!")
print("="*80)
print(f"\nLink direto: /start {slug}")
print(f"O filme está disponível no catálogo!")
