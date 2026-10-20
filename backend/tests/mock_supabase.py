"""Servidor falso con la forma de la API de Supabase Storage, para probar el cliente HTTP sin red."""
import http.server, threading, json, re
from urllib.parse import unquote

class Estado:
    objetos = {}      # "bucket/ruta" -> bytes
    peticiones = []   # (metodo, ruta, cabeceras)
    fallar = False    # simula caída
    reglas_clave = None

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _resp(self, code, cuerpo=b"", tipo="application/json"):
        self.send_response(code); self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo))); self.end_headers(); self.wfile.write(cuerpo)
    def _clave(self):
        m = re.match(r"^/storage/v1/object/(?:authenticated/)?(.+)$", unquote(self.path.split("?")[0]))
        return m.group(1) if m else None
    def _registrar(self):
        Estado.peticiones.append((self.command, self.path, dict(self.headers)))
        if Estado.fallar:
            self._resp(500, b'{"message":"boom"}'); return False
        if not self.headers.get("apikey"):
            self._resp(401, b'{"message":"No API key"}'); return False
        return True
    def do_POST(self):
        if not self._registrar(): return
        n = int(self.headers.get("Content-Length", 0)); cuerpo = self.rfile.read(n); k = self._clave()
        if k in Estado.objetos and self.headers.get("x-upsert") != "true":
            self._resp(400, b'{"statusCode":"409","error":"Duplicate","message":"The resource already exists"}'); return
        Estado.objetos[k] = cuerpo; self._resp(200, json.dumps({"Key": k}).encode())
    do_PUT = do_POST
    def do_GET(self):
        if not self._registrar(): return
        k = self._clave()
        if k not in Estado.objetos:   # Supabase real responde 400 con statusCode 404 en el cuerpo
            self._resp(400, b'{"statusCode":"404","error":"not_found","message":"Object not found"}'); return
        self._resp(200, Estado.objetos[k], "application/octet-stream")
    def do_DELETE(self):
        if not self._registrar(): return
        k = self._clave(); Estado.objetos.pop(k, None); self._resp(200, b'{"message":"Successfully deleted"}')

def iniciar(puerto=0):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", puerto), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"
