import requests

login_url = "https://gestionpi2.ikeasi.com/login"
data = {
    "username": "ikea",
    "password": "Ikea1234",
    "next": "/"  # Opcional
}

response = requests.post(login_url, data=data)

# Verificar la respuesta
print(response.status_code)
print(response.headers)  # Ver la cookie de sesión si el login fue exitoso