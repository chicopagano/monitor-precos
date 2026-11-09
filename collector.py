import os
import re
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

# Configurações do Supabase via Secrets do GitHub
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configurações da Uappi via Secrets do GitHub
UAPPI_API_URL = os.environ.get("UAPPI_API_URL")
UAPPI_KEY = os.environ.get("UAPPI_TOKEN")
UAPPI_SECRET = os.environ.get("UAPPI_SECRET")


def sincronizar_produtos_uappi():
    """Busca os produtos da API da Uappi e salva/atualiza no Supabase"""
    print("Iniciando sincronização com a Uappi...")
    
    headers = {
        "x-api-key": UAPPI_KEY,
        "x-secret-key": UAPPI_SECRET,
        "Content-Type": "application/json"
    }

    try:
        url_endpoint = f"{UAPPI_API_URL.rstrip('/')}/v2/products"
        response = requests.get(url_endpoint, headers=headers, timeout=20)
        
        if response.status_code == 200:
            dados = response.json()
            produtos = dados.get("data", dados if isinstance(dados, list) else [])

            for item in produtos:
                sku = str(item.get("sku") or item.get("id"))
                nome = item.get("title") or item.get("name")
                preco = item.get("price") or item.get("special_price")

                if sku and preco:
                    supabase.table("meus_produtos").upsert({
                        "sku": sku,
                        "nome": nome,
                        "preco_proprio": float(preco)
                    }, on_conflict="sku").execute()

            print(f"Sincronização Uappi concluída! {len(produtos)} produtos verificados.")
        else:
            print(f"Erro ao acessar API Uappi: Status {response.status_code} - {response.text}")

    except Exception as e:
        print(f"Erro na integração Uappi: {e}")


def extrair_preco_concorrente(url: str) -> float:
    """Raspa o preço atual na página do concorrente"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(response.content, "html.parser")

    # Extração via Schema.org / OpenGraph
    meta_price = soup.find("meta", {"property": "product:price:amount"}) or soup.find("meta", {"property": "og:price:amount"})
    if meta_price and meta_price.get("content"):
        return float(meta_price["content"].replace(",", "."))

    # Extração via busca de texto/moeda no HTML
    elementos = soup.find_all(class_=re.compile(r"price|preco|val", re.IGNORECASE))
    for elem in elementos:
        texto = elem.get_text(strip=True)
        match = re.search(r"R\$\s?(\d+[\.,]?\d*)", texto)
        if match:
            valor_str = match.group(1).replace(".", "").replace(",", ".")
            return float(valor_str)

    return 0.0


def monitorar_concorrentes():
    """Busca os concorrentes cadastrados e salva o novo preço"""
    res = supabase.table("concorrentes_produtos").select("id, url_concorrente").execute()
    concorrentes = res.data

    for item in concorrentes:
        try:
            preco = extrair_preco_concorrente(item["url_concorrente"])
            if preco > 0:
                supabase.table("historico_precos").insert({
                    "concorrente_id": item["id"],
                    "preco_encontrado": preco,
                    "em_estoque": True
                }).execute()
                print(f"Sucesso: {item['url_concorrente']} -> R$ {preco}")
        except Exception as e:
            print(f"Erro ao monitorar {item['url_concorrente']}: {e}")


if __name__ == "__main__":
    sincronizar_produtos_uappi()
    monitorar_concorrentes()
