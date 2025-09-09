# Seguridad

Puntos clave de seguridad y configuración recomendada:

- TLS en edge (Traefik) y servicios internos si es posible.
- Guardar secretos en Vault/SSM; no en `.env` en producción.
- RBAC y roles: Owner, Admin, Agent, Analyst.
- Auditoría: registrar cambios de flujo, envíos y acciones administrativas.
- Rotación de tokens y reglas de expiración.

Recomendaciones de despliegue y hardening en producción (TLS, WAF, límites).
