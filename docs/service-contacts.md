# Contacts

Ubicación: `services/contacts`

Responsabilidades:
- CRUD de contactos
- Búsqueda y filtrado, etiquetas y atributos

Variables de entorno:
- `DATABASE_URL`

Ejecutar en dev:
```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
