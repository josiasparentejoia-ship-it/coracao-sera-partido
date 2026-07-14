"""
Script de analise - mostra usuarios que deram start mas nunca entraram no grupo
Apenas visualizacao, sem gerar links.
"""
import sys
from datetime import datetime
from database import init_db, listar_usuarios_sem_acesso

# Configurar encoding para UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


def analisar_usuarios():
    """Analisa usuarios que deram start mas nunca entraram"""

    # Inicializar banco de dados
    init_db()

    # Buscar usuarios sem acesso
    usuarios_sem_acesso = listar_usuarios_sem_acesso()
    total = len(usuarios_sem_acesso)

    print(f"\n{'='*70}")
    print(f"ANALISE DE USUARIOS - SEU CORACAO SERA PARTIDO")
    print(f"{'='*70}\n")

    print(f"Total de usuarios que deram /start mas NUNCA entraram no grupo: {total}\n")

    if total == 0:
        print("Nao ha usuarios pendentes!\n")
        print("Todos que deram /start ja tem acesso ao canal.\n")
        return

    print(f"{'─'*70}")
    print("LISTA COMPLETA DE USUARIOS:")
    print(f"{'─'*70}\n")

    for i, (user_id, data_vis) in enumerate(usuarios_sem_acesso, 1):
        data_str = datetime.fromtimestamp(data_vis).strftime("%d/%m/%Y às %H:%M")
        dias_atras = (datetime.now().timestamp() - data_vis) / 86400

        print(f"{i:3d}. User ID: {user_id:12d} | /start em: {data_str} ({dias_atras:.0f} dias atrás)")

    print(f"\n{'─'*70}")
    print(f"ESTATISTICAS:")
    print(f"{'─'*70}\n")

    # Calcular algumas estatisticas
    datas = [data_vis for _, data_vis in usuarios_sem_acesso]

    if datas:
        data_mais_antiga = min(datas)
        data_mais_recente = max(datas)

        print(f"Primeiro /start (mais antigo): {datetime.fromtimestamp(data_mais_antiga).strftime('%d/%m/%Y as %H:%M')}")
        print(f"Ultimo /start (mais recente): {datetime.fromtimestamp(data_mais_recente).strftime('%d/%m/%Y as %H:%M')}")

        # Usuarios por periodo
        agora = datetime.now().timestamp()
        ultimas_24h = sum(1 for data in datas if (agora - data) <= 86400)
        ultimos_7d = sum(1 for data in datas if (agora - data) <= 604800)
        ultimos_30d = sum(1 for data in datas if (agora - data) <= 2592000)

        print(f"\nDistribuicao por periodo:")
        print(f"   * Ultimas 24 horas: {ultimas_24h} usuarios")
        print(f"   * Ultimos 7 dias: {ultimos_7d} usuarios")
        print(f"   * Ultimos 30 dias: {ultimos_30d} usuarios")
        print(f"   * Mais de 30 dias: {total - ultimos_30d} usuarios")

    print(f"\n{'='*70}")
    print(f"PROXIMOS PASSOS:")
    print(f"{'='*70}\n")
    print(f"Para gerar links exclusivos para esses {total} usuarios, execute:")
    print(f"   python gerar_links_usuarios.py\n")
    print(f"Ou use a funcao de envio em massa no painel admin do bot:")
    print(f"   /admin -> Enviar Convites\n")


if __name__ == "__main__":
    analisar_usuarios()
