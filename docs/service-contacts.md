# Contacts

Ubicación: `services/contacts`

Responsabilidades:
- CRUD de contactos
- Búsqueda y filtrado por etiquetas y atributos

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/contacts` | Crea un contacto. |
| `GET` | `/api/contacts` | Lista todos los contactos. |
| `GET` | `/api/contacts/{id}` | Obtiene un contacto por `id`. |
| `PUT` | `/api/contacts/{id}` | Actualiza un contacto. |
| `DELETE` | `/api/contacts/{id}` | Elimina un contacto. |
| `GET` | `/api/contacts/search` | Filtra por `tags` y `attr_key/attr_value`. |

Parámetros de búsqueda:
- `tags`: repetir el parámetro para buscar por múltiples etiquetas.
- `attr_key` y `attr_value`: par clave/valor para comparar con `attributes`.

## Variables de entorno
- `DATABASE_URL`

## Ejecutar en dev
```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
