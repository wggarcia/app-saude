import requests

BASE_URL = "http://127.0.0.1:8000"

def testar_login():
    print("\n🔐 TESTANDO LOGIN...")

    dados = {
        "email": "teste@teste.com",
        "senha": "123456"
    }

    r = requests.post(f"{BASE_URL}/api/login", json=dados)

    print("STATUS LOGIN:", r.status_code)
    print("RESPOSTA:", r.text)

    if r.status_code != 200:
        return None

    data = r.json()

    token = data.get("token")

    if not token:
        print("❌ LOGIN NÃO RETORNOU TOKEN")
        return None

    print("✅ TOKEN OK:", token[:30], "...")
    return token


def testar_pagamento(token):
    print("\n💳 TESTANDO PAGAMENTO...")

    headers = {
        "Authorization": f"Bearer {token}"
    }

    r = requests.post(f"{BASE_URL}/api/pagamento/", headers=headers)

    print("STATUS PAGAMENTO:", r.status_code)
    print("RESPOSTA:", r.text)

    if r.status_code == 200:
        print("✅ PAGAMENTO OK")
    else:
        print("❌ ERRO NO PAGAMENTO")


def testar_sem_token():
    print("\n🚫 TESTANDO SEM TOKEN...")

    r = requests.post(f"{BASE_URL}/api/pagamento/")

    print("STATUS:", r.status_code)
    print("RESPOSTA:", r.text)


if __name__ == "__main__":

    print("\n🚀 INICIANDO TESTES DO SISTEMA\n")

    token = testar_login()

    if token:
        testar_pagamento(token)

    testar_sem_token()

    print("\n🏁 FIM DOS TESTES\n")
