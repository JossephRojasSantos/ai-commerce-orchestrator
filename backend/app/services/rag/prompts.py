SYSTEM_RECOMMEND = (
    "Eres un asistente de ventas experto de Tienda Mágica, una tienda de juguetes y regalos. "
    "Tu tarea es recomendar productos del catálogo basándote exclusivamente en los resultados "
    "de búsqueda semántica proporcionados. No inventes productos ni precios. "
    "Responde en español, de forma amigable y concisa (máximo 3 párrafos)."
)

USER_RECOMMEND = """\
Consulta del cliente: {query}

Productos encontrados en el catálogo (ordenados por relevancia):
{products_block}

Recomienda los productos más adecuados para la consulta del cliente. \
Si hay productos en oferta menciónalos. \
Incluye el enlace de cada producto recomendado."""


def build_products_block(hits: list[dict]) -> str:
    lines = []
    for i, h in enumerate(hits, 1):
        sale = f" (antes {h['regular_price']})" if h.get("sale_price") else ""
        stock = "disponible" if h.get("stock_status") == "instock" else "agotado"
        lines.append(
            f"{i}. {h['name']} — ${h['price']}{sale} — {stock}\n"
            f"   Categorías: {', '.join(h.get('categories', []))}\n"
            f"   {h.get('short_description', '')}\n"
            f"   Enlace: {h.get('permalink', '')}"
        )
    return "\n\n".join(lines)
