# Getting Started

Requisitos:
- Docker y Docker Compose
- Node.js (para desarrollo frontend opcional)
- Python 3.12 (para ejecutar servicios localmente sin Docker)

Pasos rápidos:
1. Copiar `.env.example` → `.env` y ajustar variables.
2. `make up` o `docker compose up -d --build`
3. Abrir `http://localhost` para acceder al frontend.

Comandos útiles:
```powershell
# Levantar todo
make up
# Ver logs
make logs
# Parar y eliminar volúmenes
make down
```
